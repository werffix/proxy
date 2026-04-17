import asyncio
import logging
from aiogram import Bot

import config
from db import database as db
from mtg import manager as mtg

logger = logging.getLogger(__name__)


async def check_grace_periods(bot: Bot):
    # Предупреждения
    for user in await db.get_users_to_warn():
        try:
            await bot.send_message(
                user["id"],
                f"⏰ <b>Внимание!</b>\n\n"
                f"До отключения прокси осталось менее <b>{config.WARNING_HOURS} часов</b>.\n\n"
                f"Подпишитесь на канал чтобы сохранить доступ:\n"
                f"👉 https://t.me/{config.CHANNEL_USERNAME.lstrip('@')}",
                parse_mode="HTML",
            )
            await db.set_warned(user["id"])
            logger.info(f"Warning sent to user {user['id']}")
        except Exception as e:
            logger.warning(f"Cannot warn user {user['id']}: {e}")

    # Блокировки
    for user in await db.get_users_to_block():
        try:
            secret = mtg.ensure_secret(user["id"], user.get("secret"))
            if secret != user.get("secret") or user.get("port") is not None:
                await db.update_user_proxy(user["id"], secret, None)
            await mtg.stop_proxy(secret)
            await db.set_user_active(user["id"], False)
            await db.log_event(user["id"], "access_revoked")
            await bot.send_message(
                user["id"],
                f"🚫 Ваш доступ к прокси отключён.\n\n"
                f"Вы вышли из канала {config.CHANNEL_USERNAME} более "
                f"{config.GRACE_PERIOD_HOURS} часов назад.\n\n"
                f"Чтобы восстановить доступ — подпишитесь на канал и напишите /start.\n"
                f"👉 https://t.me/{config.CHANNEL_USERNAME.lstrip('@')}",
                parse_mode="HTML",
            )
            logger.info(f"Access revoked for user {user['id']}")
        except Exception as e:
            logger.warning(f"Cannot notify user {user['id']}: {e}")


async def run_scheduler(bot: Bot):
    while True:
        try:
            await check_grace_periods(bot)
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        await asyncio.sleep(30 * 60)
