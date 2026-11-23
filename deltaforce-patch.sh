#!/bin/bash
# ==============================================================
# Delta Force Net Shop Bot - Universal Fast Patcher & Self-Healer
# Compatible with all Hiddify Manager versions (v10, v11, v14+)
# ==============================================================
set -e

echo "🛡️  ========================================================"
echo "🛡️   Delta Force Net Shop Bot - Universal Auto Patcher   "
echo "🛡️  ========================================================"

SHOP_DIR="/opt/deltaforce-shop"
SERVICE_FILE="/etc/systemd/system/deltaforce-shop.service"

mkdir -p "$SHOP_DIR"

# 1. Auto-detect Python Environment across different Hiddify versions
PYTHON_BIN=""
CANDIDATES=(
    "/opt/hiddify-manager/.venv313/bin/python"
    "/opt/hiddify-manager/.venv/bin/python"
    "/opt/hiddify-config/.venv/bin/python"
    "/opt/hiddify-server/.venv/bin/python"
    "/usr/bin/python3"
)

for p in "${CANDIDATES[@]}"; do
    if [ -x "$p" ]; then
        PYTHON_BIN="$p"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Error: Python binary not found in any standard Hiddify environment!"
    exit 1
fi

echo "🔍 Detected Python: $PYTHON_BIN"

# 2. Ensure Required Dependencies (pyTelegramBotAPI, requests)
"$PYTHON_BIN" -c "import telebot, requests" 2>/dev/null || {
    echo "📦 Installing missing dependencies into $PYTHON_BIN..."
    "$PYTHON_BIN" -m pip install -q pyTelegramBotAPI requests
}

# 3. Dynamic Configuration Auto-Sync from Hiddify current.json
"$PYTHON_BIN" << 'PYEOF'
import json, os, re

config_paths = [
    "/opt/hiddify-manager/data/current.json",
    "/opt/hiddify-panel/data/current.json",
    "/opt/hiddify-config/data/current.json"
]

