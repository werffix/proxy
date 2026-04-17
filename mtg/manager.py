import asyncio
import logging
from collections.abc import Awaitable, Callable

import config
from mtg import client

logger = logging.getLogger(__name__)


def _pick_secret(secret_or_port, secret: str | None) -> str:
    if secret is not None:
        return secret
    if isinstance(secret_or_port, str):
        return secret_or_port
    raise ValueError("Secret is required")


def generate_secret(user_id: int) -> str:
    return client.generate_secret(user_id)


def ensure_secret(user_id: int, current_secret: str | None) -> str:
    return client.ensure_secret(user_id, current_secret)


def build_proxy_link(secret: str, port: int | None = None) -> str:
    return client.build_proxy_link(secret)


def get_domain(secret: str) -> str:
    return client.parse_domain_from_secret(secret)


def is_current_secret(secret: str | None) -> bool:
    return client.is_current_secret(secret)


async def start_proxy(secret_or_port, secret: str | None = None) -> bool:
    try:
        user_secret = _pick_secret(secret_or_port, secret)
        return await client.add_domain(get_domain(user_secret))
    except Exception as exc:
        logger.error("Failed to enable proxy access: %s", exc)
        return False


async def stop_proxy(secret_or_port, secret: str | None = None) -> bool:
    try:
        user_secret = _pick_secret(secret_or_port, secret)
        return await client.remove_domain(get_domain(user_secret))
    except Exception as exc:
        logger.error("Failed to disable proxy access: %s", exc)
        return False


async def restore_all(users: list[dict]) -> bool:
    domains: list[str] = []
    skipped = 0

    for user in users:
        if not user.get("is_active") or not user.get("secret"):
            continue
        if not client.is_current_secret(user["secret"]):
            skipped += 1
            continue
        domains.append(get_domain(user["secret"]))

    if not domains:
        logger.info("No active mtproto_proxy domains to sync")
        if skipped:
            logger.warning("Skipped %d users with legacy proxy secrets", skipped)
        return True

    ok = await client.sync_domains(domains)
    if ok:
        logger.info("Synced %d active mtproto_proxy domains", len(domains))
    if skipped:
        logger.warning("Skipped %d users with legacy proxy secrets", skipped)
    return ok


async def sync_active_users_loop(
    get_active_users: Callable[[], Awaitable[list[dict]]],
):
    while True:
        try:
            await restore_all(await get_active_users())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Active domain sync failed: %s", exc)
        await asyncio.sleep(config.MTPROTO_PROXY_SYNC_INTERVAL_SECONDS)
