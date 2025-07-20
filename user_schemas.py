from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

class UserArticleRequest(BaseModel):
    interests: Optional[List[str]] = Field(default_factory=list, description="User interests/keywords")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=10, ge=1, le=100, description="Articles per page")
    source_filter: Optional[str] = Field(default=None, description="Filter by specific source")
    date_from: Optional[datetime] = Field(default=None, description="Filter articles from this date")
    date_to: Optional[datetime] = Field(default=None, description="Filter articles until this date")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

class BlockchainInfo(BaseModel):
    stored_on_chain: bool = False
    transaction_hash: Optional[str] = None
    blockchain_article_id: Optional[int] = None
    network: str = "bsc_testnet"
    explorer_url: Optional[str] = None
    content_hash: Optional[str] = None
    metadata_hash: Optional[str] = None

class UserArticleResponse(BaseModel):
    id: int
    title: str
    content: str
    image_url: Optional[str] = None
    source: str
    published_at: datetime
    relevance_score: Optional[float] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    blockchain_info: Optional[BlockchainInfo] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

class UserArticlesPageResponse(BaseModel):
    articles: List[UserArticleResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
    blockchain_statistics: Optional[Dict[str, Any]] = None

class ArticleSearchResponse(BaseModel):
    articles: List[UserArticleResponse]
    total_found: int
    search_query: str
    keywords_used: List[str]

class PopularInterestsResponse(BaseModel):
    popular_interests: List[str]
    total_articles_analyzed: int
    suggestion: str