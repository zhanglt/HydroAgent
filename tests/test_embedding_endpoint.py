"""Independent embedding endpoints without external network requests."""
import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from openai import OpenAI

from src.config import config
from src.knowledge.service import KnowledgeBaseService


class TestEmbeddingRequests(unittest.TestCase):
    def test_embedding_sdk_uses_independent_url_key_and_model(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={
                "object": "list", "model": "test-embedding", "usage": {"prompt_tokens": 1, "total_tokens": 1},
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
            })

        service = KnowledgeBaseService.__new__(KnowledgeBaseService)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client, \
             patch.object(config, "EMBEDDING_BASE_URL", "https://vectors.example/v1"), \
             patch.object(config, "OPENAI_BASE_URL", "https://chat.example/openai"), \
             patch.object(config, "EMBEDDING_API_KEY", "embedding-test-key"), \
             patch.object(config, "OPENAI_API_KEY", "chat-test-key"), \
             patch.object(config, "EMBEDDING_MODEL_NAME", "test-embedding"), \
             patch("openai.OpenAI", side_effect=lambda **kwargs: OpenAI(http_client=client, **kwargs)):
            self.assertEqual(service._embed_texts(["document"]), [[0.1, 0.2]])
            self.assertEqual(service._embed_texts(["query"]), [[0.1, 0.2]])
        self.assertEqual(len(requests), 2)
        for request in requests:
            self.assertEqual(str(request.url), "https://vectors.example/v1/embeddings")
            self.assertEqual(request.headers["authorization"], "Bearer embedding-test-key")
            self.assertEqual(json.loads(request.content)["model"], "test-embedding")

    def test_missing_embedding_url_keeps_chat_endpoint_fallback(self):
        service = KnowledgeBaseService.__new__(KnowledgeBaseService)
        with patch.object(config, "EMBEDDING_BASE_URL", None), \
             patch.object(config, "OPENAI_BASE_URL", "https://chat.example/v1"), \
             patch.object(config, "EMBEDDING_API_KEY", None), \
             patch.object(config, "OPENAI_API_KEY", "test-chat-key"), \
             patch("openai.OpenAI") as sdk:
            sdk.return_value.embeddings.create.return_value.data = []
            self.assertEqual(service._embed_texts(["text"]), [])
            sdk.assert_called_once_with(api_key="test-chat-key", base_url="https://chat.example/v1")


class TestEmbeddingSettingsApi(unittest.TestCase):
    def setUp(self):
        from test_console_performance import TestConsoleApi
        self.fixture = TestConsoleApi(methodName="test_permission_failures_are_not_empty_success")
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_model_lists_use_selected_provider_and_credentials(self):
        upstream = Mock(ok=True, headers={"content-type": "application/json"})
        upstream.json.return_value = {"data": [{"id": "test-model"}]}
        with patch.object(config, "EMBEDDING_BASE_URL", "https://vectors.example/v1"), \
             patch.object(config, "OPENAI_BASE_URL", "https://chat.example/openai"), \
             patch.object(config, "EMBEDDING_API_KEY", "embedding-test-key"), \
             patch.object(config, "OPENAI_API_KEY", "chat-test-key"), \
             patch("requests.get", return_value=upstream) as fetch:
            for target, base, key in [
                ("embedding", "https://vectors.example/v1", "embedding-test-key"),
                ("chat", "https://chat.example/openai", "chat-test-key"),
            ]:
                response = self.fixture.client.get(f"/api/settings/openai-models?target={target}", headers=self.fixture.headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(fetch.call_args.args[0], base + "/models")
                self.assertEqual(fetch.call_args.kwargs["headers"]["Authorization"], "Bearer " + key)
            invalid = self.fixture.client.get("/api/settings/openai-models?target=invalid", headers=self.fixture.headers)
            self.assertEqual(invalid.status_code, 422)
            with patch.object(config, "EMBEDDING_BASE_URL", None), patch.object(config, "EMBEDDING_API_KEY", None):
                response = self.fixture.client.get("/api/settings/openai-models?target=embedding", headers=self.fixture.headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(fetch.call_args.args[0], "https://chat.example/openai/models")
                self.assertEqual(fetch.call_args.kwargs["headers"]["Authorization"], "Bearer chat-test-key")

    def test_embedding_url_is_saved_as_yaml_and_reloads_agent(self):
        snapshot = {**config.get_yaml_settings(), "embedding_base_url": "https://vectors.example/v1"}
        with patch.object(config, "update_yaml_settings", return_value=snapshot) as save, \
             patch("src.llm.langchain_agent.get_hydro_agent") as agent:
            agent.return_value.reload = AsyncMock()
            response = self.fixture.client.put("/api/settings", headers=self.fixture.headers, json={"embedding_base_url": "https://vectors.example/v1"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["settings"]["embedding_base_url"], "https://vectors.example/v1")
            save.assert_called_once_with({"embedding_base_url": "https://vectors.example/v1"})
            agent.return_value.reload.assert_awaited_once()
