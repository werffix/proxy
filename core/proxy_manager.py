# core/proxy_manager.py
import asyncio
import os
import signal
import logging
from pathlib import Path
from typing import List, Tuple

import config

logger = logging.getLogger(__name__)

# Если прокси управляется systemd/docker — ставим False
MANAGE_PROXY = os.getenv("MANAGE_PROXY", "false").lower() == "true"
_CONFIG_PATH = Path(os.getenv("PROXY_CONFIG", "/etc/mtproto-proxy.conf"))
_PID_PATH = Path(os.getenv("PROXY_PID", "/run/mtproto-proxy.pid"))


async def start_proxy():
    """Запускает mtproto-proxy как дочерний процесс (только если MANAGE_PROXY=True)"""
    if not MANAGE_PROXY:
        logger.info("Proxy management disabled. Assuming external service (systemd/docker).")
        return

    logger.info("Starting mtproto-proxy process...")
    cmd = [
        config.MTPROTO_BIN,
        "-p", str(config.PROXY_PORT),
        "-S", config.SHARED_SECRET,
        "--domain", config.PROXY_DOMAIN,
        "--fake-tls",
        "--log-level", "info"
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    logger.info(f"Proxy started with PID {process.pid}")
    return process


async def stop_proxy(process=None):
    """Останавливает процесс прокси"""
    if not MANAGE_PROXY or (process is None and not _PID_PATH.exists()):
        return

    if process and process.returncode is None:
        process.terminate()
        await process.wait()
        logger.info("Proxy process stopped")
    elif _PID_PATH.exists():
        try:
            pid = int(_PID_PATH.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM to PID {pid}")
        except Exception as e:
            logger.error(f"Failed to stop proxy: {e}")


async def reload_proxy():
    """Перезагружает конфигурацию прокси (SIGHUP)"""
    if not _PID_PATH.exists():
        logger.warning("PID file not found. Proxy may be managed externally.")
        return

    try:
        pid = int(_PID_PATH.read_text().strip())
        os.kill(pid, signal.SIGHUP)
        logger.info(f"Sent SIGHUP to proxy PID {pid}")
    except Exception as e:
        logger.error(f"Failed to reload proxy: {e}")


async def add_domain(user_id: int, secret: str):
    """
    Добавляет домен в конфигурацию и перезагружает прокси.
    ⚠️ Примечание: современные версии mtproto-proxy/mtg автоматически парсят домен из секрета.
    Этот метод нужен только если вы используете static-config режим.
    """
    domain = f"{config.USER_DOMAIN_PREFIX}{user_id}.{config.PROXY_DOMAIN}".lower()
    
    if not _CONFIG_PATH.exists():
        logger.info("No config file found. Assuming proxy auto-registers domains from secrets.")
        return

    content = _CONFIG_PATH.read_text()
    if domain in content.lower():
        logger.debug(f"Domain {domain} already present in config")
        return

    # Добавляем домен в секцию allowed_domains (адаптируйте под формат вашего конфига)
    new_line = f"allowed_domains: {domain}"
    updated = f"{content.rstrip()}\n{new_line}\n"
    _CONFIG_PATH.write_text(updated)
    logger.info(f"Added domain {domain} to config")

    await reload_proxy()


async def restore_proxies(active_users: List[Tuple[int, str, int]]):
    """Восстанавливает конфигурацию после перезапуска веб-приложения"""
    if not active_users:
        return

    logger.info(f"Restoring {len(active_users)} proxy entries...")
    for user_id, secret, _ in active_users:
        await add_domain(user_id, secret)
