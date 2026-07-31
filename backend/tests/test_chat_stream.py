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


class FakeSessionContext:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self.database

    async def __aexit__(self, _exc_type, _exc, _traceback):
        return False


async def successful_workflow(**_kwargs):
    yield {"type": "agent", "agent": "ReaderAgent", "stage": "reader"}
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

        expected_order = ["agent", "action", "observation", "token", "metrics", "done"]
        offsets = [stream.index(f"event: {event}\n") for event in expected_order]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn('"content": "答案"', stream)
        self.assertIn('"total_tokens": 12', stream)
        self.assertEqual(database.commits, 1)

        assistant = next(value for value in database.added if isinstance(value, Message))
        run = next(value for value in database.added if isinstance(value, WorkflowRun))
        self.assertEqual(assistant.content, "答案")
        self.assertEqual(assistant.tool_calls[0]["output"], "source")
        self.assertEqual(run.assistant_message_id, 41)
        self.assertEqual(run.total_tokens, 12)


if __name__ == "__main__":
    unittest.main()
