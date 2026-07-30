from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "research_mate"

    llm_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model_name: str = "qwen-plus"

    agent_max_iterations: int = 10
    agent_timeout_seconds: int = 120

    # Phase 5: MCP file tool. Relative paths are resolved from the backend cwd.
    mcp_enabled: bool = True
    mcp_document_root: str = "data/documents"
    mcp_start_timeout_seconds: int = 15

    # Phase 5: LangSmith is optional at runtime. When disabled or unconfigured,
    # local metrics remain available and the chat workflow is unaffected.
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "researchmate"

    # Prompt bundles are versioned in app.prompts.registry. A/B assignment is
    # deterministic per session, which makes experiments reproducible.
    prompt_primary_variant: str = "phase4-v1"
    prompt_experiment_variant: str = "phase5-concise-v1"
    prompt_experiment_percentage: int = 0

    # Local warning thresholds (observability remains useful without a remote
    # monitoring stack).
    monitor_iteration_warning: int = 8
    monitor_tool_failure_rate_warning: float = 0.2
    monitor_duration_warning_ms: int = 90000

    max_upload_size_mb: int = 50
    upload_dir: str = "data/uploads"

    embedding_model: str = "text-embedding-v4"
    chroma_persist_dir: str = "data/chroma"
    chunk_size: int = 500
    chunk_overlap: int = 50
    retrieval_top_k: int = 5
    hybrid_semantic_top_k: int = 20
    hybrid_bm25_top_k: int = 20
    hybrid_final_top_k: int = 5
    bm25_persist_dir: str = "data/bm25"
    rerank_model: str = ""  # empty = use embedding cosine similarity for rerank
    rerank_api_url: str = ""  # optional: dedicated rerank API endpoint

    log_level: str = "INFO"
    log_dir: str = "log"

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
