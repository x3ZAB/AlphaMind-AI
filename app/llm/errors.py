class LLMProviderError(RuntimeError):
    """Controlled error raised when an LLM request cannot be completed."""


class UnknownLLMProviderError(LLMProviderError):
    """Raised when a stored configuration names an unsupported provider."""
