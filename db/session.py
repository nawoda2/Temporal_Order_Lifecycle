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
        
        # Try to create the orders database if it doesn't exist
        try:
            # Connect to default postgres database to create orders db
            default_db_url = db_url.rsplit('/', 1)[0] + '/postgres'
            conn = await asyncpg.connect(default_db_url)
            try:
                await conn.execute('CREATE DATABASE orders')
                print("Created 'orders' database")
            except asyncpg.DuplicateDatabaseError:
                pass  # Database already exists
            finally:
                await conn.close()
        except Exception as e:
            print(f"Note: Could not create database (may already exist): {e}")
        
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=10,
            max_size=30,
            command_timeout=5,
            statement_cache_size=100,
            max_cached_statement_lifetime=300,
            max_cacheable_statement_size=1024 * 15
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