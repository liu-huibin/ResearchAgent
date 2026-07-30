import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.services import agent as agent_service


class FakeAgent:
    def __init__(self, content: str):
        self.content = content

    async def ainvoke(self, _input, config=None):
        return {"messages": [AIMessage(content=self.content)]}


class FakeLLM:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, _messages, config=None):
        self.calls += 1
        if config and config.get("metadata", {}).get("research_stage") == "revision":
            return AIMessage(content="修正后的三个科研思路")
        return AIMessage(content="Supervisor 最终汇总")


class MultiAgentGraphTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        agent_service.build_multi_agent_graph.cache_clear()
        agent_service._reader_agent.cache_clear()
        agent_service._ideation_agent.cache_clear()
        agent_service._reviewer_agent.cache_clear()

    def tearDown(self):
        agent_service.build_multi_agent_graph.cache_clear()
        agent_service._reader_agent.cache_clear()
        agent_service._ideation_agent.cache_clear()
        agent_service._reviewer_agent.cache_clear()

    async def test_agent_factory_uses_langgraph_compatible_prompt_argument(self):
        fake_llm = object()
        with (
            patch.object(agent_service, "get_llm", return_value=fake_llm),
            patch.object(
                agent_service,
                "create_react_agent",
                return_value=object(),
            ) as create_agent,
        ):
            agent_service._reader_agent()

        kwargs = create_agent.call_args.kwargs
        self.assertEqual(kwargs["state_modifier"], agent_service.READER_SYSTEM_PROMPT)
        self.assertNotIn("prompt", kwargs)

    async def test_read_only_routes_directly_to_finalizer(self):
        fake_llm = FakeLLM()
        with (
            patch.object(
                agent_service,
                "_reader_agent",
                return_value=FakeAgent("论文方法总结"),
            ),
            patch.object(
                agent_service,
                "_ideation_agent",
                side_effect=AssertionError("read_only 不应调用 IdeationAgent"),
            ),
            patch.object(
                agent_service,
                "_reviewer_agent",
                side_effect=AssertionError("read_only 不应调用 ReviewerAgent"),
            ),
            patch.object(agent_service, "get_llm", return_value=fake_llm),
        ):
            result = await agent_service.build_multi_agent_graph().ainvoke(
                {
                    "user_message": "总结这篇论文的方法",
                    "document_text": "论文正文",
                    "iterations": 0,
                },
                config={"recursion_limit": 10},
            )

        self.assertEqual(result["workflow"], "read_only")
        self.assertEqual(result["reader_output"], "论文方法总结")
        self.assertNotIn("ideation_output", result)
        self.assertNotIn("review_output", result)
        self.assertEqual(result["final_output"], "Supervisor 最终汇总")

    async def test_research_cycle_reviews_and_revises_once(self):
        fake_llm = FakeLLM()
        with (
            patch.object(
                agent_service,
                "_reader_agent",
                return_value=FakeAgent("ReaderAgent 论文总结"),
            ),
            patch.object(
                agent_service,
                "_ideation_agent",
                return_value=FakeAgent("三个候选改进思路"),
            ),
            patch.object(
                agent_service,
                "_reviewer_agent",
                return_value=FakeAgent("审查结论：需修改\n补充对照实验"),
            ),
            patch.object(agent_service, "get_llm", return_value=fake_llm),
        ):
            result = await agent_service.build_multi_agent_graph().ainvoke(
                {
                    "user_message": "阅读这篇论文并提出 3 个改进思路",
                    "document_text": "论文正文",
                    "iterations": 0,
                },
                config={"recursion_limit": 10},
            )

        self.assertEqual(result["workflow"], "research_cycle")
        self.assertEqual(result["reader_output"], "ReaderAgent 论文总结")
        self.assertEqual(result["ideation_output"], "三个候选改进思路")
        self.assertIn("需修改", result["review_output"])
        self.assertEqual(result["revision_output"], "修正后的三个科研思路")
        self.assertEqual(result["final_output"], "Supervisor 最终汇总")
        self.assertEqual(fake_llm.calls, 2)


if __name__ == "__main__":
    unittest.main()
