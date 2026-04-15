import aiomysql
import logging
from datetime import datetime, timedelta
from typing import Optional
import config

logger = logging.getLogger(__name__)
pool: Optional[aiomysql.Pool] = None


async def init_db():
    global pool
    pool = await aiomysql.create_pool(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        db=config.DB_NAME,
        autocommit=True,
        charset="utf8mb4",
    )
    await _create_tables()
    logger.info("Database connected")


async def get_all_users() -> list:
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE is_banned = FALSE")
            return await cur.fetchall()

async def close_db():
    if pool:
        pool.close()
        await pool.wait_closed()


async def _create_tables():
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id              BIGINT PRIMARY KEY,
                    username        VARCHAR(255),
                    full_name       VARCHAR(512),
                    secret          VARCHAR(128) UNIQUE,
                    port            INT UNIQUE,
                    is_active       BOOLEAN DEFAULT TRUE,
                    is_banned       BOOLEAN DEFAULT FALSE,
                    left_channel_at DATETIME NULL,
                    warned_at       DATETIME NULL,
                    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_seen       DATETIME DEFAULT CURRENT_TIMESTAMP
                ) CHARACTER SET utf8mb4;
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id         INT AUTO_INCREMENT PRIMARY KEY,
                    user_id    BIGINT,
                    event      VARCHAR(64),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_user (user_id),
                    INDEX idx_event (event)
                ) CHARACTER SET utf8mb4;
            """)


async def get_user(user_id: int) -> Optional[dict]:
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return await cur.fetchone()


async def create_user(
    user_id: int,
    username: str,
    full_name: str,
    secret: str,
    port: int | None = None,
) -> dict:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO users (id, username, full_name, secret, port)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    username  = VALUES(username),
                    full_name = VALUES(full_name),
                    last_seen = NOW()
            """, (user_id, username, full_name, secret, port))
    await log_event(user_id, "registered")
    return await get_user(user_id)


async def update_user_proxy(user_id: int, secret: str, port: int | None = None):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET secret = %s, port = %s WHERE id = %s",
                (secret, port, user_id),
            )


async def get_used_ports() -> list:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT port FROM users WHERE port IS NOT NULL")
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def set_user_active(user_id: int, active: bool):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET is_active = %s, left_channel_at = NULL, warned_at = NULL WHERE id = %s",
                (active, user_id)
            )


async def set_left_channel(user_id: int):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET left_channel_at = NOW() WHERE id = %s AND left_channel_at IS NULL",
                (user_id,)
            )


async def set_warned(user_id: int):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET warned_at = NOW() WHERE id = %s",
                (user_id,)
            )


async def ban_user(user_id: int):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET is_banned = TRUE, is_active = FALSE WHERE id = %s",
                (user_id,)
            )
    await log_event(user_id, "banned")


async def unban_user(user_id: int):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE users SET is_banned = FALSE WHERE id = %s",
                (user_id,)
            )
    await log_event(user_id, "unbanned")


async def get_users_to_warn() -> list:
    warn_threshold = datetime.utcnow() - timedelta(hours=config.GRACE_PERIOD_HOURS - config.WARNING_HOURS)
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT * FROM users
                WHERE left_channel_at IS NOT NULL
                  AND left_channel_at <= %s
                  AND warned_at IS NULL
                  AND is_active = TRUE
                  AND is_banned = FALSE
            """, (warn_threshold,))
            return await cur.fetchall()


async def get_users_to_block() -> list:
    block_threshold = datetime.utcnow() - timedelta(hours=config.GRACE_PERIOD_HOURS)
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT * FROM users
                WHERE left_channel_at IS NOT NULL
                  AND left_channel_at <= %s
                  AND is_active = TRUE
                  AND is_banned = FALSE
            """, (block_threshold,))
            return await cur.fetchall()


async def get_all_active_users() -> list:
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE is_active = TRUE AND is_banned = FALSE")
            return await cur.fetchall()


async def get_stats() -> dict:
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT COUNT(*) as total FROM users")
            total = (await cur.fetchone())["total"]
            await cur.execute("SELECT COUNT(*) as active FROM users WHERE is_active = TRUE AND is_banned = FALSE")
            active = (await cur.fetchone())["active"]
            await cur.execute("SELECT COUNT(*) as banned FROM users WHERE is_banned = TRUE")
            banned = (await cur.fetchone())["banned"]
            await cur.execute("SELECT COUNT(*) as left_ch FROM users WHERE left_channel_at IS NOT NULL AND is_active = TRUE")
            grace = (await cur.fetchone())["left_ch"]
            await cur.execute("SELECT COUNT(*) as today FROM stats WHERE event = 'registered' AND DATE(created_at) = CURDATE()")
            today = (await cur.fetchone())["today"]
            return {"total": total, "active": active, "banned": banned, "grace": grace, "today": today}


async def search_users(query: str) -> list:
    q = f"%{query}%"
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                SELECT * FROM users
                WHERE username LIKE %s OR full_name LIKE %s OR id LIKE %s
                LIMIT 10
            """, (q, q, q))
            return await cur.fetchall()


async def log_event(user_id: int, event: str):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO stats (user_id, event) VALUES (%s, %s)",
                (user_id, event)
            )
