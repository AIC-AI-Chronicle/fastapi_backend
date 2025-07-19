from fastapi import FastAPI, HTTPException, Depends, status
from datetime import timedelta
from schemas import UserCreate, UserResponse, User, Token, LoginRequest
from auth import (
    get_password_hash, authenticate_user, create_access_token,
    get_current_active_user, users_db, ACCESS_TOKEN_EXPIRE_MINUTES
)

app = FastAPI(
    title="AIC News Agency API",
    description="A basic API for the AIC News Agency with authentication.",
    version="0.0.1"
)

@app.get("/")
def read_root():
    """Root endpoint."""
    return {"message": "AIC News Agency API is running."}

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "AIC News Agency API"}

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    """Register a new user."""
    if user.email in users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    user_id = len(users_db) + 1
    hashed_password = get_password_hash(user.password)
    
    new_user = User(
        id=user_id,
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        is_active=True
    )
    
    users_db[user.email] = new_user
    
    return UserResponse(
        id=new_user.id,
        email=new_user.email,
        full_name=new_user.full_name,
        is_active=new_user.is_active
    )

@app.post("/login", response_model=Token)
async def login(login_data: LoginRequest):
    """Login user and return access token."""
    user = authenticate_user(login_data.email, login_data.password)
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
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/profile", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_active_user)):
    """Get current user profile."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active
    )

@app.get("/protected")
async def protected_route(current_user: User = Depends(get_current_active_user)):
    """Protected route that requires authentication."""
    return {"message": f"Hello {current_user.full_name}, welcome to AIC News Agency!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)