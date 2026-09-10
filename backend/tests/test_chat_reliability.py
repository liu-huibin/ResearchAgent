"""Fault injection over real isolated SQLite transactions (no live histories)."""
import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import anyio
from starlette.responses import StreamingResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlmodel import SQLModel, select

from app.models.message import Message
from app.models.session import Session
from app.models.workflow_run import WorkflowRun
from app.services.chat.service import ChatContext, WorkflowResult, persist_workflow_result, prepare_chat, recover_stale_runs
from app.services.chat.stream import stream_chat


class Database:
    def __init__(self, factory):
        self.factory = factory
        self.session = OrmSession(factory.engine, expire_on_commit=False)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.session.close()

    def add(self, obj):
        self.session.add(obj)

    async def execute(self, query):
        return self.session.execute(query)

    async def get(self, *args):
        return self.session.get(*args)

    async def flush(self):
        self.factory.fail('flush')
        self.session.flush()

    async def commit(self):
        await asyncio.sleep(0)  # Cancellation checkpoint, like a real driver.
        self.factory.fail('commit')
        self.session.commit()
        self.factory.fail('ack')  # Commit succeeded but acknowledgement lost.

    async def rollback(self):
        self.session.rollback()


class Factory:
    def __init__(self):
        self.engine = create_engine('sqlite://')
        SQLModel.metadata.create_all(self.engine)
        with OrmSession(self.engine) as db:
            db.add_all([Session(id=1), Session(id=2)])
            db.commit()
        self.failure = None
        self.always_fail = False

    def fail(self, stage):
        if self.failure == stage:
            if not self.always_fail:
                self.failure = None
            raise RuntimeError('injected storage failure')

    def __call__(self):
        return Database(self)

    def records(self, model):
        with OrmSession(self.engine) as db:
            return list(db.scalars(select(model)).all())


def context(session_id=1):
    return ChatContext(session_id, 'question', None, f'00000000-0000-0000-0000-{session_id:012}', datetime.now())


async def answer(**kwargs):
    yield {'type': 'token', 'content': 'partial answer'}
    yield {'type': 'metrics', 'status': 'completed'}


