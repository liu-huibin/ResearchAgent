import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.agents import factory as agent_factory
from app.agents import graph as agent_graph
from app.agents import nodes as agent_nodes


class FakeAgent:
    def __init__(self, content: str):
        self.content = content

    async def ainvoke(self, _input, config=None):
        return {"messages": [AIMessage(content=self.content)]}


class FakeLLM:
    def __init__(self):
        self.calls = 0
        self.inputs = []

    async def ainvoke(self, _messages, config=None):
        self.calls += 1
        self.inputs.append(_messages)
        if config and config.get("metadata", {}).get("research_stage") == "revision":
            return AIMessage(content=(
                "修正后的三个科研思路\n"
                "<public_report>\n"
                "结论：已按审查意见修正方案。\n"
                "依据：ReviewerAgent 的修改要求。\n"
                "取舍：删除无证据断言。\n"
                "风险/不确定性：仍需实验验证。\n"
                "下一步：提交 Supervisor 汇总。\n"
                "</public_report>"
            ))
        return AIMessage(content="Supervisor 最终汇总")


class MultiAgentGraphTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        agent_graph.build_multi_agent_graph.cache_clear()
        agent_factory._reader_agent.cache_clear()
        agent_factory._ideation_agent.cache_clear()
        agent_factory._reviewer_agent.cache_clear()

    def tearDown(self):
        agent_graph.build_multi_agent_graph.cache_clear()
        agent_factory._reader_agent.cache_clear()
        agent_factory._ideation_agent.cache_clear()
        agent_factory._reviewer_agent.cache_clear()

    async def test_agent_factory_uses_langgraph_compatible_prompt_argument(self):
        fake_llm = object()
        with (
            patch.object(agent_factory, "get_llm", return_value=fake_llm),
            patch.object(
                agent_factory,
                "create_react_agent",
                return_value=object(),
            ) as create_agent,
        ):
            agent_factory._reader_agent()

        kwargs = create_agent.call_args.kwargs
        self.assertEqual(kwargs["state_modifier"], agent_factory.READER_SYSTEM_PROMPT)
        self.assertNotIn("prompt", kwargs)

    async def test_read_only_routes_directly_to_finalizer(self):
        fake_llm = FakeLLM()
        with (
            patch.object(
                agent_nodes,
                "_reader_agent",
                return_value=FakeAgent(
                    "论文方法总结 [citation:doc_7:chunk_3]\n"
                    "<public_report>\n"
                    "结论：论文采用对比学习。\n"
                    "依据：方法章节。\n"
                    "取舍：以正文为主。\n"
                    "风险/不确定性：未报告外部验证。\n"
                    "下一步：交由 Supervisor 汇总。\n"
                    "</public_report>"
                ),
            ),
            patch.object(
                agent_nodes,
                "_ideation_agent",
                side_effect=AssertionError("read_only 不应调用 IdeationAgent"),
            ),
            patch.object(
                agent_nodes,
                "_reviewer_agent",
                side_effect=AssertionError("read_only 不应调用 ReviewerAgent"),
            ),
            patch.object(agent_nodes, "get_llm", return_value=fake_llm),
        ):
            result = await agent_graph.build_multi_agent_graph().ainvoke(
                {
                    "user_message": "总结这篇论文的方法",
                    "document_text": "论文正文",
                    "iterations": 0,
                },
                config={"recursion_limit": 10},
            )

        self.assertEqual(result["workflow"], "read_only")
        self.assertEqual(
            result["reader_output"],
            "论文方法总结 [citation:doc_7:chunk_3]",
        )
        self.assertIn("结论：论文采用对比学习", result["reader_public_report"])
        self.assertNotIn("ideation_output", result)
        self.assertNotIn("review_output", result)
        self.assertEqual(
            result["final_output"],
            "Supervisor 最终汇总\n\n可定位来源：[citation:doc_7:chunk_3]",
        )
        self.assertIn(
            "[citation:doc_7:chunk_3]",
            fake_llm.inputs[-1][-1].content,
        )

    async def test_research_cycle_reviews_and_revises_once(self):
        fake_llm = FakeLLM()
        with (
            patch.object(
                agent_nodes,
                "_reader_agent",
                return_value=FakeAgent(
                    "ReaderAgent 论文总结\n"
                    "<public_report>\n结论：已提取论文约束。\n依据：论文正文。\n"
                    "取舍：排除无证据结论。\n风险/不确定性：样本有限。\n"
                    "下一步：生成候选方案。\n</public_report>"
                ),
            ),
            patch.object(
                agent_nodes,
                "_ideation_agent",
                return_value=FakeAgent(
                    "三个候选改进思路\n"
                    "<public_report>\n结论：形成三个可验证方案。\n依据：ReaderAgent 约束。\n"
                    "取舍：优先低风险方案。\n风险/不确定性：收益待验证。\n"
                    "下一步：ReviewerAgent 复核。\n</public_report>"
                ),
            ),
            patch.object(
                agent_nodes,
                "_reviewer_agent",
                return_value=FakeAgent(
                    "审查结论：需修改\n补充对照实验\n"
                    "<public_report>\n结论：候选方案需要修改。\n依据：缺少对照实验。\n"
                    "取舍：保留可证伪方案。\n风险/不确定性：效果证据不足。\n"
                    "下一步：补充实验设计。\n</public_report>"
                ),
            ),
            patch.object(agent_nodes, "get_llm", return_value=fake_llm),
        ):
            result = await agent_graph.build_multi_agent_graph().ainvoke(
                {
                    "user_message": "阅读这篇论文并提出 3 个改进思路",
                    "document_text": "论文正文",
                    "iterations": 0,
                },
                config={"recursion_limit": 10},
            )

        self.assertEqual(result["workflow"], "research_cycle")
        self.assertEqual(result["reader_output"], "ReaderAgent 论文总结")
        self.assertIn("已提取论文约束", result["reader_public_report"])
        self.assertEqual(result["ideation_output"], "三个候选改进思路")
        self.assertIn("需修改", result["review_output"])
        self.assertIn("需要修改", result["reviewer_public_report"])
        self.assertEqual(result["revision_output"], "修正后的三个科研思路")
        self.assertIn("删除无证据断言", result["revision_public_report"])
        self.assertEqual(result["final_output"], "Supervisor 最终汇总")
        self.assertEqual(fake_llm.calls, 2)
        finalizer_input = fake_llm.inputs[-1][-1].content
        self.assertNotIn("<public_report>", finalizer_input)
        self.assertNotIn("已提取论文约束", finalizer_input)

if __name__ == "__main__":
    unittest.main()
