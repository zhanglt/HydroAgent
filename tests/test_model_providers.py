"""Provider selection, persistence, and native Ollama wire contracts."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import yaml

from src.config import config
from src.config.config import Config
from src.knowledge.service import KnowledgeBaseError, KnowledgeBaseService
from src.llm.langchain_agent import HydroChatOpenAI
from langchain_core.messages import HumanMessage


class TestModelProviders(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "config.yaml"
        self.payload = {
            "llm_model": {
                "openai": {"openai_api_key": "chat-key", "openai_base_url": "https://chat.example/openai",
                           "openai_wire_api": "responses", "model_name": "gpt-6.1-sol"},
                "minimax": {"minimax_api_key": "minimax-key", "minimax_base_url": "https://mini.example/v1",
                            "model_name": "MiniMax-M2.5"},
            },
            "embedding_model": {"ollam": {"embedding_base_url": "http://localhost:11434", "embedding_model_name": "bge-m3:latest"}},
            "knowledge_base": {"top_k": 4},
            "proxy": "http://10.0.0.8:30000",
        }

    def load(self):
        self.path.write_text(yaml.safe_dump(self.payload, sort_keys=False))
        return Config(str(self.path), env_file_path=str(self.path.parent / "absent.env"))

    def test_user_structure_loads_and_snapshot_masks_secrets(self):
        settings = self.load()
        self.assertEqual(settings.LLM_PROVIDER, "openai")
        self.assertEqual(settings.OPENAI_WIRE_API, "responses")
        self.assertEqual(settings.MODEL_NAME, "gpt-6.1-sol")
        self.assertEqual(settings.EMBEDDING_PROVIDER, "ollama")
        self.assertIsNone(settings.EMBEDDING_API_KEY)
        self.assertNotIn("chat-key", str(settings.get_yaml_settings()))

    def test_switch_provider_preserves_other_blocks_and_reload(self):
        settings = self.load()
        snapshot = settings.update_yaml_settings({"llm_provider": "minimax", "model_name": "MiniMax-custom", "openai_api_key": "new-mini-key"})
        self.assertEqual(snapshot["llm_provider"], "minimax")
        self.assertEqual(settings.OPENAI_WIRE_API, "chat_completions")
        saved = yaml.safe_load(self.path.read_text())
        self.assertEqual(saved["llm_model"]["openai"], self.payload["llm_model"]["openai"])
        self.assertEqual(saved["llm_model"]["minimax"]["minimax_api_key"], "new-mini-key")
        self.assertNotIn("model_name", saved)
        reloaded = Config(str(self.path), env_file_path=str(self.path.parent / "absent.env"))
        self.assertEqual(reloaded.MODEL_NAME, "MiniMax-custom")
        self.assertEqual(reloaded.OPENAI_API_KEY, "new-mini-key")
        model = HydroChatOpenAI(model=reloaded.MODEL_NAME, api_key=reloaded.OPENAI_API_KEY,
                               base_url=reloaded.OPENAI_BASE_URL, use_responses_api=False)
        payload = model._get_request_payload([HumanMessage(content="Hello")])
        self.assertEqual(payload["model"], "MiniMax-custom")
        self.assertIn("messages", payload)
        settings.update_yaml_settings({"llm_provider": "openai"})
        self.assertEqual(settings.OPENAI_API_KEY, "chat-key")

    def test_nested_update_writes_active_embedding_block(self):
        settings = self.load()
        settings.update_yaml_settings({"embedding_provider": "ollama", "embedding_model_name": "other-model"})
        saved = yaml.safe_load(self.path.read_text())
        self.assertEqual(saved["embedding_model"]["ollam"]["embedding_model_name"], "other-model")
        self.assertEqual(saved["llm_model"], self.payload["llm_model"])
        self.assertEqual(saved["knowledge_base"], self.payload["knowledge_base"])

    def test_invalid_provider_is_atomic(self):
        settings = self.load()
        before = self.path.read_text()
        with self.assertRaises(ValueError):
            settings.update_yaml_settings({"llm_provider": "invalid", "model_name": "changed"})
        self.assertEqual(self.path.read_text(), before)
        self.assertEqual(settings.MODEL_NAME, "gpt-6.1-sol")

    def test_only_configured_minimax_is_inferred(self):
        self.payload["llm_model"]["openai"] = {"model_name": None}
        self.assertEqual(self.load().LLM_PROVIDER, "minimax")

    def test_provider_specific_environment_secret(self):
        os.environ["MINIMAX_API_KEY"] = "env-mini-key"
        self.payload["llm_model"]["provider"] = "minimax"
        self.assertEqual(self.load().OPENAI_API_KEY, "env-mini-key")

    def test_external_secret_survives_reload_and_other_provider_selection(self):
        os.environ["OPENAI_API_KEY"] = "external-openai-key"
        settings = self.load()
        self.assertEqual(settings.OPENAI_API_KEY, "external-openai-key")
        reloaded = Config(str(self.path), env_file_path=str(self.path.parent / "absent.env"))
        self.assertEqual(reloaded.OPENAI_API_KEY, "external-openai-key")
        settings.update_yaml_settings({"llm_provider": "minimax"})
        self.assertEqual(settings.OPENAI_API_KEY, "minimax-key")
        self.assertEqual(os.environ["OPENAI_API_KEY"], "external-openai-key")
        settings.update_yaml_settings({"llm_provider": "openai"})
        self.assertEqual(settings.OPENAI_API_KEY, "external-openai-key")

    def test_legacy_migration_keeps_model_and_credentials(self):
        self.payload = {"model_name": "old", "openai_api_key": "old-key", "embedding_model_name": "old-embedding"}
        settings = self.load()
        settings.update_yaml_settings({"llm_provider": "minimax", "openai_api_key": "mini-key"})
        settings.update_yaml_settings({"llm_provider": "openai"})
        self.assertEqual(settings.MODEL_NAME, "old")
        self.assertEqual(settings.OPENAI_API_KEY, "old-key")


class TestOllamaEmbeddings(unittest.TestCase):
    def test_native_endpoint_batches_documents_and_queries_without_chat_key(self):
        captured = []

        def handler(request):
            captured.append(request)
            body = json.loads(request.content)
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2] for _ in body["input"]]})

        service = KnowledgeBaseService.__new__(KnowledgeBaseService)
        with patch("httpx.Client", return_value=httpx.Client(transport=httpx.MockTransport(handler))) as factory, \
             patch.object(config, "EMBEDDING_PROVIDER", "ollama"), \
             patch.object(config, "EMBEDDING_BASE_URL", "http://localhost:11434/"), \
             patch.object(config, "EMBEDDING_MODEL_NAME", "bge-m3:latest"), \
             patch.object(config, "EMBEDDING_API_KEY", None), \
             patch.object(config, "OPENAI_API_KEY", "chat-secret"):
            self.assertEqual(len(service._embed_texts(["doc"] * 33)), 33)
        factory.assert_called_once()
        self.assertEqual(len(captured), 2)
        self.assertEqual(str(captured[0].url), "http://localhost:11434/api/embed")
        self.assertNotIn("authorization", captured[0].headers)
        self.assertEqual(json.loads(captured[0].content)["model"], "bge-m3:latest")

    def test_incomplete_vectors_are_rejected(self):
        service = KnowledgeBaseService.__new__(KnowledgeBaseService)
        client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"embeddings": []})))
        with patch("httpx.Client", return_value=client), \
             patch.object(config, "EMBEDDING_PROVIDER", "ollama"), \
             patch.object(config, "EMBEDDING_API_KEY", None):
            with self.assertRaises(KnowledgeBaseError):
                service._embed_texts(["document"])
