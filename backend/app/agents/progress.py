"""Public explanations and bounded Agent reports for the workflow UI.

Stage details are deterministic. Agent reports are explicitly authored for the
user interface and parsed from a bounded section of an Agent's final response.
Neither path exposes prompts, hidden chain-of-thought, or raw tool payloads.
"""

import re


PUBLIC_REPORT_START = "<public_report>"
PUBLIC_REPORT_END = "</public_report>"
PUBLIC_REPORT_MAX_CHARS = 1600
MAX_FALLBACK_CITATIONS = 12
_CITATION_RE = re.compile(
    r"\[?citation:doc_(\d+):chunk_(\d+)\]?",
    flags=re.IGNORECASE,
)
_REPORT_FIELDS = (
    "结论",
    "依据",
    "取舍",
    "风险/不确定性",
    "下一步",
)
_REPORT_ALIASES = {
    "风险与不确定性": "风险/不确定性",
    "风险和不确定性": "风险/不确定性",
    "不确定性": "风险/不确定性",
    "风险": "风险/不确定性",
}

IDEATION_TERMS = (
    "思路", "创新", "改进", "扩展", "方向", "方案", "idea",
    "improve", "innovation", "extension", "future work",
)
REVIEW_TERMS = (
    "审查", "评审", "核查", "验证", "批判", "review", "verify", "critique",
)


def extract_citation_markers(*contents: object) -> list[str]:
    """Return unique machine citations in a stable canonical form."""
    markers = []
    seen = set()
    for content in contents:
        for document_id, chunk_index in _CITATION_RE.findall(str(content or "")):
            marker = (
                f"[citation:doc_{int(document_id)}:chunk_{int(chunk_index)}]"
            )
            if marker not in seen:
                seen.add(marker)
                markers.append(marker)
    return markers


def ensure_citation_fallback(content: str, markers: list[str]) -> str:
    """Keep a response navigable when a model rewrites machine citations."""
    if extract_citation_markers(content):
        return content
    available = extract_citation_markers(*markers)[:MAX_FALLBACK_CITATIONS]
    if not available:
        return content
    suffix = "可定位来源：" + " ".join(available)
    return f"{content}\n\n{suffix}" if content.strip() else suffix


def classify_workflow(user_message: str) -> str:
    normalized = user_message.lower()
    if any(term in normalized for term in IDEATION_TERMS):
        return "research_cycle"
    if any(term in normalized for term in REVIEW_TERMS):
        return "read_and_review"
    return "read_only"


def _matched_term(user_message: str, terms: tuple[str, ...]) -> str:
    normalized = user_message.lower()
    return next((term for term in terms if term in normalized), "")


def split_agent_output(content: str) -> tuple[str, str]:
    """Separate an Agent's internal work product from its explicit UI report."""
    start = content.rfind(PUBLIC_REPORT_START)
    if start < 0:
        return content.strip(), ""
    end = content.find(PUBLIC_REPORT_END, start + len(PUBLIC_REPORT_START))
    if end < 0:
        return content.strip(), ""

    raw_report = content[start + len(PUBLIC_REPORT_START):end]
    internal = f"{content[:start]}{content[end + len(PUBLIC_REPORT_END):]}".strip()
    report = sanitize_public_report(raw_report)
    if not report:
        # Keep malformed report text out of later prompts and expose nothing.
        # If the Agent returned only a malformed report, preserve it as the
        # work product so the workflow still has recoverable content.
        return internal or content.strip(), ""
    return internal, report


