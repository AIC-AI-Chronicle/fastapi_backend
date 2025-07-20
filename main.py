from fastapi import FastAPI, HTTPException, Depends, status, WebSocket, WebSocketDisconnect, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta, datetime, timezone
from contextlib import asynccontextmanager
import os
import json
import asyncio
import math
from schemas import (
    UserCreate, UserResponse, User, Token, LoginRequest, 
    AdminUserCreate, AdminLoginRequest, UserUpdate
)
from admin_schemas import (
    PipelineStartRequest, PipelineStatusResponse, 
    ArticleResponse, AdminDashboardStats, PipelineRunResponse
)
from auth import (
    get_password_hash, authenticate_user, authenticate_admin, create_access_token,
    get_current_active_user, get_current_admin_user, ACCESS_TOKEN_EXPIRE_MINUTES
)
from database import (
    create_connection_pool, close_connection_pool, init_database,
    create_user, get_user_by_email, get_all_users, update_user_activity,
    get_db_connection, get_active_pipeline_runs, get_articles, get_dashboard_stats,
    get_user_articles, search_articles_by_keywords
)
from agents import NewsAgent
from websocket_manager import manager
from user_schemas import (
    BlockchainInfo, UserArticleRequest, UserArticleResponse, UserArticlesPageResponse
)
from blockchain_integration import BlockchainHasher

# Global variables
news_agent = None
background_tasks = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_connection_pool()
    await init_database()
    
    # Initialize news agent
    global news_agent
    gemini_api_key = os.getenv("GEMINI_API_KEY","AIzaSyAdmLL_kfsmECwKuW70gWrjrnXA0WB5ZqY")
    if not gemini_api_key:
        print("Warning: GEMINI_API_KEY not found in environment variables")
    else:
        news_agent = NewsAgent(gemini_api_key, manager)
    
    yield
    # Shutdown
    if news_agent and news_agent.is_running:
        news_agent.stop_pipeline()
    
    # Cancel all background tasks
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)
    
    await close_connection_pool()

app = FastAPI(
    title="AIC News Agency API",
    description="A news processing API with AI agents and admin functionality.",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware to allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def create_background_task(coro):
    """Create and track background tasks"""
    task = asyncio.create_task(coro)
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)
    return task

@app.get("/")
def read_root():
    """Root endpoint."""
    return {"message": "AIC News Agency API is running."}

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "AIC News Agency API"}

# WebSocket endpoint for real-time updates
@app.websocket("/ws/admin")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial connection message
        await websocket.send_text(json.dumps({
            "agent": "System",
            "message": "Connected to AIC News Agency real-time updates",
            "timestamp": "now",
            "data": {"connected": True}
        }))
        
        while True:
            # Keep connection alive and handle any incoming messages
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo back for testing
                await websocket.send_text(json.dumps({
                    "agent": "Echo",
                    "message": f"Received: {data}",
                    "timestamp": "now"
                }))
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_text(json.dumps({
                    "agent": "System",
                    "message": "ping",
                    "timestamp": "now"
                }))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# User Registration and Authentication
