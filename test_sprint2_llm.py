import asyncio
import json

import httpx
from cryptography.fernet import Fernet

from app.core.config import settings
from app.database.base import Base
from app.llm.base import BaseLLMProvider
from app.llm.errors import LLMProviderError, UnknownLLMProviderError
from app.llm.manager import LLMManager
from app.llm.prompts import ALPHAMIND_SYSTEM_PROMPT
from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.gemini import GeminiProvider
from app.llm.registry import LLMProviderRegistry
from app.llm.service import ConfiguredLLMService
from app.models import User, UserLLMConfiguration
from app.services.llm_analysis import LLMAnalysisService


class FakeProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def generate(self, messages, **kwargs) -> str:
        return messages[-1]["content"]


class FakeEncryptionService:
    def __init__(self, decrypted_key: str) -> None:
        self.decrypted_key = decrypted_key
        self.received_ciphertext = None

    def decrypt(self, value: str) -> str:
        self.received_ciphertext = value
        return self.decrypted_key


async def test_real_encryption_round_trip() -> None:
    key = Fernet.generate_key()
    original_key = "user-secret-api-key"
    original_encryption_key = settings.ENCRYPTION_KEY
    settings.ENCRYPTION_KEY = key.decode()
    try:
        from app.security.encryption import EncryptionService

        encryption = EncryptionService()
        encrypted = encryption.encrypt(original_key)
        assert encrypted != original_key
        assert encryption.decrypt(encrypted) == original_key
    finally:
        settings.ENCRYPTION_KEY = original_encryption_key


async def test_registry_and_unknown_provider() -> None:
    registry = LLMProviderRegistry({"fake": FakeProvider})
    provider = registry.create(
        "fake",
        api_key="not-used",
        model="test-model",
    )
    assert isinstance(provider, FakeProvider)

    try:
        registry.create("missing", api_key="not-used", model="test-model")
    except UnknownLLMProviderError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("Unknown provider did not raise")


async def test_openai_normalization_and_http_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["messages"] == [
            {"role": "user", "content": "provider-controlled"}
        ]
        assert payload["temperature"] == 0.2
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "  normalized response  "}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAIProvider(
            "secret-key",
            "test-model",
            client=client,
        )
        assert await provider.generate(
            [{"role": "user", "content": "provider-controlled"}],
            model="caller-model",
            temperature=0.2,
        ) == "normalized response"

    async def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    transport = httpx.MockTransport(error_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAIProvider("secret-key", "test-model", client=client)
        try:
            await provider.generate([])
        except LLMProviderError as exc:
            assert "secret-key" not in str(exc)
            assert "HTTP 401" in str(exc)
        else:
            raise AssertionError("HTTP error did not raise")


def _gemini_messages() -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": ALPHAMIND_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": "Question: analyze NVDA",
        },
    ]


async def test_gemini_uses_system_instruction_and_string_input() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "secret-key"
        payload = json.loads(request.content)
        assert payload["model"] == "gemini-3.1-flash-lite"
        assert payload["system_instruction"] == ALPHAMIND_SYSTEM_PROMPT
        assert payload["input"] == "Question: analyze NVDA"
        assert payload["store"] is True
        assert "user_input" not in json.dumps(payload)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [
                            {
                                "type": "text",
                                "text": "  balanced analysis  ",
                            }
                        ],
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = GeminiProvider(
            "secret-key",
            "gemini-3.1-flash-lite",
            client=client,
        )
        assert await provider.generate(_gemini_messages()) == "balanced analysis"


async def test_gemini_output_text_fallback() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output_text": "  direct output  ",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = GeminiProvider(
            "secret-key",
            "gemini-3.1-flash-lite",
            client=client,
        )
        assert await provider.generate(_gemini_messages()) == "direct output"


async def test_gemini_http_errors_are_controlled() -> None:
    secret_key = "super-secret-api-key"

    for status_code in (400, 401, 402, 403, 404, 429):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code,
                json={"error": "provider failure"},
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = GeminiProvider(
                secret_key,
                "gemini-3.1-flash-lite",
                client=client,
            )
            try:
                await provider.generate(_gemini_messages())
            except LLMProviderError as exc:
                assert secret_key not in str(exc)
                assert f"HTTP {status_code}" in str(exc)
            else:
                raise AssertionError(
                    f"HTTP {status_code} did not raise"
                )


async def test_gemini_network_failure_is_controlled() -> None:
    secret_key = "super-secret-api-key"

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "connection refused",
            request=request,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = GeminiProvider(
            secret_key,
            "gemini-3.1-flash-lite",
            client=client,
        )
        try:
            await provider.generate(_gemini_messages())
        except LLMProviderError as exc:
            assert secret_key not in str(exc)
            assert "request failed" in str(exc)
        else:
            raise AssertionError("Network failure did not raise")


async def test_gemini_invalid_response_is_controlled() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "completed", "steps": []},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = GeminiProvider(
            "secret-key",
            "gemini-3.1-flash-lite",
            client=client,
        )
        try:
            await provider.generate(_gemini_messages())
        except LLMProviderError as exc:
            assert "invalid response" in str(exc)
        else:
            raise AssertionError("Invalid response did not raise")


