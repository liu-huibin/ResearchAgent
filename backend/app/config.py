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