@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    """Register a new user."""
    existing_user = await get_user_by_email(user.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = get_password_hash(user.password)
    
    user_record = await create_user(
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        is_admin=False
    )
    
    return UserResponse(
        id=user_record['id'],
        email=user_record['email'],
        full_name=user_record['full_name'],
        is_active=user_record['is_active'],
        is_admin=user_record['is_admin'],
        created_at=user_record['created_at']
    )

@app.post("/login", response_model=Token)
async def login(login_data: LoginRequest):
    """Login user and return access token."""
    user = await authenticate_user(login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_type": "admin" if user.is_admin else "user"
    }

# Admin Registration and Authentication
@app.post("/admin/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def admin_register(user: AdminUserCreate, current_admin: User = Depends(get_current_admin_user)):
    """Register a new admin user. (Admin only)"""
    existing_user = await get_user_by_email(user.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = get_password_hash(user.password)
    
    user_record = await create_user(
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        is_admin=True
    )
    
    return UserResponse(
        id=user_record['id'],
        email=user_record['email'],
        full_name=user_record['full_name'],
        is_active=user_record['is_active'],
        is_admin=user_record['is_admin'],
        created_at=user_record['created_at']
    )

@app.post("/admin/login", response_model=Token)
async def admin_login(login_data: AdminLoginRequest):
    """Admin login and return access token."""
    user = await authenticate_admin(login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect admin credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user_type": "admin"
    }

# User Profile
@app.get("/profile", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_active_user)):
    """Get current user profile."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_admin=current_user.is_admin,
        created_at=current_user.created_at
    )

@app.get("/protected")
async def protected_route(current_user: User = Depends(get_current_active_user)):
    """Protected route that requires authentication."""
    return {"message": f"Hello {current_user.full_name}, welcome to AIC News Agency!"}

# Admin Routes
@app.get("/admin/users", response_model=list[UserResponse])
async def get_all_users_admin(current_admin: User = Depends(get_current_admin_user)):
    """Get all users. (Admin only)"""
    users = await get_all_users()
    return [
        UserResponse(
            id=user['id'],
            email=user['email'],
            full_name=user['full_name'],
            is_active=user['is_active'],
            is_admin=user['is_admin'],
            created_at=user['created_at']
        )
        for user in users
    ]

@app.put("/admin/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int, 
    current_admin: User = Depends(get_current_admin_user)
):
    """Toggle user active status. (Admin only)"""
    from database import get_user_by_id
    user_record = await get_user_by_id(user_id)
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    new_status = not user_record['is_active']
    await update_user_activity(user_record['email'], new_status)
    
    return {"message": f"User {'activated' if new_status else 'deactivated'} successfully"}

# News Processing Admin Routes
@app.post("/admin/pipeline/start")
async def start_pipeline(
    request: PipelineStartRequest,
    current_admin: User = Depends(get_current_admin_user)
):
    """Start the news processing pipeline. (Admin only)"""
    if not news_agent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="News agent not initialized. Check GEMINI_API_KEY."
        )
    
    if news_agent.is_running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pipeline is already running"
        )
    
    # Start pipeline in background
    task = create_background_task(news_agent.run_pipeline(request.duration_minutes))
    
    return {
        "message": f"Pipeline started for {request.duration_minutes} minutes",
        "pipeline_id": news_agent.current_pipeline_id,
        "duration_minutes": request.duration_minutes
    }

@app.post("/admin/pipeline/stop")
async def stop_pipeline(current_admin: User = Depends(get_current_admin_user)):
    """Stop the news processing pipeline. (Admin only)"""
    if not news_agent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="News agent not initialized"
        )
    
    if not news_agent.is_running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pipeline is currently running"
        )
    
    news_agent.stop_pipeline()
    return {"message": "Pipeline stop requested"}

@app.get("/admin/pipeline/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(current_admin: User = Depends(get_current_admin_user)):
    """Get pipeline status. (Admin only)"""
    if not news_agent:
        return PipelineStatusResponse(is_running=False)
    
    status = news_agent.get_status()
    return PipelineStatusResponse(
        is_running=status["is_running"],
        pipeline_id=status["pipeline_id"],
        start_time=status["start_time"],
        current_cycle=status["current_cycle"],
        total_articles_processed=status["total_articles_processed"]
    )

@app.get("/admin/pipeline/runs", response_model=list[PipelineRunResponse])
async def get_pipeline_runs(
    limit: int = 10,
    current_admin: User = Depends(get_current_admin_user)
):
    """Get pipeline run history. (Admin only)"""
    async with get_db_connection() as conn:
        runs = await conn.fetch("""
            SELECT id, pipeline_id, status, current_cycle, total_cycles, 
                   articles_processed, error_message, created_at, updated_at, 
                   started_at, ended_at, duration_minutes
            FROM pipeline_runs 
            ORDER BY created_at DESC 
            LIMIT $1
        """, limit)
        
        return [
            PipelineRunResponse(
                id=run['id'],
                pipeline_id=run['pipeline_id'],
                status=run['status'],
                current_cycle=run['current_cycle'],
                total_cycles=run['total_cycles'],
                articles_processed=run['articles_processed'],
                error_message=run['error_message'],
                created_at=run['created_at'],
                updated_at=run['updated_at'],
                started_at=run['started_at'],
                ended_at=run['ended_at'],
                duration_minutes=run['duration_minutes']
            )
            for run in runs
        ]

@app.get("/admin/articles", response_model=list[ArticleResponse])
async def get_articles_endpoint(
    limit: int = 50,
    pipeline_id: str = None,
    current_admin: User = Depends(get_current_admin_user)
):
    """Get processed articles. (Admin only)"""
    articles = await get_articles(limit, pipeline_id)
    
    return [
        ArticleResponse(
            id=article['id'],
            original_title=article['original_title'],
            original_link=article['original_link'],
            image_url=article.get('image_url'),
            generated_content=article['generated_content'],
            authenticity_score=json.loads(article['authenticity_score']) if article['authenticity_score'] else {},
            source=article['source'],
            processed_at=article['processed_at'],
            created_at=article['created_at'],
            pipeline_id=article['pipeline_id'],
            cycle_number=article['cycle_number']
        )
        for article in articles
    ]

@app.get("/admin/dashboard/stats", response_model=AdminDashboardStats)
async def get_dashboard_stats_endpoint(current_admin: User = Depends(get_current_admin_user)):
    """Get dashboard statistics. (Admin only)"""
    stats = await get_dashboard_stats()
    
    return AdminDashboardStats(
        total_articles=stats["total_articles"],
        articles_today=stats["articles_today"],
        pipeline_running=news_agent.is_running if news_agent else False,
        active_connections=len(manager.active_connections),
        running_pipelines=stats["running_pipelines"],
        recent_activity={"articles_today": stats["articles_today"], "total_articles": stats["total_articles"]}
    )

@app.get("/admin/protected")
async def admin_protected_route(current_admin: User = Depends(get_current_admin_user)):
    """Protected admin route."""
    return {"message": f"Hello Admin {current_admin.full_name}, welcome to AIC News Agency Admin Panel!"}

@app.get("/admin/pipeline/logs")
async def get_pipeline_logs(
    pipeline_id: str = Query(None),
    limit: int = 100,
    current_admin: User = Depends(get_current_admin_user)
):
    """Get recent pipeline logs. (Admin only)"""
    async with get_db_connection() as conn:
        query = "SELECT * FROM agent_logs"
        params = []
        if pipeline_id:
            query += " WHERE pipeline_id = $1"
            params.append(pipeline_id)
        query += " ORDER BY created_at DESC LIMIT $2"
        params.append(limit)
        logs = await conn.fetch(query, *params)
        return [dict(log) for log in logs]

# User Articles Endpoints
@app.post("/user/articles", response_model=UserArticlesPageResponse)
async def get_user_articles_endpoint(
    request: UserArticleRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Get articles for user based on interests with pagination."""
    
    try:
        # Validate and process date filters
        date_from = request.date_from
        date_to = request.date_to
        
        # Convert timezone-naive datetimes to UTC if needed
        if date_from and date_from.tzinfo is None:
            date_from = date_from.replace(tzinfo=timezone.utc)
        if date_to and date_to.tzinfo is None:
            date_to = date_to.replace(tzinfo=timezone.utc)
        
        # Validate date range
        if date_from and date_to and date_from > date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date_from cannot be after date_to"
            )
        
        # Get articles from database
        result = await get_user_articles(
            interests=request.interests,
            page=request.page,
            page_size=request.page_size,
            source_filter=request.source_filter,
            date_from=date_from,
            date_to=date_to
        )
        
        # Process articles and extract titles/tags from generated content
        user_articles = []
        blockchain_stored_count = 0
        
        for article in result["articles"]:
            # Extract title and content from generated_content
            generated_content = article.get("generated_content", "")
            title = article.get("original_title", "")
            content = generated_content
            tags = []
            
            # Try to parse the generated content for better formatting
            try:
                if generated_content and "HEADLINE:" in generated_content:
                    lines = generated_content.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line.startswith("HEADLINE:"):
                            title = line.replace("HEADLINE:", "").strip()
                        elif line.startswith("TAGS:"):
                            tags_str = line.replace("TAGS:", "").strip()
                            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                            break
            except Exception:
                pass
            
            # Calculate relevance score if interests provided
            relevance_score = None
            if request.interests:
                relevance_score = 0.0
                content_lower = (title + " " + content).lower()
                matches = 0
                for interest in request.interests:
                    if interest.lower() in content_lower:
                        matches += 1
                relevance_score = matches / len(request.interests) if request.interests else 0.0
            
            # Ensure datetime is timezone-aware
            published_at = article.get("created_at")
            if published_at and published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            
            # Create blockchain info
            blockchain_info = None
            if article.get("blockchain_stored"):
                blockchain_stored_count += 1
                blockchain_info = BlockchainInfo(
                    stored_on_chain=article.get("blockchain_stored", False),
                    transaction_hash=article.get("blockchain_transaction_hash"),
                    blockchain_article_id=article.get("blockchain_article_id"),
                    network=article.get("blockchain_network", "bsc_testnet"),
                    explorer_url=article.get("blockchain_explorer_url"),
                    content_hash=article.get("content_hash"),
                    metadata_hash=article.get("metadata_hash")
                )
            
            user_articles.append(UserArticleResponse(
                id=article["id"],
                title=title or "Untitled",
                content=content,
                image_url=article.get("image_url"),
                source=article.get("source", "Unknown"),
                published_at=published_at,
                relevance_score=relevance_score,
                tags=tags,
                blockchain_info=blockchain_info
            ))
        
        # Sort by relevance if interests provided
        if request.interests and user_articles:
            user_articles.sort(key=lambda x: x.relevance_score or 0, reverse=True)
        
        # Calculate pagination info
        total_pages = math.ceil(result["total_count"] / request.page_size) if result["total_count"] > 0 else 0
        has_next = request.page < total_pages
        has_previous = request.page > 1
        
        # Blockchain statistics
        blockchain_stats = {
            "total_articles_on_page": len(user_articles),
            "blockchain_stored_count": blockchain_stored_count,
            "blockchain_stored_percentage": (blockchain_stored_count / len(user_articles) * 100) if user_articles else 0,
            "network": "bsc_testnet",
            "explorer_base_url": "https://testnet.bscscan.com"
        }
        
        return UserArticlesPageResponse(
            articles=user_articles,
            total_count=result["total_count"],
            page=request.page,
            page_size=request.page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
            blockchain_statistics=blockchain_stats
        )
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_user_articles_endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching articles: {str(e)}"
        )

