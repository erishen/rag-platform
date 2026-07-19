"""全局配置：从环境变量 / .env 读取，全部带默认值。"""
import os

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


class Settings:
    # LLM
    openai_api_key: str = _env("OPENAI_API_KEY", "")
    openai_base_url: str = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
    llm_model: str = _env("LLM_MODEL", "gpt-3.5-turbo")

    # Embedding（双后端：ollama 优先，sentence-transformers 兜底）
    embed_backend: str = _env("EMBED_BACKEND", "ollama")  # ollama | st
    embed_model: str = _env("EMBED_MODEL", "snowflake-arctic-embed2")
    embed_dim: int = int(_env("EMBED_DIM", "1024"))
    ollama_base_url: str = _env("OLLAMA_BASE_URL", "http://localhost:11434")

    # 混合检索
    vector_weight: float = float(_env("VECTOR_WEIGHT", "0.6"))
    bm25_weight: float = float(_env("BM25_WEIGHT", "0.4"))
    top_k: int = int(_env("TOP_K", "4"))

    # 存储（PostgreSQL + pgvector + Redis）
    database_url: str = _env("DATABASE_URL", "postgresql+psycopg://rag:rag@localhost:5432/rag")
    redis_url: str = _env("REDIS_URL", "redis://localhost:6379/0")
    lexicon_path: str = _env("LEXICON_PATH", "./data/lexicon.json")


settings = Settings()