def sanitize_public_report(content: str) -> str:
    """Allow only the documented report fields and bound their total size."""
    without_hidden_blocks = re.sub(
        r"<(?:think|analysis)>.*?</(?:think|analysis)>",
        "",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    values: dict[str, str] = {}
    current = ""
    for raw_line in without_hidden_blocks.splitlines():
        line = raw_line.strip().lstrip("-*# ").replace("**", "")
        if not line:
            continue
        match = re.match(r"^([^：:]{1,12})[：:]\s*(.*)$", line)
        if match:
            label = _REPORT_ALIASES.get(match.group(1).strip(), match.group(1).strip())
            if label in _REPORT_FIELDS:
                current = label
                values[label] = _clean_report_value(match.group(2))
            else:
                current = ""
            continue
        if current:
            continuation = _clean_report_value(line)
            if continuation:
                values[current] = f"{values[current]} {continuation}".strip()

    if "结论" not in values or len(values) < 2:
        return ""

    lines = []
    for label in _REPORT_FIELDS:
        value = values.get(label, "")[:320].strip()
        if value:
            lines.append(f"{label}：{value}")
    return "\n".join(lines)[:PUBLIC_REPORT_MAX_CHARS].rstrip()


def _clean_report_value(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", value).strip()


def public_stage_detail(
    stage: str,
    user_message: str,
    document_text: str | None,
    previous_stage: str = "",
) -> str:
    workflow = classify_workflow(user_message)
    if stage == "supervisor":
        if workflow == "research_cycle":
            signal = _matched_term(user_message, IDEATION_TERMS)
            return (
                f"任务判断：识别到“{signal}”这一研究设计信号。"
                "路由依据：这类任务既需要论文证据，也需要生成并审查候选方案，"
                "因此选择完整研究流程。下一步：先提取证据，再形成方案并独立复核；"
                "只有审查明确要求修改时才进入一次修正。"
            )
        if workflow == "read_and_review":
            signal = _matched_term(user_message, REVIEW_TERMS)
            return (
                f"任务判断：识别到“{signal}”这一核验信号。"
                "路由依据：需要先建立原文证据基线，再检查回答或方案是否与证据一致。"
                "下一步：ReaderAgent 提取证据后，由 ReviewerAgent 检查事实、可行性和证据缺口。"
            )
        return (
            "任务判断：未识别到研究方案生成或独立审查要求，当前问题按阅读、总结或证据问答处理。"
            "路由依据：无需引入额外的方案生成与返工环节。"
            "下一步：ReaderAgent 完成证据分析后，由 Supervisor 直接汇总。"
        )
    if stage == "reader":
        if document_text:
            return (
                f"当前依据：会话中已有约 {len(document_text):,} 个字符的论文正文。"
                "分析取舍：优先以正文中的研究问题、方法、实验结论和局限为证据，"
                "避免把外部常识混成论文结论。下一步：仅在正文不足以回答时补充知识库检索。"
            )
        return (
            "当前依据：会话中没有可供分析的论文正文。"
            "分析取舍：将知识库检索作为证据入口，不凭模型记忆补造论文结论。"
            "下一步：若检索证据仍不足，将在回答中明确标注缺口。"
        )
    if stage == "ideation":
        return (
            "进入依据：ReaderAgent 已完成证据分析，流程确认本任务需要形成研究方案。"
            "生成约束：候选改进必须能追溯到现有证据，并同时说明验证实验、风险和预期收益；"
            "没有证据支撑的设想只作为待验证假设。下一步：交由 ReviewerAgent 独立复核。"
        )
    if stage == "reviewer":
        return (
            "进入依据：当前流程要求对 ReaderAgent 的分析或 IdeationAgent 的候选方案进行独立复核。"
            "审查标准：逐项检查事实一致性、创新性、可行性和可证伪性。"
            "决策规则：证据不足的内容不能作为既定事实进入最终回答；明确不通过时才触发修正。"
        )
    if stage == "revision":
        return (
            "进入依据：ReviewerAgent 已返回“需修改”或“不通过”结论，流程因此进入修正分支。"
            "修正边界：只执行一次有边界的返工，保留有依据的内容，删除无证据断言，"
            "并补足验证实验与风险控制。下一步：修正版将直接进入最终汇总，避免无限循环。"
        )
    if stage == "finalize":
        if previous_stage == "revision":
            source = "审查后的修正版"
        elif workflow == "read_and_review":
            source = "ReaderAgent 的证据分析和 ReviewerAgent 的核验结果"
        elif workflow == "research_cycle":
            source = "已经通过审查的候选方案"
        else:
            source = "ReaderAgent 的证据分析"
        return (
            f"汇总依据：现在以{source}作为主要材料生成最终回答。"
            "表达取舍：区分原文事实、Agent 推断和待验证假设，不把中间草稿直接当成结论。"
            "输出要求：保留可定位的引用标记，并明确仍未解决的证据缺口。"
        )
    return "正在执行当前编排阶段，并仅向前端公开可审计的任务依据和状态。"
