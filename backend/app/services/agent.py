import json
import logging
from typing import AsyncIterator

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from app.config import settings
from app.services.llm import get_llm
from app.tools.read_file import read_file
from app.tools.retrieve_knowledge import hybrid_retrieve

logger = logging.getLogger(__name__)

READER_SYSTEM_PROMPT = """你是一位专业的学术论文阅读助手（ReaderAgent）。你的职责是帮助研究人员理解和分析学术论文。

## 核心工作流程（必须严格遵守）
1. **第一步：检索知识库** —— 收到用户问题后，首先必须调用 `hybrid_retrieve` 工具搜索知识库。
   - 这是强制性步骤，即使你认为自己知道答案，也必须先搜索知识库以提供准确的、有来源的信息。
   - 当用户消息中包含以下关键词时，**必须立即调用 hybrid_retrieve**：
     搜索、查找、检索、知识库、文档、论文、研究、有没有、是否有、找一下、查一下、
     了解、介绍、解释、总结、find、search、lookup
   - 将用户的问题转化为简洁的描述性查询进行检索。

2. **第二步：阅读文档** —— 如果用户明确要求阅读当前会话上传的完整文档文件，使用 `read_file` 工具。

3. **第三步：综合分析** —— 基于检索结果和文档内容进行结构化分析，引用来源。

## 分析要求
- 仔细理解检索到的内容，理解其核心方法、实验设计和结论。
- 用清晰的条理回答用户的问题，包括但不限于：
  - 论文的研究问题与动机
  - 提出的方法与创新点
  - 实验设计与结果
  - 论文的局限性
- **事实为依据**：回答严格基于检索到的内容，不要编造信息。如果信息不在检索结果中，明确说明"知识库中未找到相关信息"。

## 输出格式
- 用中文回复用户。
- 先展示你的思考过程（推理步骤、关键发现），然后用分隔线 `---` 隔开，最后给出正式回答。
- 回答要结构清晰，可使用标题和要点。

## 工具说明
- `hybrid_retrieve`：**首选工具**，混合检索（语义搜索 + BM25 + Rerank），效果精准。**回答任何研究问题前都必须先调用。**
- `read_file`：仅在需要完整阅读当前会话的文档文件时使用。
- 在回答中引用知识库内容时，请务必保留返回结果中的 [citation:doc_X:chunk_Y] 引用标记。
"""


def _get_agent():
    llm = get_llm()
    tools = [hybrid_retrieve, read_file]
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=READER_SYSTEM_PROMPT,
    )


async def run_reader_agent(
    user_message: str,
    document_text: str | None = None,
) -> AsyncIterator[dict]:
    """Run the ReaderAgent with streaming output.

    Yields dicts with keys: type (thought/action/observation/token/error), content.
    """
    agent = _get_agent()

    input_text = user_message
    if document_text:
        input_text = (
            f"当前会话上传的文档内容如下：\n\n```\n{document_text}\n```\n\n"
            f"用户问题：{user_message}\n\n"
            f"请基于上述文档内容回答用户的问题。如需读取完整文件，可使用 read_file 工具。"
        )

    logger.info("Agent run started: msg_len=%d, has_doc=%s", len(user_message), document_text is not None)
    messages = [HumanMessage(content=input_text)]

    try:
        async for event in agent.astream_events(
            {"messages": messages},
            version="v1",
        ):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is None:
                    continue

                # Stream content tokens
                content = getattr(chunk, "content", "")
                if content:
                    yield {"type": "token", "content": content}

                # Handle tool call chunks (incremental)
                tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
                if tool_call_chunks:
                    for tc in tool_call_chunks:
                        name = tc.get("name")
                        args = tc.get("args", "")
                        if name:
                            yield {
                                "type": "action",
                                "tool": name,
                                "input": args,
                            }
                            yield {
                                "type": "thought",
                                "content": f"正在调用工具: {name}",
                            }

            elif kind == "on_tool_start":
                name = event.get("name", "unknown")
                input_data = event.get("data", {}).get("input", {})
                logger.info("Tool start: %s, input=%s", name, str(input_data)[:200])
                yield {
                    "type": "thought",
                    "content": f"执行工具 {name}...",
                }

            elif kind == "on_tool_end":
                name = event.get("name", "unknown")
                output = event.get("data", {}).get("output", "")
                output_str = str(output)
                if len(output_str) > 500:
                    output_str = output_str[:500] + "..."
                logger.info("Tool end: %s, output_len=%d", name, len(str(output)))
                yield {
                    "type": "observation",
                    "tool": name,
                    "output": output_str,
                }

    except Exception as e:
        logger.exception("Agent execution error")
        yield {"type": "error", "content": f"Agent 执行出错: {str(e)}"}
