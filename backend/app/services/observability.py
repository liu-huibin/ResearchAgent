import json
import logging
import threading
import time
from collections import defaultdict
from functools import lru_cache
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from app.config import settings

logger = logging.getLogger(__name__)


def _empty_usage() -> dict[str, int]:
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def _normalize_usage(raw: dict[str, Any] | None) -> dict[str, int]:
    raw = raw or {}
    input_tokens = int(raw.get("input_tokens", raw.get("prompt_tokens", 0)) or 0)
    output_tokens = int(raw.get("output_tokens", raw.get("completion_tokens", 0)) or 0)
    total_tokens = int(raw.get("total_tokens", input_tokens + output_tokens) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _extract_usage(response: Any) -> tuple[dict[str, int], str]:
    model_name = "unknown"
    for generations in getattr(response, "generations", []) or []:
        for generation in generations:
            message = getattr(generation, "message", None)
            if message is None:
                continue
            metadata = getattr(message, "response_metadata", {}) or {}
            model_name = str(metadata.get("model_name") or metadata.get("model") or model_name)
            usage = getattr(message, "usage_metadata", None)
            if usage:
                return _normalize_usage(dict(usage)), model_name
            token_usage = metadata.get("token_usage") or metadata.get("usage")
            if token_usage:
                return _normalize_usage(dict(token_usage)), model_name

    llm_output = getattr(response, "llm_output", None) or {}
    model_name = str(llm_output.get("model_name") or model_name)
    return _normalize_usage(llm_output.get("token_usage")), model_name


class WorkflowMetricsCallback(BaseCallbackHandler):
    """Attribute LLM token usage and latency to the active ResearchMate agent."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._runs: dict[str, tuple[str, float]] = {}
        self._usage: dict[str, dict[str, int]] = defaultdict(_empty_usage)
        self._models: dict[str, set[str]] = defaultdict(set)
        self._llm_failures: dict[str, int] = defaultdict(int)
        self._llm_latency_ms: dict[str, int] = defaultdict(int)

    def _start(self, run_id: Any, metadata: dict[str, Any] | None) -> None:
        agent = str((metadata or {}).get("research_agent") or "Unknown")
        with self._lock:
            self._runs[str(run_id)] = (agent, time.perf_counter())

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: Any,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._start(run_id, metadata)

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: Any,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._start(run_id, metadata)

    def on_llm_end(self, response: Any, *, run_id: Any, **kwargs: Any) -> None:
        usage, model_name = _extract_usage(response)
        with self._lock:
            agent, started_at = self._runs.pop(
                str(run_id), ("Unknown", time.perf_counter())
            )
            target = self._usage[agent]
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                target[key] += usage[key]
            if model_name != "unknown":
                self._models[agent].add(model_name)
            self._llm_latency_ms[agent] += int(
                (time.perf_counter() - started_at) * 1000
            )

    def on_llm_error(self, error: BaseException, *, run_id: Any, **kwargs: Any) -> None:
        with self._lock:
            agent, started_at = self._runs.pop(
                str(run_id), ("Unknown", time.perf_counter())
            )
            self._llm_failures[agent] += 1
            self._llm_latency_ms[agent] += int(
                (time.perf_counter() - started_at) * 1000
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            agents = set(self._usage) | set(self._llm_failures) | set(self._llm_latency_ms)
            return {
                agent: {
                    **dict(self._usage[agent]),
                    "llm_calls_failed": self._llm_failures[agent],
                    "llm_latency_ms": self._llm_latency_ms[agent],
                    "models": sorted(self._models[agent]),
                }
                for agent in sorted(agents)
            }


@lru_cache(maxsize=1)
def _get_langsmith_tracer() -> Any | None:
    if not settings.langsmith_tracing:
        return None
    try:
        from langchain_core.tracers.langchain import LangChainTracer
        from langsmith import Client

        client = Client(
            api_url=settings.langsmith_endpoint,
            api_key=settings.langsmith_api_key or None,
        )
        return LangChainTracer(
            project_name=settings.langsmith_project,
            client=client,
            tags=["researchmate", "phase-5"],
        )
    except Exception:
        logger.exception(
            "LangSmith tracing could not be initialized; local metrics remain enabled"
        )
        return None


def create_workflow_callbacks() -> tuple[WorkflowMetricsCallback, list[Any], bool]:
    metrics = WorkflowMetricsCallback()
    callbacks: list[Any] = [metrics]
    tracer = _get_langsmith_tracer()
    if tracer is not None:
        callbacks.append(tracer)
    return metrics, callbacks, tracer is not None


def summarize_agent_usage(agent_usage: dict[str, Any]) -> dict[str, int]:
    totals = _empty_usage()
    for usage in agent_usage.values():
        for key in totals:
            totals[key] += int(usage.get(key, 0) or 0)
    return totals


def log_workflow_metrics(metrics: dict[str, Any]) -> None:
    logger.info(
        "workflow_metrics %s",
        json.dumps(metrics, ensure_ascii=False, sort_keys=True),
    )
    iterations = int(metrics.get("iterations", 0) or 0)
    duration_ms = int(metrics.get("duration_ms", 0) or 0)
    tool_calls = int(metrics.get("tool_calls", 0) or 0)
    tool_failures = int(metrics.get("tool_failures", 0) or 0)
    failure_rate = tool_failures / tool_calls if tool_calls else 0.0

    if iterations >= settings.monitor_iteration_warning:
        logger.warning(
            "workflow alert: iterations=%d threshold=%d trace_id=%s",
            iterations,
            settings.monitor_iteration_warning,
            metrics.get("trace_id"),
        )
    if tool_calls and failure_rate >= settings.monitor_tool_failure_rate_warning:
        logger.warning(
            "workflow alert: tool_failure_rate=%.3f threshold=%.3f trace_id=%s",
            failure_rate,
            settings.monitor_tool_failure_rate_warning,
            metrics.get("trace_id"),
        )
    if duration_ms >= settings.monitor_duration_warning_ms:
        logger.warning(
            "workflow alert: duration_ms=%d threshold=%d trace_id=%s",
            duration_ms,
            settings.monitor_duration_warning_ms,
            metrics.get("trace_id"),
        )
