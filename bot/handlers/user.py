from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
import logging

import config
from db import database as db
from mtg import manager as mtg

logger = logging.getLogger(__name__)
router = Router()


def subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Подписаться на канал",
                    url=f"https://t.me/{config.CHANNEL_USERNAME.lstrip('@')}",
                )
            ],
            [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")],
        ]
    )


def proxy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Моя ссылка", callback_data="my_link")],
            [InlineKeyboardButton(text="📊 Мой статус", callback_data="my_status")],
            [InlineKeyboardButton(text="🆘 Поддержка", url="https://t.me/psychowaresupportxbot")],
        ]
    )


async def check_subscription(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(config.CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as exc:
        logger.warning("check_subscription error for %s: %s", user_id, exc)
        return False


async def _ensure_user_proxy_secret(user_row: dict | None, user_id: int) -> str | None:
    if not user_row:
        return None

    secret = mtg.ensure_secret(user_id, user_row.get("secret"))
    if secret != user_row.get("secret") or user_row.get("port") is not None:
        await db.update_user_proxy(user_id, secret, None)
        user_row["secret"] = secret
        user_row["port"] = None
    return secret


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await db.get_user(message.from_user.id)

    if user and user["is_banned"]:
        await message.answer("🚫 Вы заблокированы и не можете пользоваться прокси.")
        return

    is_subscribed = await check_subscription(message.bot, message.from_user.id)
    if not is_subscribed:
        await message.answer(
            f"👋 Привет, <b>{message.from_user.full_name}</b>!\n\n"
            f"Для получения доступа к прокси, необходимо подписаться на канал {config.CHANNEL_USERNAME}.\n\n"
            f"После подписки нажмите кнопку ниже 👇",
            parse_mode="HTML",
            reply_markup=subscribe_keyboard(),
        )
        return

    await _give_access(message, message.from_user)


async def _give_access(target, user):
    existing = await db.get_user(user.id)
    secret = await _ensure_user_proxy_secret(existing, user.id)

    if existing and secret and existing["is_active"]:
        ok = await mtg.start_proxy(secret)
        if not ok:
            await target.answer("⚠️ Не удалось активировать прокси. Попробуйте позже.")
            return

        link = mtg.build_proxy_link(secret)
        await target.answer(
            f"✅ Ваш прокси активен!\n\n"
            f"🔗 <b>Ссылка для подключения:</b>\n{link}\n\n"
            f"⚠️ Не передавайте ссылку другим — она привязана к вашему аккаунту.",
            parse_mode="HTML",
            reply_markup=proxy_keyboard(),
        )
        return

    if existing and secret and not existing["is_active"] and not existing["is_banned"]:
        ok = await mtg.start_proxy(secret)
        if ok:
            await db.set_user_active(user.id, True)
            await db.log_event(user.id, "access_restored")
            link = mtg.build_proxy_link(secret)
            await target.answer(
                f"✅ Ваш прокси восстановлен!\n\n"
                f"🔗 <b>Ссылка для подключения:</b>\n{link}\n\n"
                f"⚠️ Не передавайте ссылку другим — она привязана к вашему аккаунту.",
                parse_mode="HTML",
                reply_markup=proxy_keyboard(),
            )
        else:
            await target.answer("⚠️ Не удалось активировать прокси. Попробуйте позже.")
        return

    secret = mtg.generate_secret(user.id)
    await db.create_user(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
        secret=secret,
        port=None,
    )

    ok = await mtg.start_proxy(secret)
    if not ok:
        await db.set_user_active(user.id, False)
        await target.answer("⚠️ Не удалось создать прокси. Попробуйте позже.")
        return

    await db.set_user_active(user.id, True)
    await db.log_event(user.id, "access_granted")

    link = mtg.build_proxy_link(secret)
    await target.answer(
        f"🔗 <b>Ваша персональная ссылка:</b>\n{link}\n\n"
        f"📌 Нажмите на ссылку чтобы подключить прокси в Telegram.\n"
        f"⚠️ Не передавайте ссылку другим — она привязана к вашему аккаунту.",
        parse_mode="HTML",
        reply_markup=proxy_keyboard(),
    )


@router.callback_query(F.data == "check_sub")
async def callback_check_sub(callback: CallbackQuery):
    is_subscribed = await check_subscription(callback.bot, callback.from_user.id)
    if not is_subscribed:
        await callback.answer("❌ Вы ещё не подписались на канал!", show_alert=True)
        return
    await callback.message.delete()
    await _give_access(callback.message, callback.from_user)
    await callback.answer()


@router.callback_query(F.data == "my_link")
async def callback_my_link(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user or not user["is_active"]:
        await callback.answer("У вас нет активного прокси. Напишите /start", show_alert=True)
        return

    secret = await _ensure_user_proxy_secret(user, callback.from_user.id)
    if not secret:
        await callback.answer("Ссылка пока не готова. Напишите /start", show_alert=True)
        return

    await mtg.start_proxy(secret)
    link = mtg.build_proxy_link(secret)
    await callback.message.answer(
        f"🔗 <b>Ваша ссылка:</b>\n{link}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "my_status")
async def callback_my_status(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.answer("Вы не зарегистрированы.", show_alert=True)
        return

    status = "✅ Активен" if user["is_active"] else "❌ Отключён"
    left = user["left_channel_at"].strftime("%d.%m.%Y %H:%M UTC") if user["left_channel_at"] else "—"
    await callback.message.answer(
        f"📊 <b>Ваш статус</b>\n\n"
        f"Статус: {status}\n"
        f"Порт: {config.PROXY_PORT}\n"
        f"Вышел с канала: {left}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("status"))
async def cmd_status(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Вы не зарегистрированы. Напишите /start")
        return

    status = "✅ Активен" if user["is_active"] else "❌ Отключён"
    if user["is_active"]:
        secret = await _ensure_user_proxy_secret(user, message.from_user.id)
        if not secret:
            await message.answer("Ссылка пока не готова. Напишите /start")
            return

        await mtg.start_proxy(secret)
        link = mtg.build_proxy_link(secret)
        await message.answer(
            f"📊 Статус: {status}\n\n🔗 <b>Ваша ссылка:</b>\n{link}",
            parse_mode="HTML",
            reply_markup=proxy_keyboard(),
        )
    else:
        await message.answer(
            f"📊 Статус: {status}\n\nНапишите /start для восстановления доступа."
        )
