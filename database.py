import asyncpg
import os
from typing import Optional
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create articles table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                original_title TEXT NOT NULL,
                original_link TEXT,
                generated_content TEXT NOT NULL,
                authenticity_score JSONB,
                source TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                pipeline_id VARCHAR(255),
                cycle_number INTEGER DEFAULT 1
            )
        """)
        
        # Create pipeline_runs table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id SERIAL PRIMARY KEY,
                pipeline_id VARCHAR(255) UNIQUE NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                current_cycle INTEGER DEFAULT 0,
                total_cycles INTEGER DEFAULT 1,
                articles_processed INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                auto_mode BOOLEAN DEFAULT FALSE,
                duration_minutes INTEGER DEFAULT 30
            )
        """)
        
        # Create agent_logs table for detailed logging
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_logs (
                id SERIAL PRIMARY KEY,
                pipeline_id VARCHAR(255),
                agent_name VARCHAR(100) NOT NULL,
                message TEXT NOT NULL,
                log_level VARCHAR(20) DEFAULT 'INFO',
                data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        print("Database tables initialized successfully")

# Database operations
async def create_user(email: str, full_name: str, hashed_password: str, is_admin: bool = False):
    """Create a new user in database"""
    async with get_db_connection() as conn:
        user_record = await conn.fetchrow("""
            INSERT INTO users (email, full_name, hashed_password, is_admin)
            VALUES ($1, $2, $3, $4)
            RETURNING id, email, full_name, is_active, is_admin, created_at
        """, email, full_name, hashed_password, is_admin)
        return dict(user_record)

async def get_user_by_email(email: str):
    """Get user by email from database"""
    async with get_db_connection() as conn:
        user_record = await conn.fetchrow("""
            SELECT id, email, full_name, hashed_password, is_active, is_admin, created_at
            FROM users WHERE email = $1
        """, email)
        return dict(user_record) if user_record else None

async def get_user_by_id(user_id: int):
    """Get user by ID from database"""
    async with get_db_connection() as conn:
        user_record = await conn.fetchrow("""
            SELECT id, email, full_name, hashed_password, is_active, is_admin, created_at
            FROM users WHERE id = $1
        """, user_id)
        return dict(user_record) if user_record else None

async def update_user_activity(email: str, is_active: bool):
    """Update user activity status"""
    async with get_db_connection() as conn:
        await conn.execute("""
            UPDATE users SET is_active = $1 WHERE email = $2
        """, is_active, email)

async def get_all_users():
    """Get all users (admin only)"""
    async with get_db_connection() as conn:
        users = await conn.fetch("""
            SELECT id, email, full_name, is_active, is_admin, created_at
            FROM users ORDER BY created_at DESC
        """)
        return [dict(user) for user in users]

async def log_agent_activity(pipeline_id: str, agent_name: str, message: str, log_level: str = "INFO", data: dict = None):
    """Log agent activity"""
    async with get_db_connection() as conn:
        await conn.execute("""
            INSERT INTO agent_logs (pipeline_id, agent_name, message, log_level, data)
            VALUES ($1, $2, $3, $4, $5)
        """, pipeline_id, agent_name, message, log_level, data)