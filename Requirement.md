**智能科研助手（ResearchMate）需求规格说明书**

**目录**

1. 项目概述
2. 总体架构
3. 前端功能需求
4. 后端功能需求
5. 智能体（Agent）详细设计
6. 可观测性与工程化（Harness Engineering）
7. 数据库设计概要
8. 接口规范概要
9. 非功能性需求
10. 交付与验收标准
11. 附录

---

## 0. 项目环境
- 使用conda环境"ResearchAgent"
- 大模型接入qwen的API模型

## 1. 项目概述

### 1.1 项目背景

研究生在日常科研中需要大量阅读学术论文并构思创新点。现有通用对话工具缺乏对科研场景的深度定制，难以将论文阅读与思路生成有机融合。本项目旨在构建一款智能科研助手，通过多智能体（Multi-Agent）协作，实现“读-想-审”闭环，辅助研究者高效阅读与创新。

### 1.2 项目目标

- 搭建 Web 科研对话平台，支持学术文档上传与在线阅读。
- 实现 Multi-Agent 协作系统，分工处理论文分析、思路生成与内容审查。
- 采用 ReAct（Reasoning + Acting）思考模式，展示透明推理过程。
- 集成混合检索 RAG，基于知识库提供精准、可溯源回答。
- 提供长期会话存储与便捷管理。
- 通过 MCP 封装本地文件读写等工具，增强 Agent 能力。
- 引入可观测性工程（Harness Engineering），保障 Agent 系统稳定可控。

### 1.3 用户角色

- **研究生（主要用户）**：进行论文阅读、发起提问、管理知识库和会话。
- **系统管理员**：维护底层部署与 LLM 配置（服务端统一管理）。

## 2. 总体架构

### 2.1 前端架构

前后端分离的单页应用（SPA），技术栈建议：React/Vue + TypeScript。  
经典三栏布局：

- 左侧栏：会话列表 + 知识库管理
- 中央区域：文档阅读器（支持 PDF/Word）
- 右侧栏：对话界面（消息列表 + 输入框）

### 2.2 后端架构

后端基于 Python + FastAPI 构建，异步 IO 处理高并发。  
核心组件：

- **API Layer**：RESTful + SSE 流式响应。
- **Agent 调度层**：基于 LangGraph 的 Multi-Agent 状态图，协作处理任务。
- **LLM 接入层**：统一封装外部大模型 API，由管理员在服务端配置。
- **Tool 层**：实现文件读写、混合检索等工具，部分工具通过 MCP 协议暴露。
- **存储层**：MySQL（会话/消息/文档元数据）、Chroma 向量库、本地文件系统。
- **可观测性层**：集成 LangSmith 或类似平台，实现全链路追踪与提示管理。

### 2.3 数据存储架构

- **关系型数据库（MySQL）**：用户表（预留多用户）、会话表、消息表、知识库文档元数据表。
- **向量数据库（Chroma）**：文档切片向量与 BM25 索引。
- **文件存储**：`/data/uploads/{user_id}/knowledge/` 存储原始文件。

## 3. 前端功能需求

### 3.1 布局概览

三栏布局，支持拖拽调整宽度，默认比例：左侧 15%，中间 50%，右侧 35%。

### 3.2 左侧：会话与知识库管理

| 功能 | 详细描述 |
|------|----------|
| 会话列表 | 时间倒序展示历史会话，显示标题、最后活跃时间。 |
| 切换会话 | 点击会话项，中间和右侧区域切换至对应文档及消息历史。 |
| 新建会话 | 顶部按钮，创建空白会话，自动生成默认标题。 |
| 删除会话 | 右键菜单或悬停删除按钮，二次确认后删除，同步清除绑定及消息。 |
| 重命名会话 | 双击标题内联编辑，限制 50 字符。 |
| 上传到知识库 | 上传按钮，支持 PDF/Word，前端显示上传进度。上传前计算文件 MD5，若重复则提示并拒绝。 |
| 知识库文件列表 | 可折叠区域展示已上传文件，支持删除，删除同步清除向量、BM25 索引及原始文件。 |

### 3.3 中间：文档阅读区

