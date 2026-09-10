import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agents import runner


class Graph:
    def __init__(self, mode):
        self.mode = mode

    async def astream_events(self, *args, **kwargs):
        if self.mode == 'timeout':
            await asyncio.sleep(60)
        elif self.mode == 'iteration_limit':
            raise RuntimeError('recursion limit reached')
        elif self.mode == 'error':
            raise RuntimeError('private model failure')
        elif self.mode == 'finalize':
            yield {
                'event': 'on_chat_model_stream',
                'metadata': {'langgraph_node': 'finalize'},
                'data': {'chunk': SimpleNamespace(content='回答见 [Sec. 2.3]。')},
            }
            yield {
                'event': 'on_chain_end',
                'metadata': {'langgraph_node': 'finalize'},
                'data': {
                    'output': {
                        'final_output': (
                            '回答见 [Sec. 2.3]。\n\n'
                            '可定位来源：[citation:doc_7:chunk_3]'
                        ),
                    }
                },
            }
        elif self.mode == 'report':
            yield {
                'event': 'on_chain_start',
                'metadata': {'langgraph_node': 'reader'},
                'data': {},
            }
            yield {
                'event': 'on_chain_end',
                'metadata': {'langgraph_node': 'reader'},
                'data': {
                    'output': {
                        'reader_output': 'private full analysis',
                        'reader_public_report': (
                            '结论：识别出主要方法。\n'
                            '依据：论文方法章节。\n'
                            '下一步：交由 Supervisor 汇总。'
                        ),
                    }
                },
            }
        else:
            yield {'event': 'on_tool_end', 'name': 'hybrid_retrieve',
                   'data': {'output': '混合检索失败: private error'}}


class RunnerLimitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tracing = patch.object(runner.settings, 'langsmith_tracing', False)
        self.tracing.start()
        self.addCleanup(self.tracing.stop)

    async def test_timeout_iteration_limit_and_model_error(self):
        for status in ('timeout', 'iteration_limit', 'error'):
            with self.subTest(status=status), \
                 patch.object(runner, 'build_multi_agent_graph', return_value=Graph(status)), \
                 patch.object(runner.settings, 'agent_timeout_seconds', .01):
                events = [e async for e in runner.run_multi_agent_workflow('test')]
                self.assertEqual(events[-1]['type'], 'metrics')
                self.assertEqual(events[-1]['status'], status)
                self.assertNotIn('private model failure', str(events))

    async def test_retrieval_string_failure_is_counted_and_sanitized(self):
        with patch.object(runner, 'build_multi_agent_graph', return_value=Graph('tool')):
            events = [e async for e in runner.run_multi_agent_workflow('test')]
        self.assertTrue(events[0]['is_error'])
        self.assertEqual(events[-1]['tool_failures'], 1)
        self.assertNotIn('private error', str(events))

    async def test_only_explicit_public_report_is_emitted_for_agent_output(self):
        with patch.object(runner, 'build_multi_agent_graph', return_value=Graph('report')):
            events = [e async for e in runner.run_multi_agent_workflow('test')]

        report = next(event for event in events if event['type'] == 'report')
        self.assertEqual(report['agent'], 'ReaderAgent')
        self.assertIn('结论：识别出主要方法', report['content'])
        self.assertNotIn('private full analysis', str(events))

    async def test_finalizer_citation_correction_is_streamed_after_model_tokens(self):
        with patch.object(runner, 'build_multi_agent_graph', return_value=Graph('finalize')):
            events = [e async for e in runner.run_multi_agent_workflow('test')]

        content = ''.join(
            event['content'] for event in events if event['type'] == 'token'
        )
        self.assertEqual(
            content,
            '回答见 [Sec. 2.3]。\n\n可定位来源：[citation:doc_7:chunk_3]',
        )
