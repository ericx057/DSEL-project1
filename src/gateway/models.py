from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class AccessTier(str, Enum):
    T1 = "T-1"  # Interface level only
    T2 = "T-2"  # Summary level
    T3 = "T-3"  # Implementation level

class User(BaseModel):
    id: str
    groups: List[str] = Field(default_factory=list)

class QueryRequest(BaseModel):
    query: str
    override_model: Optional[str] = None
    diagram_requested: bool = False

class AuditEvent(BaseModel):
    user_id: str
    access_tier: AccessTier
    query_hash: str
    repo_scope: List[str]
    model_used: str
    latency_ms: float
    cache_hit: bool
    rbac_blocked: bool

class HistoryRecord(BaseModel):
    user_id: str
    query: str
    response: str
    model_used: str
    repo_scope: List[str]
    created_at: float