| 功能 | 详细描述 |
|------|----------|
| 文档展示 | 上传至当前会话的文档在此渲染。 |
| PDF 渲染 | pdf.js 逐页渲染，支持缩放、翻页、搜索高亮。 |
| Word 渲染 | 后端转 HTML 或前端 mammoth.js 渲染，保留基本格式。 |
| 上下文标记 | Agent 引用片段时，对应段落高亮并可跳转。 |
| 无文档状态 | 显示“暂无文档，请上传文件到当前会话”。 |

### 3.4 右侧：对话交互区

| 功能 | 详细描述 |
|------|----------|
| 消息展示 | 用户与 Agent 气泡区分，Agent 回复包含：思考过程（灰色可折叠）、最终正文（黑色）。 |
| 流式响应 | SSE 流式传输，先流式输出思考过程，再输出正文。 |
| 文件上传 | 输入框附近上传按钮，文档绑定到当前会话并在中央显示。 |
| 工具调用可视化 | 思考过程中展示工具名、输入输出摘要卡片。 |
| 操作按钮 | 复制、重新生成、👍/👎 反馈。 |
| 上下文关联 | 点击引用标注，中央阅读区滚动并高亮对应段落。 |

### 3.5 通用交互要求

- 浅色/深色主题支持。
- 操作响应 < 200ms 给出视觉反馈。
- 错误提示友好，网络异常时自动重试。

## 4. 后端功能需求

### 4.1 核心框架与 API

使用 FastAPI 构建 RESTful API，SSE 实现流式响应。

核心接口模块：

- 会话管理：`POST /api/sessions`、`GET /api/sessions`、`DELETE /api/sessions/{id}`、`PATCH /api/sessions/{id}`
- 消息处理：`POST /api/sessions/{id}/messages`（返回 SSE 流）、`GET /api/sessions/{id}/messages`
- 知识库管理：`POST /api/knowledge/upload`、`DELETE /api/knowledge/{doc_id}`、`GET /api/knowledge/list`
- 会话文档：`POST /api/sessions/{id}/upload`、`GET /api/sessions/{id}/document`

### 4.2 统一 LLM 接入

后端通过配置文件（环境变量）统一管理 API 地址、密钥、模型名称等。  
Agent 初始化时从全局配置加载 LLM 实例，所有用户共用同一模型。  
管理员可修改配置后重启服务以切换模型。

### 4.3 Multi-Agent 协作系统（精简设计）

基于 LangGraph 构建有状态的 Multi-Agent 图，包含四个 Agent：

| Agent | 职责 |
|-------|------|
| Supervisor | 意图理解、任务分解、调度其他 Agent、汇总结果 |
| ReaderAgent | 精读论文，回答事实性问题，提取方法、结论等 |
| IdeationAgent | 基于论文内容与知识库，生成科研思路、扩展方向 |
| ReviewerAgent | 审查生成内容的合理性、与原文的一致性，消除幻觉，提出改进建议 |

**协作理由**：  
去掉单独的 RetrievalAgent，将混合检索封装为工具，供 ReaderAgent 和 IdeationAgent 直接调用，减少 Agent 数量与通信开销。  
增加 ReviewerAgent，对 IdeationAgent 的产出进行事实核查与质量评估，保障生成内容的可信度。  
总 Agent 数为 4，结构清晰，避免过度复杂。

### 4.4 ReAct 思考模式与循环上限

所有 Agent 遵循 ReAct 范式：输出 `Thought`（推理）→ `Action`（工具调用）→ `Observation`（观察结果），循环直至得到最终答案。  
**循环上限**：LangGraph 图中设置 `max_iterations`（默认 10），单个 Agent 或整体流程达到上限后强制结束并返回当前已生成的回复，防止无限循环和资源浪费。  
后端解析 Thought/Action 边界，通过 SSE 将思考过程（灰色）和正文分别推送前端。

### 4.5 工具封装与 MCP 集成

**本地工具（Agent 直接调用）**：

- `read_file(file_path)`：读取本地指定目录（如 `/data/documents/`）下的 Word/PDF 文本内容片段，供论文阅读使用。
- `search_arxiv(query)`：调用 ArXiv API 搜索论文。
- `hybrid_retrieve(query, top_k)`：混合检索工具，内部封装多路召回与重排序逻辑。

**MCP 集成（增强扩展性）**：  
将文件读写工具通过 MCP Server 标准化暴露，MCP Server 管理对 `/data/documents/` 目录的安全访问（限制读取范围，禁止写入或仅允许写入指定子目录）。  
Agent 通过 MCP Client 动态发现并调用 `read_file`、`write_file`（若未来需要）等工具。  
首期实现：`read_file` 通过 MCP 调用，验证技术可行性；`hybrid_retrieve` 维持本地工具形式。

