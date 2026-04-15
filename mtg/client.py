import asyncio
import logging
import re
from collections.abc import Iterable

import config

logger = logging.getLogger(__name__)

_HEX_SECRET_RE = re.compile(r"^[0-9a-f]{32}$")
_FULL_SECRET_RE = re.compile(r"^ee[0-9a-f]{32}[0-9a-f]+$")


def _shared_secret() -> str:
    secret = config.MTPROTO_PROXY_SHARED_SECRET.lower()
    if not _HEX_SECRET_RE.fullmatch(secret):
        raise ValueError("MTPROTO_PROXY_SHARED_SECRET must be 32 lowercase hex chars")
    return secret


def user_domain(user_id: int) -> str:
    return f"{config.MTPROTO_PROXY_DOMAIN_PREFIX}{user_id}.{config.PROXY_DOMAIN}".lower()


def generate_secret(user_id: int) -> str:
    domain = user_domain(user_id)
    return f"ee{_shared_secret()}{domain.encode().hex()}"


def ensure_secret(user_id: int, current_secret: str | None) -> str:
    if is_current_secret(current_secret):
        current_secret = current_secret.lower()
        if parse_domain_from_secret(current_secret) == user_domain(user_id):
            return current_secret
    return generate_secret(user_id)


def is_current_secret(secret: str | None) -> bool:
    if not secret:
        return False
    secret = secret.lower()
    if not _FULL_SECRET_RE.fullmatch(secret):
        return False
    if secret[2:34] != _shared_secret():
        return False
    try:
        parse_domain_from_secret(secret)
    except ValueError:
        return False
    return True


def parse_domain_from_secret(secret: str) -> str:
    if not secret:
        raise ValueError("Secret is empty")

    secret = secret.lower()
    if not _FULL_SECRET_RE.fullmatch(secret):
        raise ValueError("Secret must be an ee-hex fake-TLS secret")

    domain_hex = secret[34:]
    try:
        return bytes.fromhex(domain_hex).decode("ascii").lower()
    except ValueError as exc:
        raise ValueError("Secret contains invalid domain payload") from exc


def build_proxy_link(secret: str) -> str:
    return (
        f"https://t.me/proxy?"
        f"server={config.PROXY_HOST}"
        f"&port={config.PROXY_PORT}"
        f"&secret={secret}"
    )


def _escape_erlang_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def _run_proxy_command(*args: str) -> tuple[bool, str]:
    try:
        process = await asyncio.create_subprocess_exec(
            config.MTPROTO_PROXY_BIN,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("mtproto_proxy binary not found: %s", config.MTPROTO_PROXY_BIN)
        return False, ""
    except Exception as exc:
        logger.error("Failed to start mtproto_proxy command %s: %s", args, exc)
        return False, ""

    stdout, stderr = await process.communicate()
    stdout_text = stdout.decode(errors="replace").strip()
    stderr_text = stderr.decode(errors="replace").strip()

    if process.returncode != 0:
        logger.error(
            "mtproto_proxy command failed (%s): %s",
            " ".join(args),
            stderr_text or stdout_text or f"exit code {process.returncode}",
        )
        return False, stdout_text

    if stderr_text:
        logger.warning("mtproto_proxy stderr (%s): %s", " ".join(args), stderr_text)

    return True, stdout_text


async def _eval(expression: str) -> bool:
    ok, _ = await _run_proxy_command("eval", expression)
    return ok


async def add_domain(domain: str) -> bool:
    expression = (
        f'mtp_policy_table:add({config.MTPROTO_PROXY_DOMAIN_TABLE}, '
        f'tls_domain, "{_escape_erlang_string(domain.lower())}").'
    )
    return await _eval(expression)


async def remove_domain(domain: str) -> bool:
    expression = (
        f'mtp_policy_table:del({config.MTPROTO_PROXY_DOMAIN_TABLE}, '
        f'tls_domain, "{_escape_erlang_string(domain.lower())}").'
    )
    return await _eval(expression)


async def sync_domains(domains: Iterable[str]) -> bool:
    unique_domains = sorted({domain.lower() for domain in domains if domain})
    if not unique_domains:
        return True

    for domain in unique_domains:
        if not await add_domain(domain):
            return False

    return True
