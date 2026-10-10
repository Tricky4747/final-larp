import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import llm


class LLMProviderTests(unittest.TestCase):
    def test_gemini_is_default_even_when_apmix_key_is_configured(self):
        with patch.dict(
            os.environ,
            {
                "APMIX_API_KEY": "test-key",
                "GEMINI_API_KEY": "gemini-test",
            },
            clear=True,
        ):
            self.assertEqual(llm._provider(), "gemini")
            self.assertTrue(llm.is_configured())

    def test_provider_can_be_explicitly_set_to_gemini(self):
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "gemini",
                "APMIX_API_KEY": "test-key",
                "GEMINI_API_KEY": "gemini-test",
            },
            clear=True,
        ):
            self.assertEqual(llm._provider(), "gemini")
            self.assertTrue(llm.is_configured())

    def test_unconfigured_provider_returns_mock(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("llm.asyncio.sleep", new=AsyncMock()):
                result = asyncio.run(
                    llm.complete("system", "user", mock="offline")
                )
        self.assertEqual(result, "offline")

    def test_apmix_completion_uses_configured_model_and_messages(self):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="provider result"))
            ]
        )
        create = AsyncMock(return_value=response)
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "apmix",
                "APMIX_API_KEY": "test-key",
                "APMIX_BASE_URL": "https://api.apmix.ai/v1",
                "APMIX_MODEL": "claude-sonnet-4-6-free",
            },
            clear=True,
        ), patch("llm._get_apmix_client", return_value=fake_client):
            result = asyncio.run(
                llm.complete("system prompt", "user prompt", max_tokens=123)
            )

        self.assertEqual(result, "provider result")
        create.assert_awaited_once_with(
            model="claude-sonnet-4-6-free",
            messages=[
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "user prompt"},
            ],
            max_tokens=123,
        )

    def test_apmix_client_uses_configured_key_and_base_url(self):
        with patch.dict(
            os.environ,
            {
                "APMIX_API_KEY": "test-key",
                "APMIX_BASE_URL": "https://api.apmix.ai/v1/",
            },
            clear=True,
        ), patch("openai.AsyncOpenAI") as client_factory, patch.object(
            llm, "_apmix_client", None
        ):
            llm._get_apmix_client()

        client_factory.assert_called_once_with(
            api_key="test-key",
            base_url="https://api.apmix.ai/v1",
        )

    def test_unknown_provider_is_rejected(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "unknown"}, clear=True):
            with self.assertRaisesRegex(ValueError, "LLM_PROVIDER"):
                llm.is_configured()


if __name__ == "__main__":
    unittest.main()