### 4.6 RAG 检索增强生成（混合检索 + MD5 去重）

**上传处理流程**：

1. 文件上传时，后端计算文件 MD5 哈希值。
2. 查询 `documents` 表中同用户下是否存在相同 MD5 的文档，若存在则返回错误“文件已存在”，拒绝重复上传。
3. 校验格式，保存原始文件至 `/data/uploads/{user_id}/knowledge/`。
4. 提取文本，清洗后按 500 tokens、重叠 50 tokens 切片。
5. 混合索引构建：
  - 向量化切片，存入 Chroma 集合 `knowledge_{user_id}`。
  - 同时基于切片构建 BM25 索引（使用 `rank_bm25` 或 Elasticsearch），存储文本及对应切片元数据。
6. 向量元数据记录：`source_doc_id`, `chunk_index`, `text`, `file_md5`。

**多路混合检索流程（`hybrid_retrieve` 工具）**：

1. 接收查询文本，进行语义向量检索（从 Chroma 召回 Top-K1，如 20 个片段）。
2. 同时执行 BM25 词检索（从 BM25 索引召回 Top-K2，如 20 个片段）。
3. 合并两路结果并去重（以 `chunk_id` 为依据）。
4. 使用 Rerank 模型（如 bge-reranker-v2-m3 或 Cohere Rerank）对合并后的候选片段进行精排，计算相关性分数。
5. 返回最终 Top-K（默认 5）的切片文本及来源信息，供 Agent 引用。

### 4.7 会话与消息管理

- 会话归属于当前固定单用户（`user_id=1`），数据库结构预留多用户外键。
- 会话包含：`id`, `user_id`, `title`, `active_document_id`, `created_at`, `updated_at`。
- 消息包含：`id`, `session_id`, `role`, `content`, `thought`, `tool_calls`(JSON), `created_at`。
- 流式过程中消息逐步写入 MySQL，支持断线重连后历史补全。

### 4.8 文件与知识库管理

- 区分知识库文档（长期、跨会话）与会话文档（仅当前会话）。
- 会话文档上传不自动向量化，仅本地存储和渲染。
- 知识库文档删除：同步清除 Chroma 切片、BM25 索引项、本地原始文件。

## 5. 智能体（Agent）详细设计

### 5.1 Supervisor（主协调 Agent）

- **角色**：任务路由器，维持全局状态。
- **工具**：无直接工具，拥有调度子 Agent 权限。
- **职责**：
  - 接收用户输入，分析意图。
  - 决定调用 ReaderAgent、IdeationAgent 或 ReviewerAgent 的顺序和次数。
  - 子任务完成后评估是否需要进一步处理或直接汇总回答用户。
  - 严格控制整体迭代轮次不超上限。

### 5.2 ReaderAgent（论文阅读 Agent）

- **角色**：文献分析专家。
- **可用工具**：`read_file`（MCP）、`hybrid_retrieve`、`search_arxiv`。
- **典型场景**：
  - 总结论文方法、创新点、实验结果。
  - 解释特定图表或概念。
  - 对比多篇论文异同。
- **输出**：结构化的论文分析结果。

### 5.3 IdeationAgent（思路生成 Agent）

- **角色**：研究创意发想者。
- **可用工具**：`hybrid_retrieve`、`search_arxiv`。
- **典型场景**：
  - “根据这篇论文，提出 3 个改进方向。”
  - “结合知识库中相关研究，设计扩展实验方案。”
- **输出**：包含可行性分析的创意列表。
- **注意**：不包含代码生成功能。

### 5.4 ReviewerAgent（审查 Agent）

- **角色**：内容质量守门员。
- **可用工具**：`read_file`（核实原文）、`hybrid_retrieve`（查找证据）。
- **职责**：
  - 对 IdeationAgent（或其他 Agent）生成的内容进行事实核查。
  - 验证思路是否与原文一致，有无虚构信息（幻觉）。
  - 输出审查意见：通过、需修改（附建议）、不通过（附理由）。
- **触发条件**：Supervisor 判断生成内容较为关键时调用。

### 5.5 Agent 间协作流程

**示例（用户：“阅读这篇论文，并提出改进思路”）**：

