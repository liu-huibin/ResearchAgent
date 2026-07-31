# ResearchMate 智能体问答型 KMS 开发计划

> 版本：V1.0  
> 编制日期：2026-07-31  
> 依据：`KMS文档/ResearchMate智能体问答型KMS需求规格说明书_V1.1_正式冻结稿.docx`、`KMS文档/ResearchMate智能体问答型KMS总体设计报告_V1.1_正式冻结稿.docx`  
> 适用范围：KMS 首期 P0 功能；单课题组共享空间，固定 `user_id=1`

## 1. 计划目标

在保留现有会话、消息、Multi-Agent、MCP、RAG 和可观测性能力的前提下，增加以 `paper_id` 为核心的论文资产层，完成以下闭环：

1. PDF/DOCX 上传、处理、题名/作者搜索、详情、编辑、下载、回收站和恢复。
2. 论文详情/阅读页右侧的单篇论文 Agent 问答。
3. 整个论文库问答，并保存论文名、PDF 页码或 DOCX 章节/段落来源。
4. 论文关联历史会话、继续最近会话和手动选择历史会话。
5. 文档处理可重试、可恢复、可观测；满足首期容量与并发目标。

本计划将总体设计中的 6 个工作包合并为 4 个迭代。每个迭代都必须形成可独立运行、可自动化测试、可人工验收、可回滚的交付物；前一迭代未通过退出门禁，不进入下一迭代。

## 2. 冻结范围

### 2.1 首期包含

- 论文资产：`papers`、`paper_files`、`paper_authors`、`paper_chunks`。
- 处理任务：`ingestion_jobs`，Redis + Celery Worker，默认处理并发 2。
- 会话及引用：`session_documents`、`message_citations`。
- PDF/DOCX，单文件不超过 50 MB；重复文件返回已有 `paper_id`。
- MySQL 元数据搜索、Chroma 向量检索、Whoosh 增量词法索引。
- 当前实际的 `text-embedding-v4` Embedding 与余弦重排。
- 单篇论文问答、全库问答、执行状态、引用展示和历史会话。
- 30 天回收站、恢复、定时物理清理。
- 2,000 篇设计容量、500 篇先导验证、10 名并发用户、5 路 Agent、2 路文档处理。

### 2.2 首期不包含

- 多论文选择、对比以及一个会话同时分析多篇论文的前端能力。
- 引用点击跳页、精确句子高亮。
- 知识成果中心及成果保存正式 API；只允许保留表结构占位。
- 多用户、课题组、角色和权限隔离。
- 旧版二进制 DOC。
- 拼音、作者缩写、拼写纠错、同名作者消歧。
- 启用 CrossEncoder 或宣称已使用 `bge-reranker-v2-m3`。
- 独立监控大屏、Prometheus/Grafana。

## 3. 现有环境复用策略

### 3.1 直接复用

| 现有能力 | 复用方式 |
|---|---|
| Conda 环境 `ResearchAgent` | 继续作为唯一后端开发和验证环境，不新建 Python 环境。 |
| React 19 + TypeScript 6 + Vite 8 + Tailwind CSS 4 | 在现有 `frontend` 内新增论文库路由和自定义组件，不引入第二套前端或 UI 组件库。 |
| FastAPI + SQLModel + 异步 SQLAlchemy + aiomysql | 继续作为 API、领域模型和 MySQL 访问层。 |
| `sessions`、`messages`、`documents`、`workflow_runs` | 保留字段和旧接口；通过新增表和兼容关系扩展，不直接删除旧数据。 |
| LangGraph Multi-Agent | 复用 Supervisor、ReaderAgent、IdeationAgent、ReviewerAgent、Prompt 版本和最大迭代限制。 |
| SSE 消息链路 | 增加 `stage`、`tool`、`tool_result`、`citation` 事件，保持现有 `token/metrics/done/error` 兼容。 |
| Chroma | 使用新的 KMS 元数据和稳定 `vector_id`；迁移期间保留旧集合以便回滚。 |
| `text-embedding-v4` | 同时用于向量化和现有余弦重排，不新增 Rerank 服务。 |
| `rank_bm25` 接口 | 仅作为 Whoosh 迁移期兼容和回退，不继续扩展全量重建实现。 |
| MCP `read_file` | 保留显式路径工具；KMS 主问答改走 PaperService/RetrievalService。 |
| LangSmith 与本地指标 | LangSmith 继续默认关闭；`workflow_runs`、`messages.tool_calls` 和日志仍是本地权威数据。 |
| `run_backend.py`、`run_frontend.py` | 保留根目录启动方式；新增 Worker 启动脚本时保持相同使用习惯。 |
| `unittest`、前端 lint/build | 继续作为自动化门禁，不为首期额外引入 pytest 或新的前端测试框架。 |

