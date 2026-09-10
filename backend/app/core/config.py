from urllib.parse import quote_plus
import ssl
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "researchmate_app"
    mysql_password: str = ""
    mysql_password_file: str = ""
    mysql_database: str = "research_mate"
    mysql_require_tls: bool = True
    mysql_ssl_ca: str = ""
    mysql_ssl_cert: str = ""
    mysql_ssl_key: str = ""
    mysql_ssl_verify: bool = True

    llm_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model_name: str = "qwen-plus"

    # Browser/API boundary.  A token is optional for loopback-only development,
    # but run_backend.py requires a strong token before binding a remote host.
    api_token: str = ""
    cors_allowed_origins: str = (
        "http://127.0.0.1:3000,http://localhost:3000,"
        "http://127.0.0.1:5173,http://localhost:5173"
    )

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
    max_docx_entries: int = 2000
    max_docx_uncompressed_mb: int = 100
    max_docx_compression_ratio: int = 100
    max_pdf_pages: int = 2000
    max_extracted_chars: int = 2_000_000
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

    @field_validator("api_token")
    @classmethod
    def validate_api_token(cls, value: str) -> str:
        if value and len(value) < 32:
            raise ValueError("API_TOKEN must contain at least 32 characters")
        return value

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        return tuple(
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        )

    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{quote_plus(self.mysql_user)}:"
            f"{quote_plus(self.effective_mysql_password)}@{self.mysql_host}:"
            f"{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def effective_mysql_password(self) -> str:
        if not self.mysql_password_file:
            return self.mysql_password
        password_path = Path(self.mysql_password_file).expanduser()
        if not password_path.is_absolute():
            password_path = Path(__file__).resolve().parents[2] / password_path
        return password_path.read_text(encoding="utf-8").strip()

    @property
    def database_connect_args(self) -> dict:
        if not self.mysql_require_tls:
            return {}
        ca_path = self._backend_path(self.mysql_ssl_ca) if self.mysql_ssl_ca else None
        context = ssl.create_default_context(cafile=str(ca_path) if ca_path else None)
        if not self.mysql_ssl_verify:
            context.check_hostname = False
        if self.mysql_ssl_cert:
            context.load_cert_chain(self.mysql_ssl_cert, self.mysql_ssl_key or None)
        return {"ssl": context}

    @staticmethod
    def _backend_path(value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else Path(__file__).resolve().parents[2] / path

    model_config = {
        "env_file": str(Path(__file__).resolve().parents[2] / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()
