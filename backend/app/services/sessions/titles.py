"""Deterministic, low-latency titles for the first user message."""

import re


PLACEHOLDER_TITLES = {"", "新会话", "new chat", "new session"}
_LEADING_PHRASES = (
    "麻烦帮我",
    "请帮我",
    "我希望",
    "我需要",
    "我想要",
    "请问",
    "能否",
    "可以",
    "帮我",
    "麻烦",
    "请",
)


def is_placeholder_title(title: str | None) -> bool:
    return (title or "").strip().lower() in PLACEHOLDER_TITLES


def generate_session_title(user_message: str, max_chars: int = 12) -> str:
    """Create a short, stable title without another model request."""
    has_citation = bool(re.search(r"\[citation:doc_\d+:chunk_\d+\]", user_message))
    has_link = bool(re.search(r"https?://\S+", user_message))
    text = re.sub(r"\[citation:doc_\d+:chunk_\d+\]", "", user_message)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    for phrase in _LEADING_PHRASES:
        if text.startswith(phrase):
            text = text[len(phrase):].lstrip(" ，,：:")
            break
    text = re.split(r"[\r\n。！？!?；;]", text, maxsplit=1)[0]
    text = re.sub(r"[`*_>#\[\](){}]", "", text).strip(" ，,：:")
    text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)
    if not text:
        if has_link:
            return "链接内容分析"
        if has_citation:
            return "引用内容分析"
        return "会话内容"
    return text[:max(1, max_chars)].rstrip()