### 3.2 最小新增项

仅新增冻结设计所必需的依赖，并在 `ResearchAgent` 中完成真实导入和最小运行测试后锁定版本：

- Redis：Celery broker/result backend。
- Celery：文档解析、Embedding、索引、重处理和物理清理。
- Whoosh：持久化增量词法索引。
- Alembic：KMS 新表的版本化升级和回滚；`init_db.sql` 继续用于全新环境初始化。

本地 Windows 开发优先复用现有 Conda 环境；Celery 使用 Windows 可运行的线程池或等价开发模式验证 `concurrency=2`。部署环境再使用 Linux/容器的标准 Worker 池。不得为了本功能更换 MySQL、Chroma、前端框架、Agent 框架或 LLM 供应商。

## 4. 全程开发与验证规则

### 4.1 数据安全

- 迁移不得删除或覆盖旧 `documents`、旧 Chroma 集合和 BM25 pickle。
- 数据迁移必须先提供预检查、备份说明、执行脚本、结果核对和回滚脚本。
- 文件、索引和数据库的跨资源操作必须可补偿；失败时不得留下“数据库成功但文件/索引缺失”的不可解释状态。
- API Key、数据库密码、Redis 地址和 LangSmith Key 只从环境变量读取，测试和日志不得打印密钥或论文全文。

### 4.2 每个迭代的共同门禁

每个迭代结束时至少完成：

```powershell
cd backend
conda run -n ResearchAgent python -B -m unittest discover -s tests -v

cd ../frontend
npm.cmd run lint
npm.cmd run build

cd ..
git diff --check
```

同时满足：

- 新功能有单元测试；跨 MySQL/Chroma/Whoosh/Redis/Celery 的功能有真实集成测试。
- 不依赖仅 Mock 的 Agent 工厂测试掩盖真实依赖/API 不兼容。
- 测试数据使用独立数据库、独立索引目录和临时文件目录，不污染历史论文和会话。
- `.pyc`、日志、临时上传、测试 Chroma/Whoosh、Celery 结果等不进入交付变更。
- 旧会话、旧消息、现有知识库接口和现有 Agent 基础回归测试保持通过。

## 5. 开发前置门禁（不计入阶段数）

由于冻结稿编制时本机 MySQL 未启动，本门禁完成前不得执行正式数据库迁移。

### 工作内容

1. 启动并只读连接实际 MySQL，导出：数据库版本、字符集、表、字段、索引、外键、行数和数据量。
2. 对比实际实例、SQLModel 模型和 `backend/init_db.sql`，形成差异清单。
3. 完成数据库全量备份，并验证备份文件可读取；记录恢复命令但不在生产库试执行。
4. 盘点现有 `documents.type=knowledge`、文件路径、MD5 重复情况、Chroma 切片数量和 BM25 corpus 数量。
5. 在 `ResearchAgent` 中验证 Redis/Celery/Whoosh/Alembic 的兼容版本；写入 `backend/requirements.txt` 前必须完成最小导入、任务执行、索引写入/查询和迁移 smoke test。
6. 记录当前后端、前端和真实 Qwen/SSE 冒烟基线；API Key 只从现有环境变量读取且不得输出。

### 通过标准

- 有实际数据库结构核验结果和可恢复备份。
- 明确旧知识库文档、文件与索引的数量关系及异常项。
- 新依赖在 `ResearchAgent` 中可真实运行，而不只是 `pip check` 通过。
- 当前所有后端测试、前端 lint/build 及一轮真实问答冒烟通过。

