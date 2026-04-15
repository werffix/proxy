import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import config
from db import database as db
from bot.handlers import user, admin, channel
from mtg import manager as mtg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def migrate_proxy_secrets():
    users = await db.get_all_users()
    updated = 0

    for user in users:
        secret = mtg.ensure_secret(user["id"], user.get("secret"))
        if secret != user.get("secret") or user.get("port") is not None:
            await db.update_user_proxy(user["id"], secret, None)
            updated += 1

    if updated:
        logger.info("Migrated %s users to single-port proxy secrets", updated)


async def main():
    await db.init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.include_router(channel.router)
    dp.include_router(user.router)
    dp.include_router(admin.router)

    await migrate_proxy_secrets()

    active_users = await db.get_all_active_users()
    await mtg.restore_all(active_users)
    sync_task = asyncio.create_task(mtg.sync_active_users_loop(db.get_all_active_users))

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member"])
    finally:
        sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sync_task
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
