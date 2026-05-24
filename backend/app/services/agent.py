import json
from typing import AsyncIterator

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

from app.config import settings
from app.services.llm import get_llm
from app.tools.read_file import read_file

READER_SYSTEM_PROMPT = """你是一位专业的学术论文阅读助手（ReaderAgent）。你的职责是帮助研究人员理解和分析学术论文。

## 工作方式
1. **阅读与理解**：仔细阅读提供的论文内容，理解其核心方法、实验设计和结论。
2. **结构化分析**：用清晰的条理回答用户的问题，包括但不限于：
   - 论文的研究问题与动机
   - 提出的方法与创新点
   - 实验设计与结果
   - 论文的局限性
3. **事实为依据**：回答严格基于论文内容，不要编造信息。如果信息不在论文中，明确说明"论文中未提及"。

## 输出格式
- 用中文回复用户。
- 先展示你的思考过程（推理步骤、关键发现），然后用分隔线 `---` 隔开，最后给出正式回答。
- 回答要结构清晰，可使用标题和要点。

## 工具使用
- 你可以使用 `read_file` 工具来读取文档文件的内容。如果需要阅读当前会话的文档，请使用该工具。
- 如果没有文档可读，直接基于用户提供的信息进行回答。
"""


def _get_agent():
    llm = get_llm()
    tools = [read_file]
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
                yield {
                    "type": "observation",
                    "tool": name,
                    "output": output_str,
                }

    except Exception as e:
        yield {"type": "error", "content": f"Agent 执行出错: {str(e)}"}
