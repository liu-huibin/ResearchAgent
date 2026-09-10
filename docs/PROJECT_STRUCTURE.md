# 项目结构与技术栈

## 技术栈

| 层级 | 当前实现 |
| --- | --- |
| 前端 | React 19、TypeScript 6、Vite 8、Tailwind CSS 4 |
| 文档渲染 | react-pdf / pdf.js、mammoth |
| 后端 | Python、FastAPI、SQLModel、SQLAlchemy asyncio、aiomysql |
| Agent | LangGraph、LangChain、OpenAI-compatible Chat API |
| 检索 | Chroma、BM25、Embedding、可选 sentence-transformers CrossEncoder |
| 数据 | MySQL 8、Chroma 持久目录、BM25 JSON、本地文件系统 |
| 工具协议 | MCP Python SDK，stdio 只读文件 Server |
| 可观测性 | 本地日志与 `workflow_runs`，可选 LangSmith |

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
│   │   ├── tools/             Agent 工具适配器
│   │   ├── main.py            FastAPI 入口
│   │   └── mcp_server.py      MCP 文件读取 Server
│   ├── scripts/               安全加固、索引修复和 KMS 前置核验脚本
│   ├── tests/                 后端单元与集成测试
│   ├── init_db.sql            可重复执行的 MySQL 初始化脚本
│   ├── requirements.txt       Python 依赖
│   └── .env.example           基础环境变量示例
├── frontend/
│   ├── src/components/        三栏 UI、阅读器、对话和侧边栏
│   ├── src/contexts/          文档标签页状态
│   ├── src/hooks/             会话、知识库、SSE 和引用逻辑
│   ├── src/services/          API 与浏览器安全封装
│   ├── tests/                 真实 PDF/DOCX 浏览器回归脚本
│   └── package.json
├── docs/                      项目专题文档
├── run_backend.py             根目录后端启动器
├── run_frontend.py            根目录前端启动器
├── Requirement.md             需求规格，含未完成规划
└── Develop.md                 分阶段开发方案
```

运行数据默认位于 `backend/data/`，日志默认位于 `backend/log/`。这些目录可能包含用户论文、索引和对话相关信息，不应提交到版本库，也不能作为测试清理目标。

后端分层约束详见 [backend/ARCHITECTURE.md](../backend/ARCHITECTURE.md)，安装与数据安全说明见 [安装、配置与安全](SETUP.md)。

