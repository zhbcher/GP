"""
Database initialization script.
Run: python init_db.py
"""
import asyncio
import os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def init():
    from app.db import engine, Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database initialized successfully.")


if __name__ == "__main__":
    asyncio.run(init())
