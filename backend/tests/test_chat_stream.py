import unittest
from datetime import datetime

from app.models.message import Message
from app.models.workflow_run import WorkflowRun
from app.services.chat.service import ChatContext
from app.services.chat.stream import stream_chat


class FakeStreamDatabase:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if isinstance(value, Message) and value.id is None:
                value.id = 41

    async def commit(self):
        self.commits += 1

    async def refresh(self, _value):
        return None

    async def execute(self, _query):
        class Result:
            def scalar_one_or_none(self):
                return None
        return Result()

    async def rollback(self):
        pass


class FakeSessionContext:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self.database

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


async def successful_workflow(**_kwargs):
    yield {
        "type": "agent",
        "agent": "ReaderAgent",
        "stage": "reader",
        "detail": "private stage injection",
    }
    yield {"type": "thought", "agent": "ReaderAgent", "content": "private reasoning"}
    yield {
        "type": "action",
        "agent": "ReaderAgent",
        "tool": "hybrid_retrieve",
        "input": {"query": "method"},
    }
    yield {
        "type": "observation",
        "agent": "ReaderAgent",
        "tool": "hybrid_retrieve",
        "output": "source",
        "is_error": False,
    }
    yield {
        "type": "report",
        "agent": "ReaderAgent",
        "stage": "reader",
        "content": "private raw report",
    }
    yield {
        "type": "report",
        "agent": "ReaderAgent",
        "stage": "reader",
        "content": (
            "结论：已定位论文方法。\n"
            "依据：正文方法章节。\n"
            "取舍：优先采用原文证据。\n"
            "风险/不确定性：实验设置仍需核查。\n"
            "下一步：交由 Supervisor 汇总。"
        ),
    }
    yield {"type": "token", "content": "答案"}
    yield {
        "type": "metrics",
        "trace_id": "00000000-0000-0000-0000-000000000007",
        "status": "completed",
        "total_tokens": 12,
        "duration_ms": 25,
    }


class ChatStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_stream_keeps_event_contract_and_persists_once(self):
        database = FakeStreamDatabase()
        context = ChatContext(
            session_id=7,
            user_message="总结方法",
            document_text=None,
            trace_id="00000000-0000-0000-0000-000000000007",
            started_at=datetime.now(),
        )

        chunks = [
            chunk
            async for chunk in stream_chat(
                context,
                session_factory=lambda: FakeSessionContext(database),
                workflow_runner=successful_workflow,
            )
        ]
        stream = "".join(chunks)

        expected_order = [
            "agent", "action", "observation", "report", "token", "metrics", "done"
        ]
        offsets = [stream.index(f"event: {event}\n") for event in expected_order]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn('"content": "答案"', stream)
        self.assertIn('"total_tokens": 12', stream)
        self.assertIn("当前依据：会话中没有可供分析的论文正文", stream)
        self.assertIn("结论：已定位论文方法", stream)
        self.assertNotIn("private reasoning", stream)
        self.assertNotIn("private stage injection", stream)
        self.assertNotIn("private raw report", stream)
        self.assertNotIn("method", stream)
        self.assertNotIn("source", stream)
        self.assertEqual(database.commits, 1)

        assistant = next(value for value in database.added if isinstance(value, Message))
        run = next(value for value in database.added if isinstance(value, WorkflowRun))
        self.assertEqual(assistant.content, "答案")
        self.assertIsNone(assistant.thought)
        stage = next(item for item in assistant.tool_calls if item["kind"] == "stage")
        tool = next(item for item in assistant.tool_calls if item["kind"] == "tool")
        self.assertEqual(stage["stage"], "reader")
        self.assertEqual(stage["status"], "succeeded")
        self.assertIn("知识库检索作为证据入口", stage["detail"])
        self.assertIn("实验设置仍需核查", stage["report"])
        self.assertEqual(tool["status"], "succeeded")
        self.assertNotIn("input", tool)
        self.assertNotIn("output", tool)
        self.assertEqual(run.assistant_message_id, 41)
        self.assertEqual(run.total_tokens, 12)


if __name__ == "__main__":
    unittest.main()