## 6. 迭代 A：数据与迁移底座

### 目标

在不改变现有用户功能的情况下，建立 KMS 数据模型、存储边界和可回滚迁移能力。完成后虽然尚未开放论文库页面，但数据层和迁移链路可独立验收。

### 开发内容

1. 引入 Alembic，建立现有 schema 基线和 KMS 迁移版本。
2. 新增 SQLModel 模型、Schema、Repository：
   - `papers`
   - `paper_files`
   - `paper_authors`
   - `paper_chunks`
   - `ingestion_jobs`
   - `session_documents`
   - `message_citations`
3. 为 `knowledge_artifacts`、`artifact_papers` 只创建预留迁移或占位模型，不创建前端和正式业务 API。
4. 落实关键约束：
   - 首期 `UNIQUE(user_id, file_md5)`。
   - 同一论文仅一个当前文件版本。
   - 首期同一会话仅一个 `is_primary=true` 的论文。
   - 删除时间、`purge_after`、处理状态、版本号和引用关系索引。
5. 新增 `StorageService`：只保存相对路径；统一根目录、路径规范化、越界校验、临时文件和原子移动。
6. 新增只读迁移扫描与正式迁移脚本：
   - 扫描 `documents.type=knowledge`。
   - 按 MD5 去重生成 `papers/paper_files`。
   - 为旧会话 `active_document_id` 生成兼容 `session_documents`。
   - 不删除旧记录、文件或索引。
7. 增加 KMS 配置项及启动时配置校验；缺少 Redis 等非本迭代运行项时给出明确错误，不影响旧功能回归。

### 独立验证

- 在全新临时 MySQL 数据库执行 upgrade 两次，第二次无重复表、索引或外键错误。
- 在包含旧表和样例数据的临时数据库执行迁移，核对迁移前后旧表行数、KMS 行数和 MD5 映射。
- 执行 downgrade/回滚，确认旧表、旧数据、旧 Chroma 和旧 BM25 完整保留。
- 对 StorageService 执行路径穿越、同名文件、异常中断和原子移动测试。
- Repository 完成 CRUD、唯一性、事务回滚和并发判重测试。

### 退出门禁

- 数据库迁移报告、回滚报告和模型字段清单齐全。
- 当前前后端功能无可见变化且全部旧回归通过。
- 正式迁移仍保持关闭，只有显式运维命令可以执行。

## 7. 迭代 B：论文资产中心与入库检索

### 目标

交付一个不依赖 Agent 也可完整使用的论文资产中心：论文能安全入库、处理、搜索、查看、编辑、下载、删除、恢复和重新处理。

### 开发内容

#### 7.1 后端与异步处理

1. 新增 Redis + Celery 应用和根目录 Worker 启动脚本；默认处理并发 2。
2. 实现 `/api/kms/papers` 系列 API：上传、列表、详情、元数据编辑、下载、删除、恢复、重新处理。
3. 上传采用流式临时文件并同步计算 MD5，校验：
   - 扩展名只允许 PDF/DOCX。
   - 大小不超过 50 MB。
   - MIME 和基础文件结构有效；PDF 校验签名，DOCX 校验 ZIP/OOXML 结构。
   - 重复文件删除临时文件并返回已有 `paper_id`。
4. 通过 Celery 编排解析、元数据提取、切片、Embedding、Chroma 写入和 Whoosh 写入；API 快速返回 `paper_id` 和处理状态。
5. 升级解析器：
   - PDF 切片保存 `page_start/page_end`。
   - DOCX 切片保存 `section_title/paragraph_index`，不伪造稳定页码。
