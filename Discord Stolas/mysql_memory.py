import aiomysql
import asyncio
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="Discord Stolas\TOKENS.env")

# ------------------------------
# MySQL Connection Pool Setup
# ------------------------------
mysql_pool = None  # Global pool variable

async def init_pool():
    """Initialize a MySQL connection pool"""
    return await aiomysql.create_pool(
        host=os.getenv("host"),
        user=os.getenv("user"),
        password=os.getenv("password"),
        db=os.getenv("db"),
    )

async def setup():
    """Set up the global pool"""
    global mysql_pool
    if mysql_pool is None:
        mysql_pool = await init_pool()


# ------------------------------
# MySQL Memory Class
# ------------------------------
class MySQLMemory:
    def __init__(self, pool):
        self.pool = pool

    async def add_message(self, user_id, guild_id, role, content, emotion=None, intensity=1):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO messages (user_id, guild_id, role, content, emotion, intensity)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (user_id, guild_id, role, content, emotion, intensity)
                )
                await conn.commit()

    async def get_recent_messages(self, user_id, limit=10):
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT role, content
                    FROM messages
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                    """,
                    (user_id, limit)
                )
                rows = await cur.fetchall()
                return list(reversed(rows))

    async def upsert_profile(self, user_id, username=None, nickname=None, description=None):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO user_profiles (user_id, username, nickname, description)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        username = COALESCE(%s, username),
                        nickname = COALESCE(%s, nickname),
                        description = COALESCE(%s, description)
                    """,
                    (user_id, username, nickname, description,
                     username, nickname, description)
                )
                await conn.commit()

    async def get_profile(self, user_id):
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM user_profiles WHERE user_id = %s",
                    (user_id,)
                )
                return await cur.fetchone()

    async def save_user_profile(self, user_id: str, description: str):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO user_profiles (user_id, description)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE description = %s
                    """,
                    (user_id, description, description)
                )
            await conn.commit()
    async def get_all_user_ids(self):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT DISTINCT user_id FROM messages")
                return [row[0] for row in await cur.fetchall()]

    async def fetch_user_messages(self, user_id, limit=200):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT content FROM messages WHERE user_id=%s AND role='user' ORDER BY id DESC LIMIT %s",
                    (user_id, limit)
                )
                return [row[0] for row in await cur.fetchall()]

    async def save_user_profile(self, user_id, description):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO user_profiles (user_id, description) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE description=%s",
                    (user_id, description, description)
                )
                await conn.commit()
