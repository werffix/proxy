from aiogram import Router
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, KICKED, LEFT, MEMBER
from aiogram.types import ChatMemberUpdated
import logging

import config
from db import database as db
from mtg import manager as mtg

logger = logging.getLogger(__name__)
router = Router()


async def _ensure_user_proxy_secret(user_row: dict | None) -> str | None:
    if not user_row:
        return None

    secret = mtg.ensure_secret(user_row["id"], user_row.get("secret"))
    if secret != user_row.get("secret") or user_row.get("port") is not None:
        await db.update_user_proxy(user_row["id"], secret, None)
        user_row["secret"] = secret
        user_row["port"] = None
    return secret


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_joined_channel(event: ChatMemberUpdated):
    if event.chat.id != config.CHANNEL_ID:
        return

    user_id = event.new_chat_member.user.id
    user = await db.get_user(user_id)

    if not user or user["is_banned"]:
        return

    secret = await _ensure_user_proxy_secret(user)

    if user["left_channel_at"] is not None and not user["is_active"] and secret:
        ok = await mtg.start_proxy(secret)
        if ok:
            await db.set_user_active(user_id, True)
            await db.log_event(user_id, "access_restored")
            link = mtg.build_proxy_link(secret)
            try:
                await event.bot.send_message(
                    user_id,
                    f"🎉 Вы снова подписаны на канал!\n\n"
                    f"Ваш прокси восстановлен:\n{link}",
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.warning("Cannot notify user %s: %s", user_id, exc)
    elif user["left_channel_at"] is not None:
        await db.set_user_active(user_id, True)
        try:
            await event.bot.send_message(
                user_id,
                "✅ Отлично! Вы снова подписаны на канал. Ваш прокси продолжает работать.",
            )
        except Exception:
            pass


@router.chat_member(ChatMemberUpdatedFilter(member_status_changed=LEFT | KICKED))
async def user_left_channel(event: ChatMemberUpdated):
    if event.chat.id != config.CHANNEL_ID:
        return

    user_id = event.new_chat_member.user.id
    user = await db.get_user(user_id)

    if not user or user["is_banned"] or not user["is_active"]:
        return

    secret = await _ensure_user_proxy_secret(user)
    if secret:
        await mtg.stop_proxy(secret)

    await db.set_user_active(user_id, False)
    await db.set_left_channel(user_id)
    await db.log_event(user_id, "left_channel")
    logger.info("User %s left channel, access revoked immediately", user_id)

    try:
        await event.bot.send_message(
            user_id,
            f"🚫 Вы вышли из канала {config.CHANNEL_USERNAME}.\n\n"
            f"Доступ к прокси отключён.\n\n"
            f"Чтобы восстановить доступ — подпишитесь обратно и напишите /start.\n"
            f"👉 https://t.me/{config.CHANNEL_USERNAME.lstrip('@')}",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("Cannot notify user %s: %s", user_id, exc)