6. `ingestion_jobs` 持久化步骤、进度、耗时、重试次数和结构化错误。
7. 实现幂等重处理：稳定 `vector_id`、Whoosh 唯一键、旧版本范围清理和 `content_hash` 检测。
8. 只对 429、5xx、连接超时等瞬时错误指数退避，默认最多 3 次；文件损坏、空文本和不支持格式不自动重试。
9. 实现 `SearchService`：题名/作者连续子串、大小写不敏感、trim、分页、排序，并排除回收站和不可用论文。
10. 新增 `LexicalIndexRepository` 和 Whoosh 增量索引；保留 rank_bm25 兼容层，完成双读对比后再切换主索引。
11. 实现回收站：软删除、恢复、每日过期扫描、物理清理顺序及 `source_available=false` 处理。

#### 7.2 前端

1. 新增论文库首页：上传、进度、综合搜索、题名/作者条件、分页、排序和状态展示。
2. 新增论文详情/阅读页：元数据、文件信息、处理状态、编辑、下载和现有 PDF/DOCX 阅读器复用。
3. 新增回收站页面：删除时间、预计清理时间和恢复操作。
4. 对重复文件、格式错误、大小超限、处理中、部分可用、失败和重新处理提供明确反馈。
5. 继续使用现有 Tailwind 和自定义组件，不引入新的组件库或全局状态库；URL 保存搜索和分页参数。

### 独立验证

- 从上传到 `READY` 完成一条真实 PDF 和一条真实 DOCX 全链路。
- 同一文件重复上传返回相同 `paper_id`，不产生第二个逻辑论文、文件或索引副本。
- 伪造扩展名、错误 MIME、损坏文件、空文本、超过 50 MB 和路径穿越均被拒绝。
- 题名任意连续子串、作者大小写不敏感和 trim 搜索通过；分页和排序稳定。
- 下载响应恢复原始文件名，文件哈希与上传源一致。
- 删除后论文从列表、搜索、Chroma 和 Whoosh 查询中不可见；恢复后重新可见，缺失索引时自动提交重建。
- 模拟 Embedding 429、Worker 中断和 Whoosh 写入失败，任务状态、重试计数和错误信息正确；重跑无重复切片。
- Whoosh 与旧 BM25 对固定问题集完成双读差异报告，达到冻结稿确认的召回要求后才能切换。

### 对应验收项

`AC-01`～`AC-05`、`AC-10`，以及 `AC-12` 中的 `ingestion_jobs` 可查询部分。

### 退出门禁

- 不启动 Agent 也可以完成论文资产完整闭环。
- 所有处理任务可查、可重跑、可恢复；Web 进程不执行重型入库任务。
- 旧知识库接口仍可读，旧索引仍可回退。

## 8. 迭代 C：Agent 融合与问答交互

### 目标

把 KMS 论文资产稳定接入现有 LangGraph 工作流，完成单篇问答、全库问答、引用和论文历史会话闭环，并确保检索范围不会被 Agent 自行扩大。

### 开发内容

1. 实现 `PaperService`、`RetrievalService`、`CitationService`、`SessionDocumentService`。
2. 实现确定性的 `ContextResolver`，在进入 LangGraph 前生成并校验：
   - `current_paper`：只允许当前 `paper_id`。
   - `library`：只允许所有未删除且可检索论文。
3. 新增或改造工具：`get_paper_metadata`、`search_current_paper`、`search_library`、`read_paper_chunk/page`；工具的 scope 由服务端注入，模型不能修改。
4. KMS 主问答不再无条件把整篇正文拼入 Prompt；现有 MCP `read_file` 仅保留显式路径场景。
5. 复用现有 Supervisor、ReaderAgent、IdeationAgent、ReviewerAgent、Prompt 版本、A/B 分流、超时和最大迭代限制。
6. 保存 `session_documents` 和 `message_citations`；PDF 引用保存论文名、页码和 chunk，DOCX 保存论文名、章节/段落来源。
7. 扩展 SSE：发送阶段、工具状态、工具摘要、引用、Token 和最终状态；保留旧事件兼容。
8. 前端把原“思考过程”改为执行状态卡片，不展示或保存模型原始私有推理。
9. 论文详情页右侧复用现有 ChatPanel；提供新建会话、论文关联历史会话、继续最近会话和选择指定会话。
10. 保留 `/library-chat` 全库问答入口，不增加多论文选择/对比模式。
11. 加入 `asyncio.Semaphore`，默认最多 5 路 Agent；繁忙时返回 `AGENT_BUSY`。
12. 失败策略：
    - 首个 token 前的 LLM 429/5xx/连接错误最多重试 2 次。
    - 首个 token 后不自动重放整轮请求。
    - 仅幂等工具允许自动重试；失败写入 `messages.tool_calls` 和 `workflow_runs`。
    - SSE 中断后前端重新拉取消息和运行状态，不重复发送用户问题。

