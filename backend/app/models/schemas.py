from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


# ── User / Auth schemas ────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    email: Optional[str] = None
    display_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None


class TokenResponse(BaseModel):
    token: str
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=128)


# ── Document schemas ───────────────────────────────────────────────────

# Document schemas
class DocumentBase(BaseModel):
    name: str

class DocumentCreate(DocumentBase):
    pass

class IndexNode(BaseModel):
    id: str
    title: str
    page_start: int
    page_end: int
    level: int
    children: List["IndexNode"] = []
    
    class Config:
        arbitrary_types_allowed = True

class DocumentResponse(BaseModel):
    id: str
    name: str
    file_type: str
    file_size: int
    page_count: int
    index_status: Literal["pending", "indexing", "ready", "error"]
    user_id: Optional[str] = None
    index_tree: Optional[IndexNode] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int

# Conversation schemas
class MessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    references: Optional[List[dict]] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class ConversationResponse(BaseModel):
    id: str
    title: str
    user_id: Optional[str] = None
    chat_type: Optional[str] = "doc_chat"
    document_id: Optional[str] = None
    messages: List[MessageResponse] = []
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ConversationListResponse(BaseModel):
    conversations: List[ConversationResponse]
    total: int

# Chat schemas
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    document_id: Optional[str] = None
    chat_type: Optional[Literal["doc_chat", "general"]] = None
    stream: bool = True

class ChatResponse(BaseModel):
    conversation_id: str
    message: MessageResponse

# Memory schemas
class MemoryCreate(BaseModel):
    content: str
    category: Literal["daily", "long_term", "preference", "decision", "lesson"] = "daily"
    source: Optional[str] = "manual"
    source_id: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: int = Field(default=5, ge=1, le=10)

class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: Optional[int] = Field(default=None, ge=1, le=10)
    is_archived: Optional[int] = Field(default=None, ge=0, le=1)

class MemoryResponse(BaseModel):
    id: str
    user_id: str
    category: str
    content: str
    source: Optional[str] = None
    source_id: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: int
    is_archived: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class MemoryListResponse(BaseModel):
    memories: List[MemoryResponse]
    total: int

class MemoryStatsResponse(BaseModel):
    total: int
    by_category: dict[str, int]
    archived: int
    active: int

# Index schemas
class IndexStatusResponse(BaseModel):
    document_id: str
    status: Literal["pending", "indexing", "ready", "error"]
    progress: Optional[int] = None
    started_at: Optional[datetime] = None
    error_message: Optional[str] = None

IndexNode.model_rebuild()

# ── Admin schemas ──

class UserToggleBody(BaseModel):
    action: Literal["activate", "deactivate", "grant_admin", "revoke_admin"]


# ── Token usage schemas ──

class TokenUsageResponse(BaseModel):
    id: str
    user_id: str
    username: Optional[str] = None
    conversation_id: Optional[str] = None
    model_name: Optional[str] = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TokenSummaryResponse(BaseModel):
    total_prompt: int
    total_completion: int
    total_all: int
    turn_count: int
    daily: List[dict]


# ========== API Registration Schemas ==========
from pydantic import ConfigDict


class ApiDefinitionBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    base_url: str = Field(..., min_length=1, max_length=500)
    method: str = "GET"
    path: str = "/"
    headers: dict = Field(default_factory=dict)
    body_schema: dict = Field(default_factory=dict)
    auth_type: str = "none"
    auth_header: str = ""
    timeout_ms: int = 30000


class ApiDefinitionCreate(ApiDefinitionBase):
    pass


class ApiDefinitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    base_url: str | None = None
    method: str | None = None
    path: str | None = None
    headers: dict | None = None
    body_schema: dict | None = None
    auth_type: str | None = None
    auth_header: str | None = None
    timeout_ms: int | None = None
    enabled: bool | None = None
    example_queries: list[str] | None = None
    expected_response: dict | None = None


class ApiDefinitionResponse(ApiDefinitionBase):
    id: str
    enabled: int
    example_queries: list[str] = []
    expected_response: dict = {}
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str = ""

    model_config = ConfigDict(from_attributes=True)


class SerialChainBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    members: list["ChainMemberCreate"] = []


class SerialChainCreate(SerialChainBase):
    pass


class ChainMemberCreate(BaseModel):
    order: int
    api_id: str
    input_mapping: dict = Field(default_factory=dict)
    output_mapping: dict = Field(default_factory=dict)


class ChainMemberResponse(BaseModel):
    id: str
    order: int
    api_id: str
    api_name: str
    input_mapping: dict = {}
    output_mapping: dict = {}
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SerialChainResponse(BaseModel):
    id: str
    name: str
    description: str
    steps_count: int
    enabled: int
    members: list[ChainMemberResponse] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str = ""

    model_config = ConfigDict(from_attributes=True)


class ApiUsageLogCreate(BaseModel):
    chain_id: str | None = None
    api_id: str | None = None
    request_payload: dict = Field(default_factory=dict)
    response_payload: dict = Field(default_factory=dict)
    status_code: int | None = None
    duration_ms: int | None = None
    error: str = ""


class ApiUsageLogResponse(BaseModel):
    id: str
    chain_id: str | None
    api_id: str | None
    status_code: int | None
    duration_ms: int | None
    error: str
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class IntentSuggestion(BaseModel):
    type: str  # "api" or "chain"
    confidence: float
    target_id: str | None = None
    target_name: str
    explanation: str
    example_queries: list[str] = []


class ChainExecuteRequest(BaseModel):
    input_data: dict = Field(default_factory=dict)


class ChainExecuteResponse(BaseModel):
    chain_id: str
    chain_name: str
    status: str  # "success" | "partial" | "failed"
    steps: list[dict]
    total_duration_ms: int
    error: str = ""


SerialChainBase.model_rebuild()


class ChatResponseWithSuggestions(BaseModel):
    """Chat response with API suggestions."""
    conversation_id: str
    message: dict  # Message as dict
    intent: IntentSuggestion | None = None
    api_suggestions: list[IntentSuggestion] = []

