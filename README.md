# ResearchMate

面向论文阅读、知识库问答和科研思路审查的本地多智能体研究助手。

当前后端版本为 `0.5.0`。项目采用 React 三栏界面、FastAPI API、LangGraph 多智能体工作流、MySQL 持久化、Chroma + BM25 混合检索、SSE 流式响应和 MCP 只读文件工具，默认按单用户、本机开发环境运行。

> 本 README 以当前代码为准。`Requirement.md` 和 `Develop.md` 同时包含需求目标、历史设计及后续规划，其中部分能力尚未实现，不能视为当前运行说明。

## 主要能力

- 三栏工作区：左侧会话与知识库，中间 PDF/DOCX 阅读器，右侧流式对话。
- 会话管理：创建、切换、重命名、删除和历史恢复；首次提问后自动生成极短标题。
- 文档能力：会话内单篇精读，以及带 MD5 去重、分块和索引的长期知识库。
- 混合检索：语义召回与 BM25 召回合并去重，再使用向量相似度或可选 CrossEncoder 精排。
- 多智能体协作：Supervisor、ReaderAgent、IdeationAgent 和 ReviewerAgent 按任务选择最小必要流程。
- 公开推理说明：展示任务判断、证据、关键取舍、风险和下一步，不展示隐藏思维链、系统提示词及工具原始数据。
- 可定位引用：切换到来源文档，定位 PDF 页或 DOCX 段落并高亮原文。
- 可靠流式处理：SSE 心跳、阶段状态、周期检查点、断流收尾、异常恢复和幂等持久化。
- 可观测性：记录工作流状态、Agent Token、工具调用、耗时和提示版本；可选接入 LangSmith。
- 安全边界：默认仅监听回环地址，支持 API Token、严格 CORS、上传结构校验、MCP 路径限制和 MySQL TLS。

## 快速开始

需要 Windows PowerShell、Conda、Python 3.11+、Node.js 20.19+ 或 22.12+、npm 和 MySQL 8+。完整环境说明、TLS、API Token 和全部配置项见 [安装、配置与安全](docs/SETUP.md)。

在仓库根目录执行：

```powershell
conda create -n ResearchAgent python=3.12 -y
conda run -n ResearchAgent python -m pip install -r backend/requirements.txt

Set-Location frontend
npm.cmd ci
Set-Location ..

mysql.exe -u root -p -e 'source backend/init_db.sql'
Copy-Item backend/.env.example backend/.env
```

在 `backend/.env` 中填写 MySQL、LLM 和 Embedding 配置后，分别打开两个终端：

```powershell
conda run -n ResearchAgent python run_backend.py
```

```powershell
conda run -n ResearchAgent python run_frontend.py
```

默认地址：

- 前端：<http://127.0.0.1:3000>
- 健康检查：<http://127.0.0.1:8000/api/health>
- OpenAPI：<http://127.0.0.1:8000/docs>