### 独立验证

- 使用确定性测试数据证明单篇问答只能返回当前 `paper_id` 的切片，即使问题明确要求另一篇论文也不能越界。
- 全库问答可召回多篇论文，引用能区分论文名和页码/章节，回收站论文不参与检索。
- 新建会话只产生一条主要论文绑定；历史会话按最后活跃时间排序，用户可继续指定会话且消息不串会话。
- PDF 引用必须有真实页码；DOCX 无页码时回退章节/段落且不伪造页码。
- 前端仅展示执行阶段和工具摘要，接口与数据库不新增原始思维链内容。
- 模拟 LLM 首 token 前失败、首 token 后失败、SSE 断开、MCP 不可用和达到 5 路并发上限，行为符合失败策略。
- Mock 测试通过后，在现有 API Key 环境中执行一条真实 Qwen + SSE + MySQL + Chroma + Whoosh 端到端冒烟；不得输出密钥。

### 对应验收项

`AC-06`～`AC-09`，以及 `AC-12` 中的 workflow、Token、工具和引用数据。

### 退出门禁

- 单篇和全库两类范围均有不可绕过的服务端测试。
- 问答结束后 message、citation、workflow_run 可通过 ID 相互追踪。
- 旧会话问答仍可使用；MCP 不可用不影响 KMS 主问答。

## 9. 迭代 D：容量、故障、迁移与发布验收

### 目标

完成历史数据迁移、性能与并发验证、故障和回滚演练，并按 `AC-01`～`AC-12` 形成可发布证据。该迭代不增加新的业务范围。

### 开发内容

1. 在备份后执行历史 `documents.type=knowledge` 迁移：
   - 生成 KMS 论文、文件、作者、切片和会话关系。
   - 新建 KMS Chroma 集合和 Whoosh 索引。
   - 双写/双读观察期间保持旧接口可读；新上传只写 KMS。
2. 完成 500 篇先导导入和 2,000 篇容量数据集测试；记录数据构成、索引大小、构建时长和查询结果。
3. 使用现有 Python `asyncio/httpx` 编写可重复压测脚本，避免仅为首期引入 Locust：
   - 10 名并发用户混合场景。
   - 至少 5 路 Agent 持续问答 10 分钟。
   - 2 路上传/解析/索引任务并行。
   - 典型检索 P95 不高于 1.5 秒。
4. 故障演练：Embedding 429/5xx、Redis 短暂不可用、Worker 重启、Chroma/Whoosh 写失败、SSE 中断、MCP 不可用、MySQL 短暂连接失败。
5. 安全验证：路径穿越、伪造 MIME、超大文件、回收站论文读取、物理删除后的引用访问和敏感日志扫描。
6. 完善文档处理指标：排队时间、执行时间、成功率、失败步骤、重试次数、Embedding/索引失败率和清理数量。
7. 执行迁移回滚演练：恢复旧 Agent 检索路径，确认旧 documents、旧 Chroma 和旧 BM25 可继续使用。
8. 完成配置、启动、迁移、备份恢复、Worker、索引重建、回收站清理和故障处理运行手册。

### 独立验证

- 对 `AC-01`～`AC-12` 逐项执行并形成“需求编号—测试用例—证据—结果”追踪矩阵。
- 500/2,000 篇两档测试、10 用户混合负载、5 Agent、2 Worker 均有可重复脚本和结果报告。
- 并发期间无 session/paper 数据串扰，无重复消息、重复切片和跨范围引用。
- Worker 和 Web 进程重启后，PENDING/RUNNING/RETRYING 任务可恢复或安全重跑。
- 在不删除新表的情况下切回旧检索路径成功；必要时可执行数据库 downgrade。
- 完成一次从备份恢复到临时数据库的演练，确认备份真实可用。