class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Factory()

    def tearDown(self):
        self.db.engine.dispose()

    async def collect(self, workflow=answer, ctx=None):
        return ''.join([frame async for frame in stream_chat(ctx or context(), self.db, workflow)])

    async def test_flush_commit_and_uncertain_commit_retry_without_duplicates(self):
        for stage in ('flush', 'commit', 'ack'):
            with self.subTest(stage=stage):
                self.db.failure = stage
                ctx = context({'flush': 1, 'commit': 2, 'ack': 1}[stage])
                ctx = ChatContext(ctx.session_id, ctx.user_message, None, stage, ctx.started_at)
                frames = await self.collect(ctx=ctx)
                self.assertIn('event: done', frames)
                self.assertEqual(len([r for r in self.db.records(WorkflowRun) if r.trace_id == stage]), 1)
        self.assertEqual(len(self.db.records(Message)), 3)

    async def test_event_error_overrides_completed_metrics_and_terminates_tools(self):
        async def failure(**kwargs):
            yield {'type': 'action', 'tool': 'read'}
            yield {'type': 'error', 'content': 'private exception'}
            yield {'type': 'metrics', 'status': 'completed'}
        frames = await self.collect(failure)
        self.assertNotIn('private exception', frames)
        self.assertEqual(self.db.records(WorkflowRun)[0].status, 'error')
        self.assertEqual(self.db.records(Message)[0].tool_calls[0]['status'], 'failed')

    async def test_runner_exception_keeps_partial(self):
        async def failure(**kwargs):
            yield {'type': 'token', 'content': 'partial'}
            raise RuntimeError('private')
        frames = await self.collect(failure)
        self.assertIn('event: done', frames)
        self.assertEqual(self.db.records(Message)[0].content, 'partial')
        self.assertEqual(self.db.records(WorkflowRun)[0].status, 'error')

    async def test_generator_close_saves_and_closes_producer(self):
        closed = []
        async def workflow(**kwargs):
            try:
                yield {'type': 'token', 'content': 'partial'}
                await asyncio.sleep(60)
            finally:
                closed.append(True)
        generator = stream_chat(context(), self.db, workflow)
        await anext(generator)  # start
        await anext(generator)  # token
        await generator.aclose()
        self.assertTrue(closed)
        self.assertEqual(self.db.records(WorkflowRun)[0].status, 'cancelled')

    async def test_anyio_disconnect_shields_persistence(self):
        received = anyio.Event()
        closed = []
        async def workflow(**kwargs):
            try:
                yield {'type': 'token', 'content': 'partial'}
                await asyncio.sleep(60)
            finally:
                closed.append(True)
        async def consume():
            async for frame in stream_chat(context(), self.db, workflow):
                if 'event: token' in frame:
                    received.set()
        async with anyio.create_task_group() as group:
            group.start_soon(consume)
            await received.wait()
            group.cancel_scope.cancel()
        self.assertTrue(closed)
        self.assertEqual(self.db.records(Message)[0].content, 'partial')
        self.assertEqual(self.db.records(WorkflowRun)[0].status, 'cancelled')

    async def test_real_asgi_disconnect_saves_partial(self):
        token_sent = asyncio.Event()
        async def workflow(**kwargs):
            yield {'type': 'token', 'content': 'ASGI partial'}
            await asyncio.sleep(60)
        async def send(message):
            if b'event: token' in message.get('body', b''):
                token_sent.set()
        async def receive():
            await token_sent.wait()
            return {'type': 'http.disconnect'}
        response = StreamingResponse(stream_chat(context(), self.db, workflow))
        await response({'type': 'http', 'asgi': {'spec_version': '2.0'}}, receive, send)
        self.assertEqual(self.db.records(Message)[0].content, 'ASGI partial')
        self.assertEqual(self.db.records(WorkflowRun)[0].status, 'cancelled')

    async def test_database_outage_never_claims_done(self):
        self.db.failure, self.db.always_fail = 'commit', True
        frames = await self.collect()
        self.assertNotIn('event: done', frames)
        self.assertIn('保存失败', frames)
        self.assertEqual(self.db.records(Message), [])

    async def test_parallel_sessions_do_not_cross_contaminate(self):
        await asyncio.gather(self.collect(ctx=context(1)), self.collect(ctx=context(2)))
        self.assertEqual({r.session_id for r in self.db.records(WorkflowRun)}, {1, 2})

    async def test_checkpoint_then_finalize_updates_same_message(self):
        with patch('app.services.chat.stream.CHECKPOINT_SECONDS', 0):
            await self.collect()
        self.assertEqual(len(self.db.records(Message)), 1)
        self.assertEqual(self.db.records(Message)[0].content, 'partial answer')
        self.assertEqual(self.db.records(WorkflowRun)[0].status, 'completed')

    async def test_heartbeat_during_silent_workflow(self):
        async def silent(**kwargs):
            await asyncio.sleep(.04)
            yield {'type': 'token', 'content': 'answer'}
        with patch('app.services.chat.stream.HEARTBEAT_SECONDS', .01):
            frames = await self.collect(silent)
        self.assertIn(': keepalive', frames)

    async def test_prepare_and_recover_process_kill(self):
        async with self.db() as db:
            ctx = await prepare_chat(db, 1, '请帮我总结论文方法和实验')
        self.assertEqual(self.db.records(Session)[0].title, '总结论文方法和实验')
        self.assertEqual(self.db.records(WorkflowRun)[0].status, 'running')
        async with self.db() as db:
            old = ChatContext(1, 'question', None, ctx.trace_id, datetime.now() - timedelta(hours=1))
            await persist_workflow_result(db, old, WorkflowResult(content_parts=['checkpoint']), 'running')
        async with self.db() as db:
            await recover_stale_runs(db, 1)
        run = self.db.records(WorkflowRun)[0]
        self.assertEqual(run.status, 'interrupted')
        self.assertEqual(len(self.db.records(Message)), 2)
        self.assertEqual(self.db.records(Message)[1].content, 'checkpoint')
