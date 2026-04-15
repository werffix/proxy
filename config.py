from dotenv import load_dotenv
import os


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS").split(",")]

# --- MySQL ---
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT"))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# --- Прокси ---
PROXY_HOST = os.getenv("PROXY_HOST")
PROXY_DOMAIN = os.getenv("PROXY_DOMAIN")
PROXY_PORT = int(os.getenv("PROXY_PORT"))

# --- mtproto_proxy ---
MTPROTO_PROXY_BIN = "/opt/mtp_proxy/bin/mtp_proxy"
MTPROTO_PROXY_SHARED_SECRET = "203a37a643a4d3061a53759e3fc7b210"
MTPROTO_PROXY_DOMAIN_TABLE = "customer_domains"
MTPROTO_PROXY_DOMAIN_PREFIX = "u"
MTPROTO_PROXY_SYNC_INTERVAL_SECONDS = 300
MTPROTO_PROXY_MAX_CONNECTIONS_PER_USER = 15

# --- Grace period ---
GRACE_PERIOD_HOURS = 0
WARNING_HOURS = 2
