import asyncio
from database import create_connection_pool, init_database, close_connection_pool

async def main():
    """Initialize database tables"""
    print("Initializing database...")
    
    try:
        await create_connection_pool()
        await init_database()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        await close_connection_pool()

if __name__ == "__main__":
    asyncio.run(main())