from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class PipelineStartRequest(BaseModel):
    duration_minutes: int = 30

class PipelineStatusResponse(BaseModel):
    is_running: bool
    start_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None

class PipelineRunResponse(BaseModel):
    id: int
    pipeline_id: str
    status: str
    current_cycle: int
    total_cycles: int
    articles_processed: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    ended_at: Optional[datetime] = None
    auto_mode: bool
    duration_minutes: int

class AgentUpdateResponse(BaseModel):
    agent: str
    message: str
    timestamp: str
    data: Optional[Dict[str, Any]] = None

class AgentLogResponse(BaseModel):
    id: int
    pipeline_id: str
    agent_name: str
    message: str
    log_level: str
    data: Optional[Dict[str, Any]] = None
    created_at: datetime

class ArticleResponse(BaseModel):
    id: int
    original_title: str
    original_link: str
    generated_content: str
    authenticity_score: Dict[str, Any]
    source: str
    processed_at: datetime
    created_at: datetime
    pipeline_id: Optional[str] = None
    cycle_number: Optional[int] = None

class AdminDashboardStats(BaseModel):
    total_articles: int
    articles_today: int
    pipeline_running: bool
    active_connections: int
    running_pipelines: int
    recent_activity: Dict[str, int]