current_data = None
for cp in config_paths:
    if os.path.exists(cp):
        try:
            with open(cp, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
                break
        except Exception:
            pass

shop_config_path = "/opt/deltaforce-shop/config.py"
if current_data and os.path.exists(shop_config_path):
    api_path = current_data.get("api_path")
    api_key = current_data.get("api_key")
    
    # Client proxy path
    proxy_client = None
    chconfigs = current_data.get("chconfigs")
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
    
    # Active domain
    active_domain = None
    domains = current_data.get("domains")
    if isinstance(domains, list):
        for d in domains:
            if isinstance(d, dict) and d.get("domain"):
                active_domain = d.get("domain")
                break
            elif isinstance(d, str):
                active_domain = d
                break
    elif isinstance(domains, dict):
        for d in domains.values():
            if isinstance(d, dict) and d.get("domain"):
                active_domain = d.get("domain")
                break

    with open(shop_config_path, "r", encoding="utf-8") as f:
        conf_text = f.read()

    changed = False
    if api_path:
        new_base = f"https://127.0.0.1/{api_path}/api/v2/admin"
        if new_base not in conf_text:
            conf_text = re.sub(r'HIDDIFY_API_BASE\s*=\s*".*?"', f'HIDDIFY_API_BASE = "{new_base}"', conf_text)
            changed = True

    if api_key:
        if api_key not in conf_text:
            conf_text = re.sub(r'HIDDIFY_API_KEY\s*=\s*".*?"', f'HIDDIFY_API_KEY = "{api_key}"', conf_text)
            changed = True

    if proxy_client and active_domain:
        new_sub = f"https://{active_domain}/{proxy_client}"
        if new_sub not in conf_text:
            conf_text = re.sub(r'HIDDIFY_SUB_BASE\s*=\s*".*?"', f'HIDDIFY_SUB_BASE = "{new_sub}"', conf_text)
            changed = True

    if changed:
        with open(shop_config_path, "w", encoding="utf-8") as f:
            f.write(conf_text)
        print("🔄 Updated config.py with live Hiddify API credentials and domains.")
    else:
        print("✅ config.py is already synchronized with Hiddify.")

    # Neutralize Hiddify internal bot in current.json to prevent webhook hijacking
    if current_data:
        c_changed = False
        if current_data.get("telegram_enable") is True:
            current_data["telegram_enable"] = False
            c_changed = True
        if current_data.get("telegram_bot_token"):
            current_data["telegram_bot_token"] = ""
            c_changed = True
        if c_changed:
            for cp in config_paths:
                if os.path.exists(cp):
                    try:
                        with open(cp, "w", encoding="utf-8") as f:
                            json.dump(current_data, f, indent=2)
                        print(f"🛡️ Neutralized Hiddify internal bot setting in {cp}")
                    except Exception:
                        pass
PYEOF

# 3.5 Neutralize Hiddify's internal bot in MariaDB/MySQL
if command -v mariadb >/dev/null 2>&1 || command -v mysql >/dev/null 2>&1; then
    SQL_CLI="mariadb"
    command -v mariadb >/dev/null 2>&1 || SQL_CLI="mysql"
    CFG_FILE="/opt/hiddify-manager/data/hiddify-panel/app.cfg"
    if [ -f "$CFG_FILE" ]; then
        DB_USER=$(grep -oP "mysql\+mysqldb://\K[^:]+" "$CFG_FILE" 2>/dev/null || echo "hiddifypanel")
        DB_PASS=$(grep -oP "mysql\+mysqldb://[^:]+:\K[^@]+" "$CFG_FILE" 2>/dev/null || echo "")
        DB_NAME=$(grep -oP "localhost/\K[^?]+" "$CFG_FILE" 2>/dev/null || echo "hiddifypanel")
        
        $SQL_CLI -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "
            UPDATE bool_config SET value=0 WHERE \`key\`='telegram_enable';
            UPDATE str_config SET value='' WHERE \`key\`='telegram_bot_token';
        " >/dev/null 2>&1 || true
        echo "🛡️ Neutralized Hiddify internal bot in MariaDB ($DB_NAME)."
    fi
fi

# 4. Clear Telegram Webhook (Allows daemon to take full polling control instantly)
"$PYTHON_BIN" << 'PYEOF'
import urllib.request, re, os

token = None
conf_path = "/opt/deltaforce-shop/config.py"
env_path = "/opt/deltaforce-shop/.env"
if os.path.exists(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            match = re.search(r'BOT_TOKEN\s*=\s*["\']?(.*?)["\']?$', f.read(), re.M)
            if match:
                token = match.group(1).strip()
    except Exception:
        pass
if not token and os.path.exists(conf_path):
    try:
        with open(conf_path, "r", encoding="utf-8") as f:
            match = re.search(r'BOT_TOKEN\s*=\s*"(.*?)"', f.read())
            if match:
                token = match.group(1).strip()
    except Exception:
        pass

if token:
    try:
        url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True"
        req = urllib.request.Request(url, headers={"User-Agent": "DeltaForceBot/1.0"})
        urllib.request.urlopen(req, timeout=8)
        print("🧹 Webhook cleared & pending updates flushed.")
    except Exception as e:
        print(f"⚠️ Webhook clear note: {e}")
PYEOF

# 5. Ensure systemd daemon is using the exact detected Python
cat << EOF > "$SERVICE_FILE"
[Unit]
Description=Delta Force Net Shop Telegram Bot Daemon
After=network.target hiddify-panel.service

[Service]
Type=simple
User=root
WorkingDirectory=$SHOP_DIR
ExecStart=$PYTHON_BIN $SHOP_DIR/shop_bot.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Ensure Gateway Callback port is open if firewall is active
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw allow 8088/tcp comment 'Payment Gateway Callback' >/dev/null 2>&1 || true
fi

systemctl daemon-reload
systemctl enable deltaforce-shop.service >/dev/null 2>&1

# 6. Restart Service and Verify Health
systemctl restart deltaforce-shop.service
sleep 2

STATUS=$(systemctl is-active deltaforce-shop.service)
if [ "$STATUS" = "active" ]; then
    echo "🚀 Service Status: 🟢 ACTIVE (RUNNING)"
    echo "🎉 Delta Force Shop Bot patched & fully operational in < 3 seconds!"
else
    echo "⚠️ Service Status: $STATUS - check logs with: journalctl -u deltaforce-shop -n 20"
fi