启动器使用严格端口，不会在端口占用时自动换端口。自定义端口、无重载启动和非回环绑定方法见 [启动说明](docs/SETUP.md#启动)。

## 系统架构

```text
Edge / Chrome
    │
    │ http://127.0.0.1:3000  (/api 由 Vite 代理)
    ▼
React + TypeScript
    ├── 会话与知识库
    ├── PDF / DOCX 阅读器
    ├── SSE 对话与公开协作说明
    └── 引用跳转与原文高亮
    │
    ▼
FastAPI  http://127.0.0.1:8000
    ├── routers        HTTP、SSE 和错误映射
    ├── services       会话、文档、检索、持久化与引用定位
    ├── agents         LangGraph 状态、节点、路由和执行限制
    ├── tools          hybrid_retrieve、MCP read_file
    └── core           配置、数据库、日志、安全和本地存储
         │
         ├── MySQL     会话、消息、文档元数据、工作流指标
         ├── Chroma    语义向量索引
         ├── BM25      JSON 词法索引
         └── Files     原始上传文件
```

后端职责边界和依赖规则见 [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md)。

## 技术栈

| 层级 | 当前实现 |
| --- | --- |
| 前端 | React 19、TypeScript 6、Vite 8、Tailwind CSS 4 |
| 文档渲染 | react-pdf / pdf.js、mammoth |
| 后端 | Python、FastAPI、SQLModel、SQLAlchemy asyncio、aiomysql |
| Agent | LangGraph、LangChain、OpenAI-compatible Chat API |
| 检索 | Chroma、BM25、Embedding、可选 sentence-transformers CrossEncoder |
| 工具与观测 | MCP stdio 只读文件 Server、本地指标、可选 LangSmith |

## 使用与多智能体流程

1. 新建会话；如需精读单篇论文，在中间区域上传 PDF/DOCX。
2. 如需跨论文检索，在左侧知识库上传文件并等待索引完成。
3. 在右侧提问；首次提问会将“新会话”替换为最多 12 个字符的稳定短标题。
4. 展开“推理与协作说明”查看 Agent 的公开报告、工具状态和失败信息。
5. 点击蓝色“来源”按钮，切换文档并定位高亮引用片段。

```text
普通阅读/证据问答：Supervisor → Reader → Finalizer
明确审查/核验任务：Supervisor → Reader → Reviewer → Finalizer
思路/创新/方案任务：Supervisor → Reader → Ideation → Reviewer
                                      └─ 需要修改 → Revision（最多一次）
                                                     → Finalizer
```

可跳转引用必须包含 `[citation:doc_N:chunk_M]` 机器标记；`[1, Sec.2.3]`、`[来源 3]` 等普通文本不能可靠定位。Agent 公开报告是专门面向界面生成的结构化说明，不是模型隐藏思维链。完整路由、引用规则和 SSE 持久化语义见 [多智能体、引用与流式处理](docs/WORKFLOW.md)。

## 目录结构

```text
ResearchAgemt/
├── backend/
│   ├── app/
│   │   ├── agents/            多智能体状态图、节点、公开报告和运行器
│   │   ├── core/              配置、数据库、日志、安全、文件边界
│   │   ├── models/            SQLModel 数据表
│   │   ├── prompts/           版本化 Prompt Bundle
│   │   ├── routers/           FastAPI 路由
│   │   ├── schemas/           API 请求/响应模型
│   │   ├── services/          应用服务与基础设施适配器
│   │   └── tools/             Agent 工具适配器
│   ├── scripts/               安全、索引修复和 KMS 前置核验脚本
│   ├── tests/                 后端测试
│   ├── init_db.sql            MySQL 初始化
│   └── requirements.txt       Python 依赖
├── frontend/
│   ├── src/                   React 应用、状态 Hook 和 API 封装
│   ├── tests/                 PDF/DOCX 浏览器回归脚本
│   └── package.json
├── docs/                      安装、工作流、API、测试和排障文档
├── run_backend.py             根目录后端启动器
├── run_frontend.py            根目录前端启动器
├── Requirement.md             需求规格，含未完成规划
└── Develop.md                 分阶段开发方案
```

运行数据默认位于 `backend/data/`，日志默认位于 `backend/log/`。其中可能包含用户论文、索引和对话相关信息，不应提交到版本库，也不能作为测试清理目标。

## 文档导航

- [安装、配置与安全](docs/SETUP.md)：完整安装、`.env`、端口、TLS、Token、配置表和数据边界。
- [项目结构与技术栈](docs/PROJECT_STRUCTURE.md)：完整依赖构成、目录职责和运行数据位置。
- [多智能体、引用与流式处理](docs/WORKFLOW.md)：Agent 职责、路由、公开报告、引用定位和 SSE 终态。
- [API 概览](docs/API.md)：当前 HTTP/SSE 接口清单。
- [测试与交付检查](docs/TESTING.md)：后端、前端和本地 Edge 回归命令。
- [故障排查](docs/TROUBLESHOOTING.md)：环境、端口、MySQL 和来源跳转问题。
- [后端架构](backend/ARCHITECTURE.md)：分层职责和依赖规则。
- [阶段五说明](backend/PHASE5.md)：MCP、指标、Prompt 实验和 LangSmith。
- [需求规格](Requirement.md)：完整需求及尚未实现的规划项。
- [开发路线](Develop.md)：分阶段开发方案与验收目标。
- [KMS 开发计划](KMS开发计划.md)：暂缓的后续计划，不属于当前运行依赖。

## 当前边界

- 当前固定 `user_id=1`，没有登录、权限角色或多租户隔离。
- KMS 尚未接入当前问答运行时，仅保留需求、设计和前置核验材料。
- 没有 Dockerfile、Compose 或正式部署配置；当前仅说明本地开发启动。
- 未实现 ArXiv 在线搜索、OCR、暗色主题、移动端适配和完整反馈/重新生成功能。
- MCP 首期只提供 `read_file`；混合检索仍是本地 LangChain 工具。
- 扫描型图片 PDF 若无法提取文本会被拒绝进入知识库。
- 前端不展示隐藏思维链，只展示 Agent 专门生成的公开推理说明。
- 仓库当前没有 `LICENSE` 文件，不应默认视为可自由分发的开源项目。

## 维护原则

1. Router 只处理协议、依赖注入和错误映射；事务、文件和索引编排放在 Service。
2. Agent 节点负责模型行为，Graph 只描述拓扑，Runner 负责限制、事件翻译和指标。
3. 数据库、文件、Chroma 或 BM25 写操作必须具备回滚或补偿清理测试。
4. 不为无使用方的旧导入路径保留兼容层；前后端契约同步升级。
5. 不新增没有稳定共享契约的 `utils.py`、`common.py` 或通用 BaseService。
6. 任何可定位文档事实都应保留 `[citation:doc_N:chunk_M]` 机器标记。