1. Supervisor 分析意图，调用 ReaderAgent，传入当前文档。
2. ReaderAgent 使用 `read_file` 阅读论文，必要时结合 `hybrid_retrieve` 查找知识库背景，输出总结。
3. Supervisor 将总结传递给 IdeationAgent。
4. IdeationAgent 利用总结和 `hybrid_retrieve` 检索，生成 3 个改进方向。
5. Supervisor 选择性地调用 ReviewerAgent，审查思路是否与原文一致、是否合理。
6. ReviewerAgent 给出审查意见，若存在问题可反馈给 IdeationAgent 修正（单次修正迭代）。
7. Supervisor 整合最终结果回复用户。

## 6. 可观测性与工程化（Harness Engineering）（仅供参考，主要依据AI领域最新的harness engineering）

为确保 Multi-Agent 系统的稳定可控与持续优化，引入 Harness Engineering 理念，对 Agent 的运行过程、提示管理、评估反馈及资源消耗进行统一工程化治理，具体包括以下方面：

- **全链路追踪**：集成 LangSmith（或 LangFuse），对 Agent 的任务执行流程进行全链路追踪，记录输入输出、工具调用、推理过程（Reasoning Trace）及状态变化，用于问题定位、行为分析与性能优化。
- **提示管理**：统一管理所有 Agent 的系统提示词、ReAct 模板及工具调用策略，并通过配置化与版本化方式维护运行时参数，支持 Prompt 迭代、版本回滚及 A/B 测试，从而提高系统可维护性与实验可复现性。
- **评估体系**：构建自动化评估流水线，针对 ReviewerAgent 的事实核查、IdeationAgent 的创新性等设定评分标准，定期回归验证模型切换或提示变更的影响。
- **监控告警**：对 Agent 循环次数、工具调用失败率、API 时延等设置阈值，接入日志与告警系统（如 Prometheus + Grafana）。
- **成本控制**：记录各 Agent 的 Token 消耗，展示在用户面板（预留），优化提示以减少浪费。

## 7. 数据库设计概要

### 7.1 MySQL 表结构

**users**（预留多用户，当前固定单用户）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INT (PK) | 用户 ID |
| username | VARCHAR(50) | 用户名 |
| created_at | DATETIME | 创建时间 |

**sessions**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INT (PK) | 会话 ID |
| user_id | INT (FK) | 所属用户 |
| title | VARCHAR(100) | 会话标题 |
| active_document_id | INT NULL | 当前绑定文档 ID |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 最后活跃时间 |

**messages**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INT (PK) | 消息 ID |
| session_id | INT (FK) | 所属会话 |
| role | VARCHAR(20) | user/assistant/tool |
| content | TEXT | 最终正文 |
| thought | TEXT NULL | 思考过程（灰色部分） |
| tool_calls | JSON NULL | 工具调用记录 |
| created_at | DATETIME | 创建时间 |

**documents**

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | INT (PK) | 文档 ID |
| user_id | INT (FK) | 上传用户 |
| filename | VARCHAR(255) | 原始文件名 |
| file_path | VARCHAR(500) | 本地存储路径 |
| file_md5 | VARCHAR(32) | 文件 MD5 哈希值，用于去重 |
| type | VARCHAR(10) | knowledge / session |
| session_id | INT NULL | 若为会话文档，绑定会话 ID |
| created_at | DATETIME | 上传时间 |

### 7.2 向量与索引存储

- **Chroma 集合**：`knowledge_{user_id}`，存储向量切片。
- **BM25 索引**：内存或持久化（如 Whoosh 或小型 Elasticsearch），以 `doc_id+chunk_index` 关联。
- **Rerank 模型**：独立部署或调用 API，作为检索流程中的精排服务。

## 8. 接口规范概要

| 方法 | 路径 | 描述 | 类型 |
|------|------|------|------|
| POST | `/api/sessions` | 创建新会话 | JSON |
| GET | `/api/sessions` | 获取会话列表 | JSON |
| DELETE | `/api/sessions/{id}` | 删除会话 | - |
| PATCH | `/api/sessions/{id}` | 重命名会话 | JSON |
| POST | `/api/sessions/{id}/messages` | 发送消息（SSE 流） | JSON → SSE |
| GET | `/api/sessions/{id}/messages` | 获取历史消息 | JSON |
| POST | `/api/knowledge/upload` | 上传知识库文档（MD5 去重） | multipart/form-data |
| DELETE | `/api/knowledge/{doc_id}` | 删除知识库文档 | - |
| GET | `/api/knowledge/list` | 知识库文档列表 | JSON |
| POST | `/api/sessions/{id}/upload` | 上传当前会话文档 | multipart/form-data |
| GET | `/api/sessions/{id}/document` | 获取会话文档内容/下载 URL | JSON |

