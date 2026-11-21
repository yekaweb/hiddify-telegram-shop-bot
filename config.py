import os
import json
import re
from pathlib import Path

# Load local .env if present
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass

# Telegram Configuration (Set via .env or Environment Variables)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Channel & Support Links
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@DeltaForce_Net")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/DeltaForce_Net")
SUPPORT_BOT_USERNAME = os.getenv("SUPPORT_BOT_USERNAME", "@DeltaForce_supbot")
SUPPORT_BOT_URL = os.getenv("SUPPORT_BOT_URL", "https://t.me/DeltaForce_supbot")

# Dynamic Hiddify Discovery (Auto-extracts local credentials from Hiddify on target server)
def _discover_hiddify():
    paths = [
        "/opt/hiddify-manager/data/current.json",
        "/opt/hiddify-panel/data/current.json",
        "/opt/hiddify-config/data/current.json"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    api_path = data.get("api_path", "")
                    api_key = data.get("api_key", "")
                    
                    proxy_client = ""
                    chconfigs = data.get("chconfigs")
                    if isinstance(chconfigs, dict):
                        for cfg in chconfigs.values():
                            if isinstance(cfg, dict) and cfg.get("proxy_path_client"):
                                proxy_client = cfg.get("proxy_path_client")
                                break
                    elif isinstance(chconfigs, list):
                        for cfg in chconfigs:
                            if isinstance(cfg, dict) and cfg.get("proxy_path_client"):
                                proxy_client = cfg.get("proxy_path_client")
                                break

                    domain = "127.0.0.1"
                    domains = data.get("domains")
                    if isinstance(domains, list):
                        for d in domains:
                            if isinstance(d, dict) and d.get("domain"):
                                domain = d.get("domain")
                                break
                            elif isinstance(d, str):
                                domain = d
                                break

                    return {
                        "api_base": f"https://127.0.0.1/{api_path}/api/v2/admin" if api_path else "https://127.0.0.1/api/v2/admin",
                        "api_key": api_key,
                        "sub_base": f"https://{domain}/{proxy_client}" if proxy_client else f"https://{domain}",
                        "admin_url": f"https://{domain}/{api_path}/{api_key}/" if (api_path and api_key) else f"https://{domain}/"
                    }
            except Exception:
                pass
    return {}

_h = _discover_hiddify()

# Hiddify API Settings
HIDDIFY_API_BASE = os.getenv("HIDDIFY_API_BASE", _h.get("api_base", "https://127.0.0.1/api/v2/admin"))
HIDDIFY_API_KEY = os.getenv("HIDDIFY_API_KEY", _h.get("api_key", ""))
HIDDIFY_SUB_BASE = os.getenv("HIDDIFY_SUB_BASE", _h.get("sub_base", ""))
HIDDIFY_ADMIN_URL = os.getenv("HIDDIFY_ADMIN_URL", _h.get("admin_url", "https://127.0.0.1/"))

# Database Path
DB_PATH = os.getenv("DB_PATH", "/opt/deltaforce-shop/shop.db")

# Default Base Rates (in Tomans)
DEFAULT_PRICE_PER_GB = int(os.getenv("DEFAULT_PRICE_PER_GB", "4500"))
DEFAULT_PRICE_PER_DAY = int(os.getenv("DEFAULT_PRICE_PER_DAY", "1000"))

# Default Card Details (Can be edited by admin in-bot)
DEFAULT_CARD_NUMBER = os.getenv("DEFAULT_CARD_NUMBER", "6037-9970-0000-0000")
DEFAULT_CARD_HOLDER = os.getenv("DEFAULT_CARD_HOLDER", "دلتا فورس نت")

# Payment Gateways (ZarinPal & Zibal)
ZARINPAL_MERCHANT = os.getenv("ZARINPAL_MERCHANT", "")
ZARINPAL_SANDBOX = os.getenv("ZARINPAL_SANDBOX", "0").lower() in ("1", "true", "yes")
ZIBAL_MERCHANT = os.getenv("ZIBAL_MERCHANT", "")
GATEWAY_CALLBACK_PORT = int(os.getenv("GATEWAY_CALLBACK_PORT", "8088"))

