# Hiddify Telegram Shop & Reseller Bot

A Telegram bot designed for Hiddify panels with automated account generation, reseller management, and real-time subscription diagnostics.

## Features
- **Automated Sales & Wallet**: Users can browse packages, pay via card-to-card, and receive instant subscriptions.
- **Reseller System**: Delegated reseller accounts with allocated volume (GB) and expiration limits.
- **Diagnostics**: Users can send subscription URLs or UUIDs to view real-time traffic usage, online/offline status, and expiration dates.
- **Dynamic Config**: Automatically reads panel credentials from local files on the server with zero hardcoded secrets.

## Installation
Run the following script on your server as root:
```bash
bash <(curl -sL https://raw.githubusercontent.com/yekaweb/hiddify-telegram-shop-bot/main/install.sh)
```

## Maintenance
To refresh configuration or restore the service after panel updates:
```bash
bash /opt/deltaforce-shop/patch.sh
```

## License
MIT
