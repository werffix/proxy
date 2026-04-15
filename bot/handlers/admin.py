from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging
import html

import config
from db import database as db
from mtg import manager as mtg
import asyncio

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def escape_markup(text: str) -> str:
    return html.escape(str(text), quote=False) if text else ""


async def ensure_user_proxy_secret(user_row: dict | None) -> str | None:
    if not user_row:
        return None

    secret = mtg.ensure_secret(user_row["id"], user_row.get("secret"))
    if secret != user_row.get("secret") or user_row.get("port") is not None:
        await db.update_user_proxy(user_row["id"], secret, None)
        user_row["secret"] = secret
        user_row["port"] = None
    return secret


def user_domain_label(user_row: dict) -> str:
    secret = user_row.get("secret")
    if not mtg.is_current_secret(secret):
        return "—"
    try:
        return mtg.get_domain(secret)
    except ValueError:
        return "—"


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="adm_search")],
        [InlineKeyboardButton(text="👥 Активные", callback_data="adm_active")],
        [InlineKeyboardButton(text="⏳ Grace period", callback_data="adm_grace")],
        [InlineKeyboardButton(text="📣 Рассылка", callback_data="adm_broadcast")],
    ])


def user_action_keyboard(user_id: int, is_banned: bool, is_active: bool) -> InlineKeyboardMarkup:
    buttons = []
    if is_banned:
        buttons.append([InlineKeyboardButton(text="✅ Разбанить", callback_data=f"adm_unban_{user_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="🚫 Забанить", callback_data=f"adm_ban_{user_id}")])
    if is_active:
        buttons.append([InlineKeyboardButton(text="🔌 Отключить", callback_data=f"adm_disable_{user_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="✅ Включить", callback_data=f"adm_enable_{user_id}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="adm_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


class AdminStates(StatesGroup):
    waiting_search = State()
    waiting_broadcast = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = await db.get_stats()
    await message.answer(
        f"🛠 <b>Админ-панель</b>\n\n"
        f"👥 Всего: <b>{stats['total']}</b>\n"
        f"✅ Активных: <b>{stats['active']}</b>\n"
        f"⏳ Grace period: <b>{stats['grace']}</b>\n"
        f"🚫 Забанено: <b>{stats['banned']}</b>\n"
        f"🆕 Новых сегодня: <b>{stats['today']}</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.message.answer(
        "📣 <b>Рассылка</b>\n\n"
        "Отправьте сообщение для рассылки.\n"
        "Поддерживается текст, фото, видео, документы.\n\n"
        "Для отмены напишите /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminStates.waiting_broadcast)
async def adm_broadcast_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if message.text and message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ Рассылка отменена.")
        return

    await state.clear()
    users = await db.get_all_users()

    status_msg = await message.answer(
        f"⏳ Начинаю рассылку на <b>{len(users)}</b> пользователей...",
        parse_mode="HTML",
    )

    ok = 0
    fail = 0

    for user in users:
        try:
            await message.copy_to(user["id"])
            ok += 1
        except Exception as e:
            logger.warning(f"Broadcast failed for {user['id']}: {e}")
            fail += 1
        await asyncio.sleep(0.05) 

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📨 Отправлено: <b>{ok}</b>\n"
        f"❌ Не доставлено: <b>{fail}</b>",
        parse_mode="HTML",
    )

@router.callback_query(F.data == "adm_panel")
async def adm_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    stats = await db.get_stats()
    await callback.message.edit_text(
        f"🛠 <b>Админ-панель</b>\n\n"
        f"👥 Всего: <b>{stats['total']}</b>\n"
        f"✅ Активных: <b>{stats['active']}</b>\n"
        f"⏳ Grace period: <b>{stats['grace']}</b>\n"
        f"🚫 Забанено: <b>{stats['banned']}</b>\n"
        f"🆕 Новых сегодня: <b>{stats['today']}</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "adm_stats")
async def adm_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    stats = await db.get_stats()
    await callback.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего зарегистрировано: <b>{stats['total']}</b>\n"
        f"✅ Активных прокси: <b>{stats['active']}</b>\n"
        f"⏳ На grace period: <b>{stats['grace']}</b>\n"
        f"🚫 Заблокировано: <b>{stats['banned']}</b>\n"
        f"🆕 Новых сегодня: <b>{stats['today']}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm_panel")]
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "adm_search")
async def adm_search(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_search)
    await callback.message.answer("🔍 Введите username, имя или ID пользователя:")
    await callback.answer()


@router.message(AdminStates.waiting_search)
async def adm_search_result(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    users = await db.search_users(message.text.strip())
    if not users:
        await message.answer("❌ Пользователи не найдены.")
        return
    for user in users:
        await _send_user_card(message, user)



@router.callback_query(F.data == "adm_active")
async def adm_active(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    users = await db.get_all_active_users()

    if not users:
        await callback.answer("Нет активных пользователей.", show_alert=True)
        return

    text = f"✅ <b>Активные ({len(users)})</b>\n\n"

    for u in users[:20]:
        name = escape_markup(u.get("full_name") or "—")
        uname_raw = f"@{u['username']}" if u.get("username") else str(u.get("id"))
        uname = escape_markup(uname_raw)
        domain = escape_markup(user_domain_label(u))

        text += f"• {name} ({uname}) — {config.PROXY_PORT} / {domain}\n"

    if len(users) > 20:
        text += f"\n...и ещё {len(users) - 20}"

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "adm_grace")
async def adm_grace(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    users = await db.get_users_to_warn() + await db.get_users_to_block()
    if not users:
        await callback.answer("Нет пользователей на grace period.", show_alert=True)
        return
    text = f"⏳ <b>Grace period ({len(users)})</b>\n\n"
    for u in users:
        name = u["full_name"] or "—"
        left_at = u["left_channel_at"].strftime("%d.%m %H:%M") if u["left_channel_at"] else "—"
        text += f"• {name} — вышел {left_at}\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("adm_ban_"))
async def adm_ban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    secret = await ensure_user_proxy_secret(user)
    if secret:
        await mtg.stop_proxy(secret)
    await db.ban_user(user_id)
    try:
        await callback.bot.send_message(user_id, "🚫 Ваш доступ к прокси заблокирован администратором.")
    except Exception:
        pass
    await callback.answer("✅ Заблокирован", show_alert=True)
    await _refresh_user_card(callback, user_id)


@router.callback_query(F.data.startswith("adm_unban_"))
async def adm_unban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    await db.unban_user(user_id)
    try:
        await callback.bot.send_message(user_id, "✅ Вы разблокированы. Напишите /start для получения прокси.")
    except Exception:
        pass
    await callback.answer("✅ Разблокирован", show_alert=True)
    await _refresh_user_card(callback, user_id)


@router.callback_query(F.data.startswith("adm_disable_"))
async def adm_disable(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    user = await db.get_user(user_id)
    secret = await ensure_user_proxy_secret(user)
    if secret:
        await mtg.stop_proxy(secret)
    await db.set_user_active(user_id, False)
    await callback.answer("🔌 Отключён", show_alert=True)
    await _refresh_user_card(callback, user_id)


@router.callback_query(F.data.startswith("adm_enable_"))
async def adm_enable(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split("_")[-1])
    user = await db.get_user(user_id)
    secret = await ensure_user_proxy_secret(user)
    if secret:
        await mtg.start_proxy(secret)
        await db.set_user_active(user_id, True)
    await callback.answer("✅ Включён", show_alert=True)
    await _refresh_user_card(callback, user_id)


async def _send_user_card(message: Message, user: dict):
    await ensure_user_proxy_secret(user)
    name = escape_markup(user["full_name"] or "—")
    uname = escape_markup(f"@{user['username']}" if user["username"] else "—")
    status = "✅ Активен" if user["is_active"] else "❌ Отключён"
    banned = "🚫 Да" if user["is_banned"] else "Нет"
    left = escape_markup(user["left_channel_at"].strftime("%d.%m.%Y %H:%M") if user["left_channel_at"] else "—")
    domain = escape_markup(user_domain_label(user))
    await message.answer(
        f"👤 <b>{name}</b> ({uname})\n"
        f"🆔 ID: <code>{user['id']}</code>\n"
        f"🔌 Порт: {config.PROXY_PORT}\n"
        f"🌐 Домен: {domain}\n"
        f"📶 Статус: {status}\n"
        f"🚫 Бан: {banned}\n"
        f"📤 Вышел с канала: {left}",
        parse_mode="HTML",
        reply_markup=user_action_keyboard(user["id"], user["is_banned"], user["is_active"]),
    )


async def _refresh_user_card(callback: CallbackQuery, user_id: int):
    user = await db.get_user(user_id)
    if user:
        await ensure_user_proxy_secret(user)
        name = escape_markup(user["full_name"] or "—")
        uname = escape_markup(f"@{user['username']}" if user["username"] else "—")
        status = "✅ Активен" if user["is_active"] else "❌ Отключён"
        banned = "🚫 Да" if user["is_banned"] else "Нет"
        domain = escape_markup(user_domain_label(user))
        await callback.message.edit_text(
            f"👤 <b>{name}</b> ({uname})\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"🔌 Порт: {config.PROXY_PORT}\n"
            f"🌐 Домен: {domain}\n"
            f"📶 Статус: {status}\n"
            f"🚫 Бан: {banned}",
            parse_mode="HTML",
            reply_markup=user_action_keyboard(user_id, user["is_banned"], user["is_active"]),
        )
