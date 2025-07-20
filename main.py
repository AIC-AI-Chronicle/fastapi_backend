from fastapi import FastAPI, HTTPException, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta
from contextlib import asynccontextmanager
import os
import json
from schemas import (
    UserCreate, UserResponse, User, Token, LoginRequest, 
    AdminUserCreate, AdminLoginRequest, UserUpdate
)
from admin_schemas import (
    PipelineStartRequest, PipelineStatusResponse, 
    ArticleResponse, AdminDashboardStats
)
from auth import (
    get_password_hash, authenticate_user, authenticate_admin, create_access_token,
    get_current_active_user, get_current_admin_user, ACCESS_TOKEN_EXPIRE_MINUTES
)
from database import (
    create_connection_pool, close_connection_pool, init_database,
    create_user, get_user_by_email, get_all_users, update_user_activity,
    get_db_connection
)
from agents import NewsAgent
from websocket_manager import manager

# Global variables
news_agent = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_connection_pool()
    await init_database()
    
    # Initialize news agent
    global news_agent
    gemini_api_key = os.getenv("GEMINI_API_KEY","AIzaSyDPgDccGhgwqqrs2DBgOu-BhbTv4vrho44")
    if not gemini_api_key:
        print("Warning: GEMINI_API_KEY not found in environment variables")
    else:
        news_agent = NewsAgent(gemini_api_key, manager)
    
    yield
    # Shutdown
    if news_agent and news_agent.is_running:
        news_agent.stop_pipeline()
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
        while True:
            # Keep connection alive and handle any incoming messages
            data = await websocket.receive_text()
            # Echo back for testing
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
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
    import asyncio
    asyncio.create_task(news_agent.run_pipeline(request.duration_minutes))
    
    return {"message": f"Pipeline started for {request.duration_minutes} minutes"}

@app.post("/admin/pipeline/stop")
async def stop_pipeline(current_admin: User = Depends(get_current_admin_user)):
    """Stop the news processing pipeline. (Admin only)"""
    if not news_agent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="News agent not initialized"
        )
    
    news_agent.stop_pipeline()
    return {"message": "Pipeline stopped"}

@app.get("/admin/pipeline/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(current_admin: User = Depends(get_current_admin_user)):
    """Get pipeline status. (Admin only)"""
    if not news_agent:
        return PipelineStatusResponse(is_running=False)
    
    return PipelineStatusResponse(is_running=news_agent.is_running)

@app.get("/admin/articles", response_model=list[ArticleResponse])
async def get_articles(
    limit: int = 50,
    current_admin: User = Depends(get_current_admin_user)
):
    """Get processed articles. (Admin only)"""
    async with get_db_connection() as conn:
        # Ensure articles table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                original_title TEXT NOT NULL,
                original_link TEXT,
                generated_content TEXT NOT NULL,
                authenticity_score JSONB,
                source TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        articles = await conn.fetch("""
            SELECT id, original_title, original_link, generated_content, 
                   authenticity_score, source, processed_at, created_at
            FROM articles 
            ORDER BY created_at DESC 
            LIMIT $1
        """, limit)
        
        return [
            ArticleResponse(
                id=article['id'],
                original_title=article['original_title'],
                original_link=article['original_link'],
                generated_content=article['generated_content'],
                authenticity_score=json.loads(article['authenticity_score']) if article['authenticity_score'] else {},
                source=article['source'],
                processed_at=article['processed_at'],
                created_at=article['created_at']
            )
            for article in articles
        ]

@app.get("/admin/dashboard/stats", response_model=AdminDashboardStats)
async def get_dashboard_stats(current_admin: User = Depends(get_current_admin_user)):
    """Get dashboard statistics. (Admin only)"""
    async with get_db_connection() as conn:
        # Ensure articles table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                original_title TEXT NOT NULL,
                original_link TEXT,
                generated_content TEXT NOT NULL,
                authenticity_score JSONB,
                source TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Get total articles
        total_articles = await conn.fetchval("SELECT COUNT(*) FROM articles")
        
        # Get articles today
        articles_today = await conn.fetchval("""
            SELECT COUNT(*) FROM articles 
            WHERE DATE(created_at) = CURRENT_DATE
        """)
    
    return AdminDashboardStats(
        total_articles=total_articles or 0,
        articles_today=articles_today or 0,
        pipeline_running=news_agent.is_running if news_agent else False,
        active_connections=len(manager.active_connections)
    )

@app.get("/admin/protected")
async def admin_protected_route(current_admin: User = Depends(get_current_admin_user)):
    """Protected admin route."""
    return {"message": f"Hello Admin {current_admin.full_name}, welcome to AIC News Agency Admin Panel!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)