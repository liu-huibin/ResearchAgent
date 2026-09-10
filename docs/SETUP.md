# 安装、配置与安全

本文说明 ResearchMate 的本地开发环境、首次安装、启动方式、配置项和数据安全边界。项目概览请先阅读根目录 [README](../README.md)。

## 环境要求

- Windows 10/11 与 PowerShell。当前启动和安全脚本主要按 Windows 开发环境验证。
- Conda 环境名：`ResearchAgent`。
- Python 3.11+；当前开发环境使用 Python 3.12。
- Node.js 20.19+ 或 22.12+，以及 npm（Vite 8 的运行要求）。
- MySQL 8+。
- 可访问的 OpenAI-compatible Chat/Embedding API。默认配置面向阿里云百炼 Qwen。
- 支持 JavaScript 的现代浏览器；浏览器引用回归脚本默认使用本地 Edge。

## 首次安装

### 1. 创建 Python 环境并安装依赖

在仓库根目录执行：

```powershell
conda create -n ResearchAgent python=3.12 -y
conda run -n ResearchAgent python -m pip install -r backend/requirements.txt
```

`requirements.txt` 包含本地 CrossEncoder 所需的 CPU 版 PyTorch。首次安装体积较大，需要可访问 PyPI 和 PyTorch CPU 软件源。

### 2. 安装前端依赖

```powershell
Set-Location frontend
npm.cmd ci
Set-Location ..
```

### 3. 初始化 MySQL

使用具备建库权限的 MySQL 管理账号执行：

```powershell
mysql.exe -u root -p -e 'source backend/init_db.sql'
```

`backend/init_db.sql` 可以重复执行，会创建 `research_mate` 数据库及 `users`、`sessions`、`messages`、`documents`、`workflow_runs` 表。还需要确保应用账号对 `research_mate` 拥有所需权限；仓库中的 `backend/scripts/provision_mysql_security.py` 可用于受控环境的账号/TLS 加固，执行前先查看其 `--help`。

### 4. 创建本地配置

```powershell
Copy-Item backend/.env.example backend/.env
```

至少配置：

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=researchmate_app
MYSQL_PASSWORD=
MYSQL_PASSWORD_FILE=.secrets/mysql_app_password
MYSQL_DATABASE=research_mate

LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=replace-with-your-key
LLM_MODEL_NAME=qwen-plus
EMBEDDING_MODEL=text-embedding-v4
```

`MYSQL_PASSWORD` 与 `MYSQL_PASSWORD_FILE` 二选一。密码文件路径相对于 `backend/` 解析，文件中只放密码本身。不要提交 `backend/.env`、`backend/.secrets/` 或真实密钥。

默认要求 MySQL TLS。若本机数据库已配置 TLS，请同步填写 `MYSQL_SSL_CA`；仅在完全受控的回环开发环境中，才可临时使用：

```dotenv
MYSQL_REQUIRE_TLS=false
MYSQL_SSL_VERIFY=false
```

## 启动

始终从仓库根目录启动。打开两个 PowerShell 终端。

终端一：

```powershell
conda run -n ResearchAgent python run_backend.py
```

终端二：

```powershell
conda run -n ResearchAgent python run_frontend.py
```

默认地址：

- 前端：<http://127.0.0.1:3000>
- 后端健康检查：<http://127.0.0.1:8000/api/health>
- OpenAPI 文档：<http://127.0.0.1:8000/docs>

两个启动器都使用严格端口：端口被占用时会失败，不会静默切换到其他端口。开发模式下后端监视 `backend/app/`，前端使用 Vite HMR。

### 使用自定义端口

后端端口与前端代理必须同步：

```powershell
conda run -n ResearchAgent python run_backend.py --port 8100
conda run -n ResearchAgent python run_frontend.py --backend-url http://127.0.0.1:8100
```

单进程后端冒烟测试可关闭自动重载：

```powershell
conda run -n ResearchAgent python run_backend.py --no-reload
```

非回环绑定必须配置至少 32 个字符的 `API_TOKEN`，并同步设置 `CORS_ALLOWED_ORIGINS`。浏览器收到 `401` 后会提示输入 Token，并且只存入当前标签页的 `sessionStorage`；Token 不会进入 URL 或前端构建产物。

## 常用配置

所有配置均由 `backend/app/core/config.py` 定义，环境变量写入 `backend/.env`。

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `MYSQL_*` | 见 `.env.example` | MySQL 地址、账号、数据库和 TLS |
| `LLM_API_BASE` | DashScope compatible-mode | Chat 与 Embedding API 基址 |
| `LLM_API_KEY` | 空 | LLM/Embedding API 密钥 |
| `LLM_MODEL_NAME` | `qwen-plus` | 对话模型 |
| `EMBEDDING_MODEL` | `text-embedding-v4` | 文档和查询向量模型 |
| `AGENT_MAX_ITERATIONS` | `10` | LangGraph 递归/迭代上限 |
| `AGENT_TIMEOUT_SECONDS` | `120` | 单次工作流硬超时 |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `500` / `50` | 文档分块字符窗口与重叠 |
| `HYBRID_SEMANTIC_TOP_K` | `20` | 语义候选数量 |
| `HYBRID_BM25_TOP_K` | `20` | BM25 候选数量 |
| `HYBRID_FINAL_TOP_K` | `5` | 精排最终数量 |
| `RERANK_MODEL` | 空 | 空值使用 Embedding 余弦；非空加载 CrossEncoder |
| `MCP_ENABLED` | `true` | 是否启用 MCP 文件工具 |
| `MCP_DOCUMENT_ROOT` | `data/documents` | MCP 可读取的唯一根目录 |
| `LANGSMITH_TRACING` | `false` | 是否发送 LangGraph 追踪到 LangSmith |
| `PROMPT_PRIMARY_VARIANT` | `phase4-v1` | 主 Prompt Bundle |
| `PROMPT_EXPERIMENT_PERCENTAGE` | `0` | 稳定哈希分流比例，范围 0–100 |
| `MAX_UPLOAD_SIZE_MB` | `50` | 单文件上传上限 |
| `UPLOAD_DIR` | `data/uploads` | 原始上传存储目录 |
| `API_TOKEN` | 空 | 回环开发可为空，远程绑定必须设置 |
| `CORS_ALLOWED_ORIGINS` | 本地 3000/5173 | 精确允许的浏览器 Origin |
| `LOG_LEVEL` / `LOG_DIR` | `INFO` / `log` | 本地日志级别与目录 |

更多 DOCX 解压上限、PDF 页数上限、监控阈值和 LangSmith 参数请直接查看 `backend/app/core/config.py`。

## 安全与数据约束

- 默认只绑定 `127.0.0.1`；不要在没有 Token 和正确 CORS 的情况下暴露到局域网或公网。
- `API_TOKEN` 只允许通过 `X-ResearchMate-Token` 请求头传递，不允许放入 URL。
- 仅接受 PDF/DOCX；上传采用流式大小限制、MIME/签名检查和 DOCX ZIP 安全检查。
- MCP `read_file` 只能读取 `MCP_DOCUMENT_ROOT` 内文件，不提供任意路径或写文件能力。
- `.env`、`.secrets/`、上传文档、向量索引、BM25 索引、日志和备份都属于本地敏感数据。
- 删除或迁移 `backend/data/` 前必须先备份并核对绝对路径；测试使用临时目录。
- Prompt Bundle 在 `backend/app/prompts/registry.py` 中版本化，实验按会话 ID 稳定分流。
- LangSmith 默认关闭；启用后会向配置的远端服务发送追踪数据，应先评估论文与对话隐私。