@app.get("/user/articles/search")
async def search_user_articles(
    q: str = Query(..., description="Search query", min_length=2),
    limit: int = Query(20, le=100, ge=1, description="Maximum number of articles to return"),
    current_user: User = Depends(get_current_active_user)
):
    """Search articles by keywords for users."""
    
    try:
        # Split search query into keywords and filter valid ones
        keywords = [keyword.strip() for keyword in q.split() if len(keyword.strip()) >= 2]
        
        if not keywords:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid search keywords provided (minimum 2 characters per keyword)"
            )
        
        # Search articles
        articles = await search_articles_by_keywords(keywords, limit)
        
        # Process and format articles
        search_results = []
        for article in articles:
            # Extract title from generated content
            generated_content = article.get("generated_content", "")
            title = article.get("original_title", "")
            content = generated_content
            tags = []
            
            # Try to parse the generated content for better formatting
            try:
                if generated_content and "HEADLINE:" in generated_content:
                    lines = generated_content.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line.startswith("HEADLINE:"):
                            title = line.replace("HEADLINE:", "").strip()
                        elif line.startswith("TAGS:"):
                            tags_str = line.replace("TAGS:", "").strip()
                            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
            except Exception:
                pass
            
            # Ensure datetime is timezone-aware
            published_at = article.get("created_at")
            if published_at and published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            
            search_results.append(UserArticleResponse(
                id=article["id"],
                title=title or "Untitled",
                content=content,
                image_url=article.get("image_url"),
                source=article.get("source", "Unknown"),
                published_at=published_at,
                relevance_score=article.get("relevance_score", 0.0),
                tags=tags
            ))
        
        return {
            "articles": search_results,
            "total_found": len(search_results),
            "search_query": q,
            "keywords_used": keywords
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in search_user_articles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching articles: {str(e)}"
        )

