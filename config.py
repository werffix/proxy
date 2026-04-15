# config.py
import os

# Сервер прокси (куда будут подключаться клиенты)
PROXY_HOST = os.getenv("PROXY_HOST", "your-server.com")
PROXY_PORT = int(os.getenv("PROXY_PORT", "443"))
PROXY_DOMAIN = os.getenv("PROXY_DOMAIN", "proxy.example.com")

# Префикс для доменов пользователей: u123.proxy.example.com
USER_DOMAIN_PREFIX = os.getenv("USER_DOMAIN_PREFIX", "u")

# Shared secret для Fake-TLS: 32 hex = 16 байт (стандарт MTProto)
# 🔹 Если нужен 32-байтный: замените на 64 hex
SHARED_SECRET = os.getenv("SHARED_SECRET", "dd" + "0" * 30).lower().replace("ee", "", 1)

# Путь к mtproto_proxy (если нужно управлять через API)
MTPROTO_BIN = os.getenv("MTPROTO_BIN", "/usr/bin/mtproto-proxy")

# Веб-сервер
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))

# База данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./proxy.db")

# 🔐 Опционально: простой пароль для защиты от спама
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")  # Если задан — требуется в запросе
