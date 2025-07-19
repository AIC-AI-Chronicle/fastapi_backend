from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
import secrets
from schemas import User, TokenData
from database import get_user_by_email as db_get_user_by_email

# Configuration
SECRET_KEY = secrets.token_urlsafe(32) 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 3000000

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Utility functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_user_by_email(email: str):
    return await db_get_user_by_email(email)

async def authenticate_user(email: str, password: str):
    user_record = await get_user_by_email(email)
    if not user_record:
        return False
    if not verify_password(password, user_record['hashed_password']):
        return False
    return User(
        id=user_record['id'],
        email=user_record['email'],
        full_name=user_record['full_name'],
        hashed_password=user_record['hashed_password'],
        is_active=user_record['is_active'],
        is_admin=user_record['is_admin'],
        created_at=user_record['created_at']
    )

async def authenticate_admin(email: str, password: str):
    user = await authenticate_user(email, password)
    if not user or not user.is_admin:
        return False
    return user

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    user_record = await get_user_by_email(email=token_data.email)
    if user_record is None:
        raise credentials_exception
    
    return User(
        id=user_record['id'],
        email=user_record['email'],
        full_name=user_record['full_name'],
        hashed_password=user_record['hashed_password'],
        is_active=user_record['is_active'],
        is_admin=user_record['is_admin'],
        created_at=user_record['created_at']
    )

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_admin_user(current_user: User = Depends(get_current_active_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Admin access required."
        )
    return current_user