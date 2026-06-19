from enum import Enum
from typing import List
from pydantic import BaseModel, ConfigDict, Field

class AccessTier(str, Enum):
    T1 = "T-1"  # Interface level only
    T2 = "T-2"  # Summary level
    T3 = "T-3"  # Implementation level

class User(BaseModel):
    id: str
    groups: List[str] = Field(default_factory=list)

class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    diagram_requested: bool = False
    response_mode: str = Field(default="summary", pattern="^(summary|paragraph|deep)$")

class AuditEvent(BaseModel):
    user_id: str
    access_tier: AccessTier
    query_hash: str
    repo_scope: List[str]
    inference_engine_used: str
    latency_ms: float
    cache_hit: bool
    rbac_blocked: bool

class HistoryRecord(BaseModel):
    user_id: str
    query: str
    response: str
    inference_engine_used: str
    repo_scope: List[str]
    created_at: float
