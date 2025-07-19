import os
import asyncpg
from typing import Optional
import asyncio
from contextlib import asynccontextmanager

# Database configuration
DATABASE_CONFIG = {
    "host": os.getenv("PGHOST", "aic-db1.postgres.database.azure.com"),
    "user": os.getenv("PGUSER", "isxuuohzgi"),
    "port": int(os.getenv("PGPORT", "5432")),
    "database": os.getenv("PGDATABASE", "postgres"),
    "password": os.getenv("PGPASSWORD", "UKgMzRirfe2ajm9iJhgFNZ58kX"),
    "ssl": "require"
}

# Connection pool
connection_pool: Optional[asyncpg.Pool] = None

async def create_connection_pool():
    """Create database connection pool"""
    global connection_pool
    connection_pool = await asyncpg.create_pool(
        **DATABASE_CONFIG,
        min_size=5,
        max_size=20
    )
    return connection_pool

async def close_connection_pool():
    """Close database connection pool"""
    global connection_pool
    if connection_pool:
        await connection_pool.close()

@asynccontextmanager
async def get_db_connection():
    """Get database connection from pool"""
    if not connection_pool:
        await create_connection_pool()
    
    async with connection_pool.acquire() as connection:
        yield connection

async def init_database():
    """Initialize database tables"""
    async with get_db_connection() as conn:
        # Create users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                full_name VARCHAR(255) NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                is_admin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index on email
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
        """)
        
        print("Database tables initialized successfully")

# Database operations
async def create_user(email: str, full_name: str, hashed_password: str, is_admin: bool = False):
    """Create a new user in database"""
    async with get_db_connection() as conn:
        user_id = await conn.fetchval("""
            INSERT INTO users (email, full_name, hashed_password, is_admin)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """, email, full_name, hashed_password, is_admin)
        
        return await conn.fetchrow("""
            SELECT id, email, full_name, is_active, is_admin, created_at
            FROM users WHERE id = $1
        """, user_id)

async def get_user_by_email(email: str):
    """Get user by email from database"""
    async with get_db_connection() as conn:
        return await conn.fetchrow("""
            SELECT id, email, full_name, hashed_password, is_active, is_admin, created_at
            FROM users WHERE email = $1
        """, email)

async def get_user_by_id(user_id: int):
    """Get user by ID from database"""
    async with get_db_connection() as conn:
        return await conn.fetchrow("""
            SELECT id, email, full_name, hashed_password, is_active, is_admin, created_at
            FROM users WHERE id = $1
        """, user_id)

async def update_user_activity(email: str, is_active: bool):
    """Update user activity status"""
    async with get_db_connection() as conn:
        await conn.execute("""
            UPDATE users SET is_active = $1, updated_at = CURRENT_TIMESTAMP
            WHERE email = $2
        """, is_active, email)

async def get_all_users():
    """Get all users (admin only)"""
    async with get_db_connection() as conn:
        return await conn.fetch("""
            SELECT id, email, full_name, is_active, is_admin, created_at
            FROM users ORDER BY created_at DESC
        """)