@app.get("/user/articles/interests")
async def get_popular_interests(current_user: User = Depends(get_current_active_user)):
    """Get popular interests/tags from articles to help users choose."""
    try:
        async with get_db_connection() as conn:
            # Get recent articles and extract common keywords
            articles = await conn.fetch("""
                SELECT generated_content 
                FROM articles 
                WHERE created_at >= NOW() - INTERVAL '30 days'
                ORDER BY created_at DESC 
                LIMIT 100
            """)
            
            # Extract tags from articles
            all_tags = []
            
            for article in articles:
                content = article.get("generated_content", "")
                try:
                    if "TAGS:" in content:
                        lines = content.split('\n')
                        for line in lines:
                            if line.startswith("TAGS:"):
                                tags_str = line.replace("TAGS:", "").strip()
                                tags = [tag.strip().lower() for tag in tags_str.split(',') if tag.strip()]
                                all_tags.extend(tags)
                                break
                except Exception:
                    continue
            
            # Count tag frequency
            from collections import Counter
            tag_counter = Counter(all_tags)
            popular_tags = [tag for tag, count in tag_counter.most_common(20) if count > 1]
            
            # Add some default popular interests
            default_interests = [
                "technology", "politics", "sports", "health", "business", 
                "science", "entertainment", "world news", "economy", "climate"
            ]
            
            # Combine and deduplicate
            all_interests = list(set(popular_tags + default_interests))[:30]
            
            return {
                "popular_interests": all_interests,
                "total_articles_analyzed": len(articles),
                "suggestion": "Select interests that match your preferences to get personalized article recommendations"
            }
    
    except Exception as e:
        return {
            "popular_interests": [
                "technology", "politics", "sports", "health", "business", 
                "science", "entertainment", "world news", "economy", "climate"
            ],
            "total_articles_analyzed": 0,
            "suggestion": "Select interests that match your preferences to get personalized article recommendations"
        }

@app.get("/blockchain/status")
async def get_blockchain_status():
    """Get blockchain connection status and statistics"""
    try:
        hasher = BlockchainHasher()
        status = await hasher.check_blockchain_status()
        return {
            "success": True,
            "blockchain_status": status
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "blockchain_status": {"connected": False}
        }

@app.get("/blockchain/articles/{article_id}")
async def get_blockchain_article(article_id: int):
    """Get article details from blockchain"""
    try:
        hasher = BlockchainHasher()
        article = await hasher.get_blockchain_article(article_id)
        return {
            "success": True,
            "article": article
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)