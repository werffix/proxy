# core/proxy_generator.py
import re
import config

_SECRET_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FULL_PATTERN = re.compile(r"^ee[0-9a-f]{64}[0-9a-f]+$")


def _get_shared() -> str:
    secret = config.SHARED_SECRET
    if not _SECRET_PATTERN.fullmatch(secret):
        raise ValueError("SHARED_SECRET must be 32 (or 64) lowercase hex chars")
    return secret


def _user_domain(user_id: int) -> str:
    return f"{config.USER_DOMAIN_PREFIX}{user_id}.{config.PROXY_DOMAIN}".lower()


def generate_secret(user_id: int) -> str:
    """ee + shared_secret + hex(domain)"""
    domain = _user_domain(user_id)
    return f"ee{_get_shared()}{domain.encode().hex()}"


def validate_secret(secret: str) -> bool:
    if not secret or not _FULL_PATTERN.fullmatch(secret.lower()):
        return False
    try:
        _extract_domain(secret)
        return True
    except:
        return False


def _extract_domain(secret: str) -> str:
    secret = secret.lower()
    # 🔹 Для 32 hex: [34:], для 64 hex: [66:]
    domain_hex = secret[34:]  # Измените на [66:] если shared_secret = 64 hex
    return bytes.fromhex(domain_hex).decode("ascii")


def build_link(secret: str) -> str:
    return (
        f"https://t.me/proxy?"
        f"server={config.PROXY_HOST}"
        f"&port={config.PROXY_PORT}"
        f"&secret={secret}"
    )
