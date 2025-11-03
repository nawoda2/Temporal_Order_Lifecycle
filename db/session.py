"""Database connection pool using asyncpg."""
import asyncpg
from typing import Optional
from config import settings

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def init_db_pool():
    """Initialize the database connection pool."""
    global _pool
    if _pool is None:
        # Convert SQLAlchemy URL to asyncpg format
        db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
    return _pool


async def get_db_pool() -> asyncpg.Pool:
    """Get the database connection pool."""
    if _pool is None:
        await init_db_pool()
    return _pool


async def close_db_pool():
    """Close the database connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_schema():
    """Initialize database schema from schema.sql file."""
    pool = await get_db_pool()
    
    # Read schema file
    with open("db/schema.sql", "r") as f:
        schema_sql = f.read()
    
    # Execute schema
    async with pool.acquire() as conn:
        await conn.execute(schema_sql)