### 对应验收项

`AC-01`～`AC-12` 全量回归，重点关闭 `AC-11` 并发和 `AC-12` 可观测性。

### 发布门禁

- 所有 P0 验收项通过，没有未解释的数据差异或越界检索。
- 无阻断级安全、迁移、回滚和数据一致性缺陷。
- 新旧检索切换开关、回滚条件和责任人明确。
- 运行手册和测试证据齐全后，才允许将 KMS 检索设为默认路径。

## 10. 阶段依赖与交付顺序

```text
开发前置门禁
    ↓
迭代 A：数据与迁移底座
    ↓
迭代 B：论文资产中心与入库检索
    ↓
迭代 C：Agent 融合与问答交互
    ↓
迭代 D：容量、故障、迁移与发布验收
```

- 迭代 A 不依赖 Redis/Worker 持续运行，可单独验证数据库和存储边界。
- 迭代 B 不依赖 Agent，可单独作为论文资产管理系统验收。
- 迭代 C 复用迭代 B 已稳定的 Paper/Retrieval 服务，可单独验证问答范围和引用。
- 迭代 D 不增加业务功能，只对已完成能力进行规模化验证和发布收口。

## 11. 建议工作量

以下为单人连续开发的粗略工作量，不作为固定交付日期；完成数据库前置核验后再调整：

| 迭代 | 建议工作量 | 主要不确定性 |
|---|---:|---|
| 前置门禁 | 1～3 人日 | 实际 MySQL、历史文件和索引一致性。 |
| 迭代 A | 4～6 人日 | 现有 schema 差异、循环外键和迁移回滚。 |
| 迭代 B | 10～15 人日 | Celery/Redis、解析页码、Whoosh 迁移及前端页面。 |
| 迭代 C | 8～12 人日 | Agent 范围控制、引用持久化和 SSE 兼容。 |
| 迭代 D | 5～8 人日 | 语料准备、性能瓶颈和故障演练。 |

若多人并行，数据库迁移、Chroma/Whoosh 写入和 Agent/SSE 仍需由单一负责人控制集成顺序，避免共享数据目录被并发修改。

## 12. 需求与迭代追踪

| 需求/验收范围 | 迭代 A | 迭代 B | 迭代 C | 迭代 D |
|---|:---:|:---:|:---:|:---:|
| 数据模型、迁移、回滚 | 主交付 | 增量 | 引用/会话增量 | 正式迁移与回滚演练 |
| AC-01～AC-05 上传、详情、搜索、下载 | 基础表 | 主交付 | 回归 | 全量验收 |
| AC-06～AC-09 Agent、全库、引用、会话 | 数据预留 | 服务准备 | 主交付 | 全量验收 |
| AC-10 回收站 | 字段和约束 | 主交付 | 检索排除 | 清理与恢复演练 |
| AC-11 并发 | 事务测试 | 2 路处理初测 | 5 路 Agent 初测 | 主验收 |
| AC-12 可观测性 | 模型/字段 | ingestion 指标 | Agent/引用追踪 | 主验收 |

## 13. 完成定义

KMS 首期只有在以下条件全部满足时才视为完成：

1. 两份 V1.1 正式冻结稿中的所有 P0 需求均有实现或明确的“不在首期”映射。
2. `AC-01`～`AC-12` 全部通过并有可重复验证证据。
3. 旧会话、旧消息、旧知识库数据和旧索引未被不可逆破坏。
4. 单篇问答范围不可越界，全库问答引用可区分来源，回收站论文不参与 RAG。
5. 500/2,000 篇、10 用户、5 Agent、2 Worker 的目标完成验证，或遗留差距经正式批准并写入发布限制。
6. 数据库、文件、Chroma、Whoosh、Redis/Celery 的备份、恢复、重建和回滚流程均已演练。
7. 后端测试、前端 lint/build、真实端到端冒烟、安全检查和迁移检查全部通过。

