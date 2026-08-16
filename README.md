# AlphaMind AI

AlphaMind AI is an intelligent financial analysis assistant built with Python, FastAPI, and python-telegram-bot. It combines live market data fetching with LLM-driven tool calling to provide stock analysis, comparison reports, and interactive follow-up handling over Telegram and REST API endpoints.

---

## Project Overview

AlphaMind AI enables users to perform technical and fundamental stock analysis through natural language queries. The application connects to market data providers, provisions custom tool execution for AI agents, and maintains conversation context to understand follow-up questions and comparisons naturally.

### Key Capabilities
- **Telegram Bot Interface**: Interactive bot supporting real-time stock lookup, AI analysis, and provider configuration.
- **REST API Endpoints**: FastAPI service for managing company records and stock price histories.
- **LLM Tool Calling**: Autonomous multi-round agent loop that invokes stock quote and metadata tools as needed.
- **Contextual Conversation Tracking**: Preserves state (active ticker, comparison pair, turn history) and injects it into prompt context.
- **User-Level Provider Configuration**: Allows users to configure their own LLM provider and model with encrypted key storage.

---

## Core Features

- **Multi-Round AI Agent**: Powered by an autonomous tool-calling loop (`AIAgent`) that queries market tools before delivering responses.
- **LLM Provider Flexibility**: Supports Google Gemini and OpenAI models.
- **Contextual Follow-up Resolution**: Delegates natural-language references (`"it"`, `"this stock"`, `"the first company"`, `"which one is better?"`) to the primary LLM using structured context injection.
- **Financial Message Formatter**: Normalizes output markdown and formats financial metrics into standard structured views.
- **Secure Credentials Storage**: Encrypts user API keys at rest using Fernet (AES-256) symmetric encryption.
- **Market Data Integration**: Asynchronous Finnhub integration for real-time quotes, technical indicators, and company profiles.

---

## Architecture

```mermaid
flowchart TD
    User[Telegram User] --> Bot[Telegram Bot Handler]
    Client[REST API Client] --> API[FastAPI Web Server]

    Bot --> TelegramService[Telegram Analysis Service]
    TelegramService --> ContextMgr[Conversation Context Manager]
    TelegramService --> Agent[AIAgent Loop]

    Agent --> ToolRegistry[Tool Registry]
    ToolRegistry --> StockTools[Stock Quote & Company Tools]
    StockTools --> Finnhub[Finnhub Provider]
    Finnhub --> FinnhubAPI((Finnhub API))

    Agent --> LLMService[Configured LLM Service]
    LLMService --> LLMProviders[Gemini / OpenAI Providers]

    API --> Repositories[SQLAlchemy Repositories]
    Repositories --> Postgres[(PostgreSQL 17 Database)]

    AppInfra[Docker Compose] -. provisions .-> API
    AppInfra -. provisions .-> Postgres
    AppInfra -. provisions .-> Redis[(Redis 8 Cache)]
```

### Component Breakdown

| Component | Module | Responsibility |
| --- | --- | --- |
| **Telegram Bot** | `app/bot/telegram.py` | Handles Telegram commands (`/start`, `/help`, `/settings`) and message routing. |
| **Analysis Service** | `app/services/telegram_analysis.py` | Orchestrates user authentication, context prompt injection, agent invocation, and formatting. |
| **AI Agent** | `app/agent/agent.py` | Manages the multi-round tool execution loop (`max_rounds=5`) until a final answer is generated. |
| **Tool Registry** | `app/tools/registry.py` & `stock.py` | Defines and executes financial tools (`get_stock_price`, `get_company`, `search_company`). |
| **LLM Layer** | `app/llm/` | Interfaces with LLM providers (`GeminiProvider`, `OpenAIProvider`) via unified step generation contracts. |
| **Conversation Context** | `app/services/conversation_context.py` | Stores in-memory user context state (`active_ticker`, `comparison_pair`, `recent_tickers`, `history`). |
| **Security Layer** | `app/security/encryption.py` | Provides Fernet AES-256 encryption and decryption for user API keys. |
| **Database & ORM** | `app/database/` & `app/models/` | Manages PostgreSQL persistence for users, stock prices, companies, and configurations. |

---

## Conversation Context Design

AlphaMind AI maintains conversation state without hardcoded natural-language keyword rules or phrase dictionaries:

- **State Container (`ConversationContext`)**: Tracks explicit ticker symbols mentioned by the user, active comparison pairs, and recent conversation turns.
- **LLM Context Injection**: Injects a `[CONVERSATION CONTEXT & HISTORY]` block directly into the primary LLM system prompt.
- **Natural-Language Understanding**: Conversational references (`"it"`, `"that company"`, `"the first one"`, `"the second one"`) are interpreted semantically by the primary LLM based on history and active state.

---

## Supported LLM Providers

