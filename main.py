from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta
from contextlib import asynccontextmanager
from schemas import (
    UserCreate, UserResponse, User, Token, LoginRequest, 
    AdminUserCreate, AdminLoginRequest, UserUpdate
)
from auth import (
    get_password_hash, authenticate_user, authenticate_admin, create_access_token,
    get_current_active_user, get_current_admin_user, ACCESS_TOKEN_EXPIRE_MINUTES
)
from database import (
    create_connection_pool, close_connection_pool, init_database,
    create_user, get_user_by_email, get_all_users, update_user_activity
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await create_connection_pool()
    await init_database()
    yield
    # Shutdown
    await close_connection_pool()

app = FastAPI(
    title="AIC News Agency API",
    description="A basic API for the AIC News Agency with authentication and admin functionality.",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware to allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allows all headers
)

@app.get("/")
def read_root():
    """Root endpoint."""
    return {"message": "AIC News Agency API is running."}

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "AIC News Agency API"}

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

@app.get("/admin/protected")
async def admin_protected_route(current_admin: User = Depends(get_current_admin_user)):
    """Protected admin route."""
    return {"message": f"Hello Admin {current_admin.full_name}, welcome to AIC News Agency Admin Panel!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)