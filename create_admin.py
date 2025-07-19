import asyncio
from database import create_connection_pool, create_user, close_connection_pool
from auth import get_password_hash

async def create_first_admin():
    """Create the first admin user"""
    await create_connection_pool()
    
    # Admin details
    email = "admin@aicnews.com"
    password = "admin123" 
    full_name = "AIC News Admin"
    
    hashed_password = get_password_hash(password)
    
    try:
        admin_user = await create_user(
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            is_admin=True
        )
        print(f"Admin user created successfully!")
        print(f"Email: {email}")
        print(f"Password: {password}")
        print(f"User ID: {admin_user['id']}")
    except Exception as e:
        print(f"Error creating admin user: {e}")
    finally:
        await close_connection_pool()

if __name__ == "__main__":
    asyncio.run(create_first_admin())