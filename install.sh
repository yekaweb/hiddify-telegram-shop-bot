#!/bin/bash
# ==============================================================================
# Hiddify Telegram Shop & Reseller Bot - 1-Click Universal Installer & Patcher
# Compatible with all Hiddify Manager versions (v10, v11, v14+)
# ==============================================================================
set -e

REPO_URL="https://github.com/yekaweb/hiddify-telegram-shop-bot.git"
INSTALL_DIR="/opt/deltaforce-shop"
SERVICE_NAME="deltaforce-shop.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

echo ""
echo "===================================================================="
echo "🚀  Hiddify Telegram Shop & Reseller Bot - Automated Installer     "
echo "===================================================================="
echo ""

# 1. Root check
if [ "$EUID" -ne 0 ]; then
    echo "❌ Error: Please run this installer as root (sudo bash ...)"
    exit 1
fi

# 2. Check Hiddify Installation
if [ ! -d "/opt/hiddify-manager" ] && [ ! -d "/opt/hiddify-config" ]; then
    echo "⚠️ Warning: Hiddify Manager was not detected in /opt/hiddify-manager."
    echo "Please make sure Hiddify is installed on this server first."
fi

# 3. Detect Python Environment
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
    echo "❌ Error: Could not locate a working Python environment."
    exit 1
fi

echo "🔍 Detected Python: $PYTHON_BIN"

# 4. Parse Arguments (if passed)
BOT_TOKEN_ARG=""
ADMIN_ID_ARG=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --token) BOT_TOKEN_ARG="$2"; shift ;;
        --admin) ADMIN_ID_ARG="$2"; shift ;;
        *) echo "Unknown parameter: $1" ;;
    esac
    shift
done

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# 5. Handle Configuration (.env)
ENV_FILE="$INSTALL_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo ""
    echo "⚙️ First-Time Setup: Please provide your Telegram Bot credentials"
    echo "----------------------------------------------------------------"
    
    if [ -n "$BOT_TOKEN_ARG" ]; then
        BOT_TOKEN="$BOT_TOKEN_ARG"
    else
        read -rp "🤖 Enter your Telegram Bot Token (from @BotFather): " BOT_TOKEN
    fi
    
    if [ -n "$ADMIN_ID_ARG" ]; then
        ADMIN_ID="$ADMIN_ID_ARG"
    else
        read -rp "👤 Enter your Telegram Admin Numeric ID (from @userinfobot): " ADMIN_ID
    fi

    cat << EOF > "$ENV_FILE"
BOT_TOKEN=${BOT_TOKEN}
ADMIN_ID=${ADMIN_ID}
CHANNEL_USERNAME=@DeltaForce_Net
CHANNEL_URL=https://t.me/DeltaForce_Net
SUPPORT_BOT_USERNAME=@DeltaForce_supbot
SUPPORT_BOT_URL=https://t.me/DeltaForce_supbot
DEFAULT_CARD_NUMBER=6037-0000-0000-0000
DEFAULT_CARD_HOLDER=مدیریت فروشگاه
ZARINPAL_MERCHANT=
ZARINPAL_SANDBOX=0
ZIBAL_MERCHANT=
GATEWAY_CALLBACK_PORT=8088
EOF
    echo "✅ Saved configuration to $ENV_FILE"
else
    echo "✅ Existing configuration detected at $ENV_FILE (kept safe)."
fi

# 6. Ensure Git is installed & update/clone code
if command -v git >/dev/null 2>&1; then
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo "📥 Updating repository files..."
        git pull origin main || true
    fi
fi

# 7. Install/Verify Python Dependencies
echo "📦 Verifying Python dependencies..."
"$PYTHON_BIN" -c "import telebot, requests" 2>/dev/null || {
    "$PYTHON_BIN" -m pip install -q pyTelegramBotAPI requests
}

# 8. Initialize SQLite Database
echo "🗄️ Initializing/migrating database..."
"$PYTHON_BIN" -c "import sys; sys.path.append('$INSTALL_DIR'); import database; database.init_db(); print('Database ready.')"

# 8.5 Neutralize Hiddify's internal bot in MariaDB/MySQL & current.json (prevents webhook hijack)
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

"$PYTHON_BIN" << 'PYEOF'
import json, os
for cp in ["/opt/hiddify-manager/data/current.json", "/opt/hiddify-panel/data/current.json", "/opt/hiddify-config/data/current.json"]:
    if os.path.exists(cp):
        try:
            with open(cp, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            if cdata.get("telegram_enable") is True or cdata.get("telegram_bot_token") != "":
                cdata["telegram_enable"] = False
                cdata["telegram_bot_token"] = ""
                with open(cp, "w", encoding="utf-8") as f:
                    json.dump(cdata, f, indent=2)
                print(f"🛡️ Neutralized Hiddify internal bot in {cp}")
        except Exception:
            pass
PYEOF

# 9. Clear Telegram Webhook
"$PYTHON_BIN" << 'PYEOF'
import urllib.request, re, os

env_path = "/opt/deltaforce-shop/.env"
token = None
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

if token:
    try:
        url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True"
        req = urllib.request.Request(url, headers={"User-Agent": "DeltaForceBot/1.0"})
        urllib.request.urlopen(req, timeout=8)
        print("🧹 Telegram Webhook cleared successfully.")
    except Exception as e:
        print(f"⚠️ Webhook clear notice: {e}")
PYEOF

# 10. Install & Restart systemd Service
echo "⚙️ Configuring systemd daemon..."
cat << EOF > "$SERVICE_FILE"
[Unit]
Description=Hiddify Telegram Shop & Reseller Bot Daemon
After=network.target hiddify-panel.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_BIN $INSTALL_DIR/shop_bot.py
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
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1
systemctl restart "$SERVICE_NAME"
sleep 2

STATUS=$(systemctl is-active "$SERVICE_NAME")
if [ "$STATUS" = "active" ]; then
    echo ""
    echo "===================================================================="
    echo "🎉 SUCCESS: Bot is ACTIVE and RUNNING!                             "
    echo "===================================================================="
    echo "Log command: journalctl -u $SERVICE_NAME -f"
    echo "Management:  systemctl restart $SERVICE_NAME"
    echo ""
else
    echo "⚠️ Warning: Service status is $STATUS. Check logs with: journalctl -u $SERVICE_NAME -n 25"
fi
