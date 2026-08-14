"""Structured analysis context for LLM stock analysis.

This module keeps data retrieval separate from LLM prompt construction.

The flow is:

    Stock data (company + quote + historical candles)
        -> Analysis Context (structured, with derived metrics)
        -> LLM Analysis Service
        -> Configured LLM Provider

Every derived metric returns ``None`` when there is insufficient data so the
LLM is never handed invented values.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Number of trading days of daily history to request/consider by default.
DEFAULT_LOOKBACK_DAYS = 250

# Windows for simple moving averages.
SMA_PERIODS = (20, 50)

# Cap on how many most-recent closes are placed directly in the context so the
# prompt stays bounded regardless of the lookback window.
RECENT_CLOSE_LIMIT = 90


# --- metric helpers ---------------------------------------------------------


def compute_sma(prices: list[float], period: int) -> float | None:
    """Return the simple moving average of the last ``period`` closes.

    Returns ``None`` when fewer than ``period`` prices are available so a
    computed value is never invented from insufficient data.
    """
    if period <= 0:
        return None

    if len(prices) < period:
        return None

    window = prices[-period:]
    return round(sum(window) / period, 6)


def compute_volatility(prices: list[float]) -> float | None:
    """Return the sample standard deviation of daily simple returns.

    Returns ``None`` when fewer than two usable returns exist.
    """
    returns: list[float] = []
    for index in range(1, len(prices)):
        previous = prices[index - 1]
        if previous == 0:
            continue
        returns.append((prices[index] - previous) / previous)

    if len(returns) < 2:
        return None

    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (
        len(returns) - 1
    )
    return round(variance ** 0.5, 6)


def compute_period_return(prices: list[float]) -> float | None:
    """Return the simple return over the whole available window.

    Returns ``None`` when fewer than two prices exist or the base price is 0.
    """
    if len(prices) < 2 or prices[0] == 0:
        return None

    return round((prices[-1] - prices[0]) / prices[0], 6)


def compute_distance_from_sma(
    price: float | None,
    sma: float | None,
) -> float | None:
    """Return how far ``price`` sits above/below an SMA as a ratio.

    Returns ``None`` when either input is missing or the SMA is 0.
    """
    if price is None or sma is None or sma == 0:
        return None

    return round((price - sma) / sma, 6)


# --- context data objects ---------------------------------------------------


@dataclass
class ContextCompany:
    name: str | None = None
    ticker: str | None = None
    industry: str | None = None
    market_cap: Any | None = None
    shares_outstanding: Any | None = None


@dataclass
class ContextMarket:
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    previous_close: float | None = None


@dataclass
class ContextHistorical:
    lookback_days: int = 0
    count: int = 0
    from_date: str | None = None
    to_date: str | None = None
    recent: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ContextMetrics:
    sma20: float | None = None
    sma50: float | None = None
    volatility: float | None = None
    period_return: float | None = None
    distance_from_sma20: float | None = None
    distance_from_sma50: float | None = None


@dataclass
class AnalysisContext:
    company: ContextCompany = field(default_factory=ContextCompany)
    market: ContextMarket = field(default_factory=ContextMarket)
    historical: ContextHistorical = field(default_factory=ContextHistorical)
    metrics: ContextMetrics = field(default_factory=ContextMetrics)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- helpers ----------------------------------------------------------------


def _as_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _company_snapshot(company: dict[str, Any] | None) -> ContextCompany:
    if not company:
        return ContextCompany()

    return ContextCompany(
        name=company.get("name"),
        ticker=company.get("ticker"),
        industry=company.get("finnhubIndustry"),
        market_cap=company.get("marketCapitalization"),
        shares_outstanding=company.get("shareOutstanding"),
    )


def _market_snapshot(quote: dict[str, Any] | None) -> ContextMarket:
    if not quote:
        return ContextMarket()

    return ContextMarket(
        price=_as_float(quote.get("c")),
        change=_as_float(quote.get("d")),
        change_percent=_as_float(quote.get("dp")),
        high=_as_float(quote.get("h")),
        low=_as_float(quote.get("l")),
        open=_as_float(quote.get("o")),
        previous_close=_as_float(quote.get("pc")),
    )


def _closes(candles: list[dict[str, Any]]) -> list[float]:
    closes: list[float] = []
    for candle in candles:
        value = _as_float(candle.get("close"))
        if value is not None:
            closes.append(value)
    return closes


# --- context builder --------------------------------------------------------


def build_analysis_context(
    company: dict[str, Any] | None,
    quote: dict[str, Any] | None,
    candles: list[dict[str, Any]] | None,
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> AnalysisContext:
    """Assemble a structured context from raw stock data.

    ``candles`` is a list of ``{"date": "YYYY-MM-DD", "close": float}``
    dicts ordered oldest -> newest. Missing inputs yield ``None`` instead of
    fabricated values.
    """
    candles = candles or []
    closes = _closes(candles)

    company_snapshot = _company_snapshot(company)
    market_snapshot = _market_snapshot(quote)

    sma20 = compute_sma(closes, 20)
    sma50 = compute_sma(closes, 50)

    reference_price = market_snapshot.price
    if reference_price is None and closes:
        reference_price = closes[-1]

    metrics = ContextMetrics(
        sma20=sma20,
        sma50=sma50,
        volatility=compute_volatility(closes),
        period_return=compute_period_return(closes),
        distance_from_sma20=compute_distance_from_sma(reference_price, sma20),
        distance_from_sma50=compute_distance_from_sma(reference_price, sma50),
    )

    first_date = candles[0].get("date") if candles else None
    last_date = candles[-1].get("date") if candles else None

    historical = ContextHistorical(
        lookback_days=lookback_days,
        count=len(candles),
        from_date=first_date,
        to_date=last_date,
        recent=candles[-RECENT_CLOSE_LIMIT:],
    )

    return AnalysisContext(
        company=company_snapshot,
        market=market_snapshot,
        historical=historical,
        metrics=metrics,
    )
