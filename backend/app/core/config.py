import os
import dotenv
from pydantic_settings import BaseSettings
from typing import Literal

# Load .env file from backend directory
dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

class Settings(BaseSettings):
    APP_NAME: str = "DocMind"
    DEBUG: bool = True
    
    # Upload settings
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./docmind.db"
    
    # LLM Settings
    LLM_PROVIDER: Literal["openai", "anthropic", "local", "ollama"] = "ollama"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    LOCAL_MODEL_URL: str = "http://localhost:11434/v1"
    LOCAL_MODEL_NAME: str = "qwen3.5:9b"
    
    # PageIndex Settings
    MAX_TREE_DEPTH: int = 5
    MAX_LEAF_NODES: int = 50
    CHUNK_SIZE: int = 1000
    
    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

# Ensure upload directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
