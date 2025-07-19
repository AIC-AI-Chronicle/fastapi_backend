from pydantic import BaseModel, EmailStr
from typing import Optional

# User schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool

class User(BaseModel):
    id: int
    email: str
    full_name: str
    hashed_password: str
    is_active: bool = True

# Authentication schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str