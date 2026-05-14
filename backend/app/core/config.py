from pydantic_settings import BaseSettings
from typing import Literal
import os


class Settings(BaseSettings):
    APP_NAME: str = "DocMind"
    DEBUG: bool = True

    # Upload settings
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB

    # Database
    DATABASE_URL: str = f"sqlite+aiosqlite:///{os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'docmind.db').replace(os.sep, '/')}"
    # LLM Settings
    LLM_PROVIDER: Literal["openai", "anthropic", "local", "ollama"] = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    LOCAL_MODEL_URL: str = "http://localhost:11434/v1"
    LOCAL_MODEL_NAME: str = "llama3"

    # PageIndex Settings
    MAX_TREE_DEPTH: int = 3      # 降低层级,让表格更扁平
    MAX_LEAF_NODES: int = 100    # 增加节点数,捕获更多细节
    CHUNK_SIZE: int = 500        # 减小块大小,提高精度



settings = Settings()

# Ensure upload directory exists

