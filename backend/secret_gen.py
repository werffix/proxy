import os
import base64
import hashlib
import secrets
from typing import Tuple

def generate_32byte_secret(domain: str = "google.com") -> Tuple[str, str, str]:
    """
    Генерирует секрет для mtg с новой структурой:
    - 16 байт: основной ключ
    - 16 байт: расширенный fingerprint (для обхода новых методов детекта)
    
    Возвращает: (hex_secret, base64_secret, tg_link_params)
    """
    # Основной 16-байтный секрет
    core_secret = secrets.token_bytes(16)
    
    # Дополнительный 16-байтный "отпечаток" (на основе домена + случайности)
    fingerprint_seed = (domain + secrets.token_hex(8)).encode()
    fingerprint = hashlib.sha256(fingerprint_seed).digest()[:16]
    
    # Объединяем: 32 байта итоговых данных
    full_secret = core_secret + fingerprint
    
    # Кодируем в hex (с префиксом ee для FakeTLS)
    hex_secret = "ee" + full_secret.hex()
    
    # Кодируем в base64 (альтернативный формат)
    b64_secret = base64.b64encode(full_secret).decode().rstrip('=')
    
    return hex_secret, b64_secret, domain

def generate_tg_proxy_link(server: str, port: int, secret: str, domain: str) -> str:
    """Создаёт tg:// deeplink для Telegram"""
    import urllib.parse
    # Секрет должен быть URL-encoded
    encoded_secret = urllib.parse.quote(secret, safe='')
    return f"tg://proxy?server={server}&port={port}&secret={encoded_secret}"
