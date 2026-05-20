from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()

def generate_id():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_id)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, default=0)
    page_count = Column(Integer, default=0)
    index_status = Column(String, default="pending")  # pending, indexing, ready, error
    index_progress = Column(Integer, default=0)  # 0-100 progress when indexing
    index_started_at = Column(DateTime, nullable=True)  # when indexing began
    index_tree = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)  # 文档所有者
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    conversations = relationship("Conversation", back_populates="document", cascade="all, delete-orphan")

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True, default=generate_id)
    title = Column(String, default="New Conversation")
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    chat_type = Column(String, default="doc_chat")  # doc_chat | general
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    document = relationship("Document", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=generate_id)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    references = Column(JSON, nullable=True)  # [{page, text, score}]
    meta = Column(JSON, nullable=True)  # 意图分析结果等
    created_at = Column(DateTime, default=datetime.utcnow)
    
    conversation = relationship("Conversation", back_populates="messages")

class Memory(Base):
    """User memory entry — similar to OpenClaw's memory system."""
    __tablename__ = "memories"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category = Column(String, nullable=False)  # daily | long_term | preference | decision | lesson
    content = Column(Text, nullable=False)
    source = Column(String, nullable=True)  # chat_message | system | manual
    source_id = Column(String, nullable=True)  # associated message_id etc.
    tags = Column(JSON, nullable=True)  # tag list
    importance = Column(Integer, default=5)  # 1-10 importance
    is_archived = Column(Integer, default=0)  # 0=active, 1=archived
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="memories")


class Setting(Base):
    """Key-value settings stored in SQLite. Survives restarts."""
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TokenUsage(Base):
    """Token consumption per user per chat turn."""
    __tablename__ = "token_usages"

    id = Column(String, primary_key=True, default=generate_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ============ API Registration Models ============


class ApiDefinition(Base):
    __tablename__ = "api_definitions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, default="")
    base_url = Column(String(500), nullable=False)
    method = Column(String(10), default="GET")  # GET, POST, PUT, DELETE, PATCH
    path = Column(String(500), default="/")
    headers = Column(Text, default="{}")  # JSON string
    body_schema = Column(Text, default="{}")  # JSON string
    auth_type = Column(String(20), default="none")  # none, bearer, basic, api_key
    auth_header = Column(String(100), default="")
    timeout_ms = Column(Integer, default=30000)
    enabled = Column(Integer, default=1)
    example_queries = Column(Text, default="[]")  # JSON string
    expected_response = Column(Text, default="{}")  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(100), default="admin")


class SerialChain(Base):
    __tablename__ = "serial_chains"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, default="")
    steps_count = Column(Integer, default=0)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(100), default="admin")
    
    members = relationship("SerialChainMember", back_populates="chain", cascade="all, delete-orphan")


class SerialChainMember(Base):
    __tablename__ = "serial_chain_members"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chain_id = Column(String, ForeignKey("serial_chains.id"), nullable=False, index=True)
    order = Column(Integer, nullable=False)  # 1, 2, 3...
    api_id = Column(String, ForeignKey("api_definitions.id"), nullable=False)
    input_mapping = Column(Text, default="{}")  # JSON string, how to map previous output to this input
    output_mapping = Column(Text, default="{}")  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)
    
    chain = relationship("SerialChain", back_populates="members")
    api = relationship("ApiDefinition")


class ApiUsageLog(Base):
    __tablename__ = "api_usage_logs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chain_id = Column(String, ForeignKey("serial_chains.id"), nullable=True)
    api_id = Column(String, ForeignKey("api_definitions.id"), nullable=True)
    request_payload = Column(Text, default="{}")
    response_payload = Column(Text, default="{}")
    status_code = Column(Integer)
    duration_ms = Column(Integer)
    error = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