Users configure their LLM provider via the Telegram `/settings` command:

| Provider | Supported Models (Examples) | Setup Requirements |
| --- | --- | --- |
| **Gemini** | `gemini-3.1-flash-lite`, `gemini-1.5-pro` | Gemini API Key |
| **OpenAI** | `gpt-4o-mini`, `gpt-4o` | OpenAI API Key |

API keys entered through Telegram are encrypted before being stored in the database.

---

## Registered Tools

The AI agent has access to the following market tools:

- `get_stock_price`: Fetches current quote (`c`), price change (`d`, `dp`), high/low/open/previous close, and company details.
- `get_company`: Retrieves company metadata (industry, market capitalization, shares outstanding).
- `search_company`: Searches company names and ticker symbols via market data provider APIs.

---

## Project Structure

```
AlphaMind-AI/
├── alembic/                  # Database migration scripts
├── app/
│   ├── agent/                # AIAgent execution loop
│   ├── api/                  # FastAPI REST endpoints (companies, stock_prices)
│   ├── bot/                  # Telegram bot handlers & formatters
│   ├── core/                 # App configuration & settings
│   ├── database/             # SQLAlchemy session & base setup
│   ├── llm/                  # LLM providers (Gemini, OpenAI), managers, & prompts
│   ├── models/               # SQLAlchemy ORM models (User, Company, StockPrice, etc.)
│   ├── providers/            # External market data providers (Finnhub)
│   ├── repositories/         # Database repository layer
│   ├── schemas/              # Pydantic schemas
│   ├── security/             # AES-256 Fernet key encryption service
│   ├── services/             # Business logic & Telegram orchestration
│   └── tools/                # Registered agent tools
├── docker-compose.yml        # Docker Compose service definition
├── Dockerfile                # Application Docker container definition
├── pyproject.toml            # Project configuration
├── requirements.txt          # Python dependencies
└── test_*.py                 # Unit & integration test scripts
```

---

## Installation & Setup

### 1. Prerequisites
- **Python**: 3.14+ (or Python 3.10+)
- **Database**: PostgreSQL 17
- **Cache**: Redis 8
- **External API Key**: Finnhub API Key

### 2. Environment Setup

Clone the repository and create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration

Copy `.env.example` to `.env` and fill in required variables:

```bash
cp .env.example .env
```

Key environment variables:
- `DATABASE_URL`: PostgreSQL connection string (e.g., `postgresql+psycopg://user:password@localhost:5432/alphamind`)
- `REDIS_URL`: Redis connection string (e.g., `redis://localhost:6379/0`)
- `FINNHUB_API_KEY`: Your Finnhub API key
- `ENCRYPTION_KEY`: Fernet 32-byte url-safe base64 key for encrypting user API keys
- `TELEGRAM_BOT_TOKEN`: Telegram bot token from BotFather

### 4. Database Migrations

Run Alembic database migrations:

```bash
alembic upgrade head
```

---

## Running with Docker

AlphaMind AI includes Docker Compose definitions for running the application along with PostgreSQL and Redis:

```bash
docker compose up --build
```

Services provisioned:
- `app`: FastAPI web application running on port `8000`.
- `postgres`: PostgreSQL 17 database running on port `5432`.
- `redis`: Redis 8 cache server running on port `6379`.

---

## Testing

The project includes test scripts covering LLM integration, agent execution, context handling, message formatting, and settings management:

```bash
python test_agent.py
python test_sprint2_llm.py
python test_analysis_context.py
python test_telegram_llm.py
python test_llm.py
python test_llm_configuration.py
python test_context_reference.py
python test_formatter.py
```

---

## Usage Examples

### 1. Analyzing a Stock
```
User: Analyze AAPL
Bot: 📊 AAPL
     ━━━━━━━━━━━━━━━━━━
     🎯 CURRENT VIEW
     Neutral / Cautiously Positive
     ...
```

### 2. Follow-Up Question (Contextual Reference)
```
User: Would you buy it at this price?
Bot: [Uses active context (AAPL) to answer budget & purchasing risks without asking for the ticker again]
```

### 3. Comparing Two Companies
```
User: Compare PLTR and RKLB
Bot: [Executes comparison analysis using context pair [PLTR, RKLB]]
```

### 4. Comparing Contextual Ordinals
```
User: Which company looks stronger for growth?
Bot: [Evaluates PLTR vs RKLB growth outlooks based on comparison context]
```

---

## Security

- **At-Rest API Key Encryption**: User-provided LLM API keys are encrypted with Fernet AES-256 before storage in PostgreSQL.
- **Sanitized Outputs**: Credentials, encryption keys, and raw tokens are never exposed in log outputs or bot messages.

---

## Disclaimer

*This application is for educational and analytical purposes only. Nothing produced by AlphaMind AI constitutes financial, investment, or legal advice. Always conduct your own research before making financial decisions.*
