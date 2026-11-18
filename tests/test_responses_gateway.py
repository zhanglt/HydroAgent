"""Wire contract regressions without network or irrigation side effects."""
import unittest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from src.api import SettingsUpdateRequest, _should_reload_agent
from src.llm.langchain_agent import HydroChatOpenAI, HydroDeepAgent
from src.llm.tool_argument_parser import ParsedToolArguments


@tool
def read_status(zone_id: str) -> str:
    """Read a test zone status without any side effects."""
    return "unknown"


class TestResponsesPayload(unittest.TestCase):
    def model(self, **kwargs):
        return HydroChatOpenAI(model="gpt-6.1-sol", api_key="test-key", streaming=True, **kwargs)

    def test_responses_maps_both_system_instructions_without_mutating_messages(self):
        model = self.model(use_responses_api=True)
        messages = [SystemMessage(content="Safety instructions"), SystemMessage(content="Runtime context"), HumanMessage(content="Hello")]
        payload = model._get_request_payload(messages)
        self.assertEqual([item["role"] for item in payload["input"]], ["developer", "developer", "user"])
        self.assertEqual([item["content"] for item in payload["input"][:2]], ["Safety instructions", "Runtime context"])
        self.assertTrue(payload["stream"])
        self.assertNotIn("messages", payload)
        self.assertTrue(all(message.type == "system" for message in messages[:2]))

    def test_auto_responses_with_tools_also_maps_instructions(self):
        model = self.model()
        bound = model.bind_tools([read_status])
        payload = model._get_request_payload([SystemMessage(content="Read only"), HumanMessage(content="Hello")], **bound.kwargs)
        self.assertEqual(payload["input"][0]["role"], "developer")
        self.assertEqual(payload["tools"][0]["name"], "read_status")

    def test_chat_completions_preserves_system_and_deepseek_reasoning(self):
        model = self.model(use_responses_api=False)
        payload = model._get_request_payload([
            SystemMessage(content="Safety instructions"),
            AIMessage(content="Answer", additional_kwargs={"reasoning_content": "Prior reasoning"}),
            HumanMessage(content="Continue"),
        ])
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["reasoning_content"], "Prior reasoning")
        self.assertNotIn("input", payload)

    def test_tool_result_roundtrip_preserves_call_ids(self):
        model = self.model(use_responses_api=True)
        payload = model._get_request_payload([
            SystemMessage(content="Read only"), HumanMessage(content="Read the status"),
            AIMessage(content="", tool_calls=[{"name": "read_status", "args": {"zone_id": "zone_test"}, "id": "call_test"}]),
            ToolMessage(content="unknown", tool_call_id="call_test"),
        ])
        call = next(item for item in payload["input"] if item.get("type") == "function_call")
        result = next(item for item in payload["input"] if item.get("type") == "function_call_output")
        self.assertEqual(call["call_id"], "call_test")
        self.assertEqual(result["call_id"], "call_test")
        self.assertEqual(result["output"], "unknown")

    def test_structured_parser_uses_same_responses_contract(self):
        model = self.model(use_responses_api=True)
        structured = model.with_structured_output(ParsedToolArguments, method="function_calling")
        binding = structured.steps[0]
        payload = model._get_request_payload([SystemMessage(content="Parse safely"), HumanMessage(content="zone 1")], **binding.kwargs)
        self.assertEqual(payload["input"][0]["role"], "developer")
        self.assertEqual(payload["tools"][0]["name"], "ParsedToolArguments")

    def test_protocol_update_is_validated_and_reloads_agent(self):
        self.assertTrue(_should_reload_agent({"openai_wire_api": "responses"}))
        self.assertEqual(SettingsUpdateRequest(openai_wire_api="responses").openai_wire_api, "responses")
        with self.assertRaises(ValueError):
            SettingsUpdateRequest(openai_wire_api="invalid")


class TestAgentProtocolInitialization(unittest.IsolatedAsyncioTestCase):
    async def test_configured_protocol_applies_to_agent_and_parser(self):
        import tempfile
        from src.config import config
        agent = HydroDeepAgent()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(config, "OPENAI_WIRE_API", "responses"), \
             patch("src.llm.langchain_agent.get_hydro_persistence") as persistence, \
             patch("src.llm.langchain_agent.MultiServerMCPClient") as mcp:
            agent._workspace_root = directory
            persistence.return_value.initialize = AsyncMock()
            mcp.return_value.get_tools = AsyncMock(return_value=[])
            await agent.initialize()
            self.assertTrue(agent._llm.use_responses_api)
            self.assertIs(agent._parser_agent._llm, agent._llm)


class TestProtocolSettingsApi(unittest.TestCase):
    def test_setting_is_saved_as_yaml_and_triggers_reload(self):
        from test_console_performance import TestConsoleApi
        from src.config import config

        fixture = TestConsoleApi(methodName="test_permission_failures_are_not_empty_success")
        fixture.setUp()
        try:
            snapshot = {**config.get_yaml_settings(), "openai_wire_api": "responses"}
            with patch.object(config, "update_yaml_settings", return_value=snapshot) as save, \
                 patch("src.llm.langchain_agent.get_hydro_agent") as agent:
                agent.return_value.reload = AsyncMock()
                response = fixture.client.put("/api/settings", headers=fixture.headers, json={"openai_wire_api": "responses"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["settings"]["openai_wire_api"], "responses")
                self.assertTrue(response.json()["agent_reloaded"])
                save.assert_called_once_with({"openai_wire_api": "responses"})
                agent.return_value.reload.assert_awaited_once()
                invalid = fixture.client.put("/api/settings", headers=fixture.headers, json={"openai_wire_api": "invalid"})
                self.assertEqual(invalid.status_code, 422)
                self.assertEqual(save.call_count, 1)
        finally:
            fixture.tearDown()
