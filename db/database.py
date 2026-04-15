# db/database.py
import aiosqlite
import config

_db = None

async def init_db():
    global _db
    _db = await aiosqlite.connect(config.DATABASE_URL)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            secret TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await _db.commit()

async def get_user(user_id: int) -> dict | None:
    async with _db.execute(
        "SELECT user_id, secret FROM users WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return {"user_id": row[0], "secret": row[1]} if row else None

async def create_or_update_user(user_id: int, secret: str):
    await _db.execute("""
        INSERT INTO users (user_id, secret) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET secret = ?, updated_at = CURRENT_TIMESTAMP
    """, (user_id, secret, secret))
    await _db.commit()
