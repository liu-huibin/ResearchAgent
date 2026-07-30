"""Versioned prompt bundles for ResearchMate agents."""

from app.prompts.registry import PromptBundle, get_prompt_bundle, select_prompt_bundle

__all__ = ["PromptBundle", "get_prompt_bundle", "select_prompt_bundle"]
