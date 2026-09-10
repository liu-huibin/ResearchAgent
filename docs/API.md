# API 概览

后端默认监听 <http://127.0.0.1:8000>，交互式 OpenAPI 文档位于 <http://127.0.0.1:8000/docs>。非回环部署或配置了 `API_TOKEN` 时，请通过 `X-ResearchMate-Token` 请求头传递 Token。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/sessions` | 创建会话 |
| `GET` | `/api/sessions` | 按更新时间倒序列出会话 |
| `PATCH` | `/api/sessions/{session_id}` | 重命名会话 |
| `DELETE` | `/api/sessions/{session_id}` | 删除会话及其会话级数据 |
| `GET` | `/api/sessions/{session_id}/messages` | 获取消息历史并恢复陈旧运行状态 |
| `POST` | `/api/sessions/{session_id}/messages` | 发送消息并返回 SSE |
| `GET` | `/api/sessions/{session_id}/metrics` | 获取会话累计与最近工作流指标 |
| `POST` | `/api/sessions/{session_id}/upload` | 上传当前会话文档 |
| `GET` | `/api/sessions/{session_id}/document` | 获取当前会话文档元数据 |
| `GET` | `/api/documents/{document_id}/file` | 获取原始文档 |
| `GET` | `/api/documents/{document_id}/citations/{chunk_index}` | 解析并定位引用 |
| `POST` | `/api/knowledge/upload` | 上传、去重并索引知识库文档 |
| `GET` | `/api/knowledge/list` | 列出知识库文档 |
| `DELETE` | `/api/knowledge/{doc_id}` | 删除知识库文档及相关索引 |

请求/响应 Schema、状态码和在线调试以运行中的 `/docs` 为准。流式事件契约见 [多智能体、引用与流式处理](WORKFLOW.md#sse-与持久化语义)。

