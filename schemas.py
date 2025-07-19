from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# User schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    is_admin: bool = True

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    is_admin: bool = False
    created_at: Optional[datetime] = None

class User(BaseModel):
    id: int
    email: str
    full_name: str
    hashed_password: str
    is_active: bool = True
    is_admin: bool = False
    created_at: Optional[datetime] = None

# Authentication schemas
class Token(BaseModel):
    access_token: str
    token_type: str
    user_type: str  # "user" or "admin"

class TokenData(BaseModel):
    email: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class AdminLoginRequest(BaseModel):
    email: str
    password: str

# Admin schemas
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None