**SSE 事件格式（不变）**

```text
event: thought
data: {"content": "正在分析论文方法..."}

event: action
data: {"tool": "hybrid_retrieve", "input": "Transformer 变体"}

event: observation
data: {"tool": "hybrid_retrieve", "output": "..."}

event: token
data: {"content": "根据论文内容，该方法的创新点在于..."}

event: done
data: {"message_id": 123}
```

## 9. 非功能性需求

### 9.1 性能

- 流式响应首字节延迟 < 2 秒（不含 LLM 首 token 时间）。
- 混合检索（向量+BM25+Rerank）总延迟 < 1.5 秒。
- 单轮 Agent 调用最大时长限制 120 秒，超时返回部分结果。

### 9.2 安全性

- 文件上传限制大小 ≤ 50MB，白名单格式，MD5 去重防冗余。
- MCP 文件读取工具限定根目录 /data/documents/，禁止访问系统文件。
- API 接口速率限制（每分钟 20 次消息发送）。
- 后端 LLM API 密钥通过环境变量注入，不可从前端获取。

### 9.3 可用性

- 支持 LLM API 异常时的优雅降级，返回“模型服务暂时不可用”。
- 服务重启不丢失会话与消息。

### 9.4 可扩展性

- Agent 通过配置文件注册，新增 Agent 只需实现标准接口。
- 工具以插件形式注册，MCP 支持动态加载新工具。
- 数据库预留多用户字段，后续可直接扩展登陆系统。

### 9.5 可维护性

- 代码遵循 PEP8，模块清晰分离。
- 配置与代码分离（数据库连接、模型配置等使用环境变量）。
- 详细日志记录，集成可观测性平台，便于问题排查。

## 10. 交付与验收标准

| 编号 | 验收项 | 验收标准 |
|------|--------|----------|
| 1 | 前端三栏布局与会话管理 | 正常创建/删除/切换会话，文档上传并显示 |
| 2 | 流式对话展示（思考+正文） | 思考过程灰色逐字输出，正文黑色 |
| 3 | Multi-Agent 协作完成论文阅读+思路生成+审查 | 输入复合指令，Supervisor 正确调度 Reader、Ideation、Reviewer，返回经审查的思路 |
| 4 | 知识库混合检索与 MD5 去重 | 上传 PDF，重复文件被拒绝；提问可召回混合检索结果，答案附带引用 |
| 5 | MCP 文件读取工具 | Agent 通过 MCP 成功读取 /data/documents/ 下指定文件内容 |
| 6 | Agent 循环上限 | 在 LangGraph 设置最大迭代 10 次，达到后强制结束 |
| 7 | 会话历史持久化 | 刷新页面后可恢复会话和消息 |
| 8 | 可观测性集成 | LangSmith 中能看到完整推理链与工具调用记录 |

## 11. 附录

### 技术栈清单

- **前端**：React 18+ / Vue 3，TypeScript，TailwindCSS，pdf.js，mammoth.js
- **后端**：Python 3.11+，FastAPI，LangChain，LangGraph，SQLModel，ChromaDB，rank_bm25，sentence-transformers（Rerank）
- **LLM**：由管理员统一配置（OpenAI 兼容接口）
- **数据库**：MySQL 8.0，Chroma
- **MCP**：mcp-python-sdk，自主实现文件读取 Server
- **可观测性**：LangSmith / LangFuse
- **部署**：Docker + Docker Compose

### 术语表

- **ReAct**：Reasoning + Acting，交替推理与行动的 Agent 模式。
- **MCP**：Model Context Protocol，标准化工具供给协议。
- **RAG**：Retrieval-Augmented Generation，检索增强生成。
- **混合检索**：语义向量检索 + BM25 词检索 + Rerank 精排的组合检索策略。
- **Harness Engineering**：用于驱动 AI Agent 的运行时工程体系，负责协调提示词、工具调用、状态管理、记忆机制、评估反馈与异常恢复等流程。