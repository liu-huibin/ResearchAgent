import unittest
import uuid
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.core.config import settings
from app.prompts.registry import select_prompt_bundle
from app.services.observability import WorkflowMetricsCallback, summarize_agent_usage


class ObservabilityTests(unittest.TestCase):
    def test_token_usage_is_attributed_to_agent(self):
        callback = WorkflowMetricsCallback()
        run_id = uuid.uuid4()
        callback.on_chat_model_start(
            {},
            [[]],
            run_id=run_id,
            metadata={"research_agent": "ReaderAgent"},
        )
        response = LLMResult(
            generations=[[
                ChatGeneration(
                    message=AIMessage(
                        content="answer",
                        usage_metadata={
                            "input_tokens": 11,
                            "output_tokens": 7,
                            "total_tokens": 18,
                        },
                        response_metadata={"model_name": "qwen-plus"},
                    )
                )
            ]]
        )
        callback.on_llm_end(response, run_id=run_id)

        usage = callback.snapshot()
        self.assertEqual(usage["ReaderAgent"]["total_tokens"], 18)
        self.assertEqual(summarize_agent_usage(usage)["input_tokens"], 11)

    def test_prompt_experiment_assignment_is_reproducible(self):
        with (
            patch.object(settings, "prompt_primary_variant", "phase4-v1"),
            patch.object(settings, "prompt_experiment_variant", "phase5-concise-v1"),
            patch.object(settings, "prompt_experiment_percentage", 100),
        ):
            first = select_prompt_bundle(42)
            second = select_prompt_bundle(42)

        self.assertEqual(first.variant, "phase5-concise-v1")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