async def test_gemini_timeout_is_controlled() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = GeminiProvider(
            "secret-key",
            "gemini-3.1-flash-lite",
            client=client,
        )
        try:
            await provider.generate(_gemini_messages())
        except LLMProviderError as exc:
            assert "timed out" in str(exc)
        else:
            raise AssertionError("Timeout did not raise")


async def test_gemini_invalid_json_is_controlled() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not valid json")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = GeminiProvider(
            "secret-key",
            "gemini-3.1-flash-lite",
            client=client,
        )
        try:
            await provider.generate(_gemini_messages())
        except LLMProviderError as exc:
            assert "invalid JSON" in str(exc)
        else:
            raise AssertionError("Invalid JSON did not raise")


async def test_openai_http_status_matrix() -> None:
    secret_key = "super-secret-api-key"

    for status_code in (400, 402, 403, 429):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, json={"error": "failure"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAIProvider(
                secret_key,
                "test-model",
                client=client,
            )
            try:
                await provider.generate(
                    [{"role": "user", "content": "hello"}]
                )
            except LLMProviderError as exc:
                assert secret_key not in str(exc)
                assert f"HTTP {status_code}" in str(exc)
            else:
                raise AssertionError(
                    f"HTTP {status_code} did not raise"
                )


async def test_openai_network_failure_is_controlled() -> None:
    secret_key = "super-secret-api-key"

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            "connection refused",
            request=request,
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAIProvider(
            secret_key,
            "test-model",
            client=client,
        )
        try:
            await provider.generate(
                [{"role": "user", "content": "hello"}]
            )
        except LLMProviderError as exc:
            assert secret_key not in str(exc)
            assert "request failed" in str(exc)
        else:
            raise AssertionError("Network failure did not raise")


async def test_openai_invalid_response_is_controlled() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAIProvider(
            "secret-key",
            "test-model",
            client=client,
        )
        try:
            await provider.generate(
                [{"role": "user", "content": "hello"}]
            )
        except LLMProviderError as exc:
            assert "invalid response" in str(exc)
        else:
            raise AssertionError("Invalid response did not raise")


async def test_encryption_manager_integration() -> None:
    encrypted = "ciphertext-only"
    encryption = FakeEncryptionService("decrypted-key")
    registry = LLMProviderRegistry({"fake": FakeProvider})
    service = ConfiguredLLMService(encryption, registry)
    configuration = UserLLMConfiguration(
        provider="fake",
        model="test-model",
        encrypted_api_key=encrypted,
    )

    result = await service.generate(
        configuration,
        [{"role": "user", "content": "Analyze this"}],
    )
    assert result == "Analyze this"
    assert encryption.received_ciphertext == encrypted

    key = Fernet.generate_key()
    original_encryption_key = settings.ENCRYPTION_KEY
    settings.ENCRYPTION_KEY = key.decode()
    try:
        from app.security.encryption import EncryptionService

        real_encryption = EncryptionService()
        encrypted_api_key = real_encryption.encrypt("decrypted-key")
        real_service = ConfiguredLLMService(
            real_encryption,
            registry,
        )
        real_configuration = UserLLMConfiguration(
            provider="fake",
            model="test-model",
            encrypted_api_key=encrypted_api_key,
        )
        assert await real_service.generate(
            real_configuration,
            [{"role": "user", "content": "Real round trip"}],
        ) == "Real round trip"
    finally:
        settings.ENCRYPTION_KEY = original_encryption_key


async def test_prompt_and_analysis_messages() -> None:
    assert "AlphaMind AI" in ALPHAMIND_SYSTEM_PROMPT
    assert "Never fabricate" in ALPHAMIND_SYSTEM_PROMPT
    assert "guaranteed" in ALPHAMIND_SYSTEM_PROMPT

    messages = LLMAnalysisService().build_messages(
        question="What are the risks?",
        company={"ticker": "AAPL"},
        current_price={"price": 100},
    )
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == ALPHAMIND_SYSTEM_PROMPT
    assert messages[1]["role"] == "user"
    assert "AAPL" in messages[1]["content"]
    assert "What are the risks?" in messages[1]["content"]


async def test_model_registration_and_manager_flow() -> None:
    assert User.__table__ in Base.metadata.tables.values()
    assert UserLLMConfiguration.__table__ in Base.metadata.tables.values()
    assert UserLLMConfiguration.__mapper__.relationships["user"]
    assert User.__mapper__.relationships["llm_configuration"].uselist is False

    response = await LLMManager(
        FakeProvider("not-used", "test-model")
    ).generate(
        [{"role": "user", "content": "hello"}]
    )
    assert response == "hello"


async def main() -> None:
    await test_real_encryption_round_trip()
    await test_registry_and_unknown_provider()
    await test_openai_normalization_and_http_error()
    await test_openai_http_status_matrix()
    await test_openai_network_failure_is_controlled()
    await test_openai_invalid_response_is_controlled()
    await test_gemini_uses_system_instruction_and_string_input()
    await test_gemini_output_text_fallback()
    await test_gemini_http_errors_are_controlled()
    await test_gemini_network_failure_is_controlled()
    await test_gemini_invalid_response_is_controlled()
    await test_gemini_timeout_is_controlled()
    await test_gemini_invalid_json_is_controlled()
    await test_encryption_manager_integration()
    await test_prompt_and_analysis_messages()
    await test_model_registration_and_manager_flow()
    print("Sprint 2 LLM tests passed")


if __name__ == "__main__":
    asyncio.run(main())
