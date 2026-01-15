"""Async Database and Redis Connection Pool"""
import asyncpg
import redis.asyncio as aioredis
from config.config import Config
from typing import Optional

# Global connection pools
db_pool: Optional[asyncpg.Pool] = None
redis_client: Optional[aioredis.Redis] = None

async def init_db_pool():
    """Initialize async PostgreSQL connection pool"""
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(
            dsn=Config.get_db_connection_string(),
            min_size=2,
            max_size=10,
            command_timeout=60
        )
        print("✓ Async PostgreSQL pool initialized")
    return db_pool

async def init_redis_client():
    """Initialize async Redis client"""
    global redis_client
    if redis_client is None:
        redis_client = await aioredis.from_url(
            f"redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/{Config.REDIS_DB}",
            encoding="utf-8",
            decode_responses=True
        )
        print("✓ Async Redis client initialized")
    return redis_client

async def close_db_pool():
    """Close PostgreSQL connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
        print("Database pool closed")

async def close_redis_client():
    """Close Redis client"""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
        print("Redis client closed")

def get_db_pool() -> Optional[asyncpg.Pool]:
    """Get current database pool"""
    return db_pool

def get_redis_client() -> Optional[aioredis.Redis]:
    """Get current Redis client"""
    return redis_client

# Legacy sync connection (for backward compatibility during migration)
import psycopg2

conn = None

def connect_db():
    """Legacy sync DB connection (deprecated)"""
    global conn
    if conn is None:
        conn = psycopg2.connect(Config.get_db_connection_string())
        print("[DEPRECATED] Sync database connected")
    return conn

def disconnect_db():
    """Legacy sync disconnect (deprecated)"""
    global conn
    if conn:
        conn.close()
        conn = None
        print("[DEPRECATED] Sync database disconnected")
