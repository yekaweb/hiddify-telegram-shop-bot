import sqlite3
import os
import logging
from config import DB_PATH, DEFAULT_CARD_NUMBER, DEFAULT_CARD_HOLDER, DEFAULT_PRICE_PER_GB, DEFAULT_PRICE_PER_DAY

logger = logging.getLogger("ShopDB")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()

    # Users Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            wallet_balance INTEGER DEFAULT 0,
            invited_by INTEGER DEFAULT NULL,
            is_banned INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Referral Rewards History Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS referral_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            order_id TEXT NOT NULL,
            purchase_amount INTEGER NOT NULL,
            reward_amount INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Plans Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            traffic_gb REAL NOT NULL,
            days INTEGER NOT NULL,
            price_toman INTEGER NOT NULL,
            description TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        )
    """)

    # Orders Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            tg_id INTEGER NOT NULL,
            plan_name TEXT NOT NULL,
            traffic_gb REAL NOT NULL,
            days INTEGER NOT NULL,
            original_price INTEGER NOT NULL,
            final_price INTEGER NOT NULL,
            discount_code TEXT DEFAULT NULL,
            status TEXT DEFAULT 'pending_payment',
            payment_method TEXT DEFAULT 'card',
            receipt_photo_id TEXT DEFAULT NULL,
            track_id TEXT DEFAULT NULL,
            ref_id TEXT DEFAULT NULL,
            hiddify_uuid TEXT DEFAULT NULL,
            custom_name TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Dynamic migrations for orders table
    try:
        c.execute("ALTER TABLE orders ADD COLUMN track_id TEXT DEFAULT NULL")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE orders ADD COLUMN ref_id TEXT DEFAULT NULL")
    except Exception:
        pass

    # Subscriptions Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL,
            hiddify_uuid TEXT NOT NULL UNIQUE,
            name TEXT,
            traffic_gb REAL NOT NULL,
            days INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Discount Codes Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS discount_codes (
            code TEXT PRIMARY KEY,
            percent INTEGER DEFAULT 0,
            fixed_amount INTEGER DEFAULT 0,
            usage_limit INTEGER DEFAULT 100,
            used_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    """)

    # Settings Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Test Accounts Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS test_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL,
            hiddify_uuid TEXT NOT NULL,
            traffic_gb REAL DEFAULT 1.0,
            days INTEGER DEFAULT 30,
            used_traffic_gb REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Resellers Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS resellers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            tg_id INTEGER DEFAULT NULL,
            total_credit_gb REAL NOT NULL DEFAULT 0.0,
            used_credit_gb REAL NOT NULL DEFAULT 0.0,
            expire_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Reseller Users Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS reseller_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reseller_id INTEGER NOT NULL,
            hiddify_uuid TEXT NOT NULL UNIQUE,
            client_name TEXT NOT NULL,
            traffic_gb REAL NOT NULL,
            days INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Update price_per_gb to 4500 and delete 1GB test from plans table
    c.execute("UPDATE settings SET value = '4500' WHERE key = 'price_per_gb'")
    c.execute("DELETE FROM plans WHERE name LIKE '%تست%' OR traffic_gb = 1.0")
    conn.commit()

    # Seed default settings if not exists
    default_settings = {
        "card_number": DEFAULT_CARD_NUMBER,
        "card_holder": DEFAULT_CARD_HOLDER,
        "price_per_gb": str(DEFAULT_PRICE_PER_GB),
        "price_per_day": str(DEFAULT_PRICE_PER_DAY),
        "card_to_card_active": "1",
        "min_custom_gb": "5",
        "max_custom_gb": "300",
        "min_custom_days": "10",
        "max_custom_days": "180"
    }
    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Seed default plans if empty
    c.execute("SELECT COUNT(*) FROM plans")
    if c.fetchone()[0] == 0:
        default_plans = [
            ("⚡️ تست ۱ گیگ (۳ روزه)", 1.0, 3, 15000, "پلن تست کیفیت و پینگ", 1, 1),
            ("🥉 اقتصادی ۱۰ گیگ (۳۰ روزه)", 10.0, 30, 65000, "مناسب وبگردی و تلگرام", 1, 2),
            ("🥈 نقره‌ای ۲۰ گیگ (۳۰ روزه)", 20.0, 30, 115000, "مناسب اینستاگرام و استفاده روزمره", 1, 3),
            ("🥇 طلایی ۳۰ گیگ (۳۰ روزه)", 30.0, 30, 160000, "مناسب یوتیوب و دانلود", 1, 4),
            ("💎 الماس ۵۰ گیگ (۳۰ روزه)", 50.0, 30, 245000, "حرفه‌ای و بدون افت سرعت", 1, 5)
        ]
        c.executemany("""
            INSERT INTO plans (name, traffic_gb, days, price_toman, description, is_active, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, default_plans)

    conn.commit()
    conn.close()

def get_setting(key, default=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
              (key, str(value)))
    conn.commit()
    conn.close()

def save_or_update_user(tg_id, username, first_name, invited_by=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT tg_id, invited_by FROM users WHERE tg_id = ?", (tg_id,))
    row = c.fetchone()
    is_new_invite = False

    if row is None:
        # New user
        valid_inviter = None
        if invited_by and int(invited_by) != int(tg_id):
            # Verify inviter exists
            c.execute("SELECT tg_id FROM users WHERE tg_id = ?", (int(invited_by),))
            if c.fetchone():
                valid_inviter = int(invited_by)
                is_new_invite = True

        c.execute("""
            INSERT INTO users (tg_id, username, first_name, invited_by)
            VALUES (?, ?, ?, ?)
        """, (tg_id, username, first_name, valid_inviter))
    else:
        # Existing user - update username/first_name without changing invited_by
        c.execute("""
            UPDATE users SET username = ?, first_name = ? WHERE tg_id = ?
        """, (username, first_name, tg_id))

    conn.commit()
    conn.close()
    return is_new_invite

def add_wallet_balance(tg_id, amount):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE tg_id = ?", (int(amount), int(tg_id)))
    conn.commit()
    conn.close()

def deduct_wallet_balance(tg_id, amount):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT wallet_balance FROM users WHERE tg_id = ?", (int(tg_id),))
    row = c.fetchone()
    if not row or row[0] < int(amount):
        conn.close()
        return False
    c.execute("UPDATE users SET wallet_balance = wallet_balance - ? WHERE tg_id = ?", (int(amount), int(tg_id)))
    conn.commit()
    conn.close()
    return True

def record_referral_reward(inviter_id, buyer_id, order_id, purchase_amount, reward_amount):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO referral_rewards (inviter_id, buyer_id, order_id, purchase_amount, reward_amount)
        VALUES (?, ?, ?, ?, ?)
    """, (int(inviter_id), int(buyer_id), str(order_id), int(purchase_amount), int(reward_amount)))
    conn.commit()
    conn.close()

def get_user_referral_stats(tg_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE invited_by = ?", (int(tg_id),))
    invites_count = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(reward_amount), 0) FROM referral_rewards WHERE inviter_id = ?", (int(tg_id),))
    total_earned = c.fetchone()[0]
    conn.close()
    return invites_count, total_earned

def get_user(tg_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_active_plans():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM plans WHERE is_active = 1 ORDER BY sort_order ASC, id ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_plans():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM plans ORDER BY sort_order ASC, id ASC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_plan(name, traffic_gb, days, price_toman, description=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO plans (name, traffic_gb, days, price_toman, description, is_active, sort_order)
        VALUES (?, ?, ?, ?, ?, 1, 99)
    """, (name, float(traffic_gb), int(days), int(price_toman), description))
    conn.commit()
    conn.close()

def update_plan_price(plan_id, new_price):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE plans SET price_toman = ? WHERE id = ?", (int(new_price), int(plan_id)))
    conn.commit()
    conn.close()

def toggle_plan_status(plan_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE plans SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (int(plan_id),))
    conn.commit()
    conn.close()

def delete_plan(plan_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM plans WHERE id = ?", (int(plan_id),))
    conn.commit()
    conn.close()

def create_discount_code(code, percent=0, fixed_amount=0, usage_limit=100):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO discount_codes (code, percent, fixed_amount, usage_limit, used_count, is_active)
        VALUES (?, ?, ?, ?, 0, 1)
    """, (code.upper(), int(percent), int(fixed_amount), int(usage_limit)))
    conn.commit()
    conn.close()

def get_all_user_ids():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT tg_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_plan(plan_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def create_order(order_id, tg_id, plan_name, traffic_gb, days, original_price, final_price, custom_name=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO orders (order_id, tg_id, plan_name, traffic_gb, days, original_price, final_price, custom_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_id, tg_id, plan_name, traffic_gb, days, original_price, final_price, custom_name))
    conn.commit()
    conn.close()

def get_order(order_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_order_status(order_id, status, receipt_photo_id=None, hiddify_uuid=None):
    conn = get_connection()
    c = conn.cursor()
    if receipt_photo_id:
        c.execute("UPDATE orders SET status = ?, receipt_photo_id = ? WHERE order_id = ?", (status, receipt_photo_id, order_id))
    elif hiddify_uuid:
        c.execute("UPDATE orders SET status = ?, hiddify_uuid = ? WHERE order_id = ?", (status, hiddify_uuid, order_id))
    else:
        c.execute("UPDATE orders SET status = ? WHERE order_id = ?", (status, order_id))
    conn.commit()
    conn.close()

def update_order_gateway_track(order_id, payment_method, track_id):
    """Set the gateway method and payment authority/track_id for an order."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE orders SET payment_method = ?, track_id = ? WHERE order_id = ?",
              (payment_method, str(track_id), order_id))
    conn.commit()
    conn.close()

def get_order_by_track_id(track_id):
    """Lookup order by payment gateway authority or track_id."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE track_id = ?", (str(track_id),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def complete_paid_order(order_id, ref_id, hiddify_uuid=None):
    """Mark an order as completed with bank payment reference ID."""
    conn = get_connection()
    c = conn.cursor()
    if hiddify_uuid:
        c.execute("UPDATE orders SET status = 'completed', ref_id = ?, hiddify_uuid = ? WHERE order_id = ?",
                  (str(ref_id), hiddify_uuid, order_id))
    else:
        c.execute("UPDATE orders SET status = 'completed', ref_id = ? WHERE order_id = ?",
                  (str(ref_id), order_id))
    conn.commit()
    conn.close()

def add_user_subscription(tg_id, hiddify_uuid, name, traffic_gb, days):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO subscriptions (tg_id, hiddify_uuid, name, traffic_gb, days)
        VALUES (?, ?, ?, ?, ?)
    """, (tg_id, hiddify_uuid, name, traffic_gb, days))
    conn.commit()
    conn.close()

def get_user_subscriptions(tg_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE tg_id = ? ORDER BY id DESC", (tg_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def check_discount(code, original_price):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM discount_codes WHERE code = ? AND is_active = 1", (code,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False, "کد تخفیف نامعتبر است یا منقضی شده است.", original_price

    d = dict(row)
    if d["used_count"] >= d["usage_limit"]:
        return False, "ظرفیت استفاده از این کد تخفیف به پایان رسیده است.", original_price

    discount_amount = 0
    if d["percent"] > 0:
        discount_amount = int(original_price * (d["percent"] / 100.0))
    elif d["fixed_amount"] > 0:
        discount_amount = d["fixed_amount"]

    final_price = max(0, original_price - discount_amount)
    return True, f"کد تخفیف با موفقیت اعمال شد ({discount_amount:,} تومان تخفیف)", final_price

def get_referral_stats(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE invited_by = ?", (user_id,))
    count = c.fetchone()[0]
    c.execute("SELECT SUM(reward_amount) FROM referral_rewards WHERE inviter_id = ?", (user_id,))
    res = c.fetchone()
    total_rewards = res[0] or 0 if res else 0
    c.execute("SELECT wallet_balance FROM users WHERE tg_id = ?", (user_id,))
    row = c.fetchone()
    balance = row[0] if row else 0
    conn.close()
    return count, total_rewards, balance

def record_referral(new_user_id, inviter_id):
    if new_user_id == inviter_id:
        return
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT invited_by FROM users WHERE tg_id = ?", (new_user_id,))
    row = c.fetchone()
    if not row or not row[0]:
        c.execute("UPDATE users SET invited_by = ? WHERE tg_id = ?", (inviter_id, new_user_id))
    conn.commit()
    conn.close()

def reward_inviter(buyer_id, order_id, purchase_amount):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT invited_by FROM users WHERE tg_id = ?", (buyer_id,))
    row = c.fetchone()
    if not row or not row[0]:
        conn.close()
        return None, 0
    inviter_id = row[0]
    reward_amount = int(purchase_amount * 0.10)
    if reward_amount > 0:
        c.execute("""
            INSERT INTO referral_rewards (inviter_id, buyer_id, order_id, purchase_amount, reward_amount)
            VALUES (?, ?, ?, ?, ?)
        """, (inviter_id, buyer_id, order_id, purchase_amount, reward_amount))
        c.execute("UPDATE users SET wallet_balance = wallet_balance + ? WHERE tg_id = ?", (reward_amount, inviter_id))
        conn.commit()
    conn.close()
    return inviter_id, reward_amount

def get_user_test_account(tg_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM test_accounts WHERE tg_id = ? ORDER BY id DESC LIMIT 1", (tg_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def save_test_account(tg_id, hiddify_uuid, traffic_gb=1.0, days=30):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO test_accounts (tg_id, hiddify_uuid, traffic_gb, days)
        VALUES (?, ?, ?, ?)
    """, (tg_id, hiddify_uuid, float(traffic_gb), int(days)))
    conn.commit()
    conn.close()

# ----------------- Reseller Engine Functions -----------------

def create_reseller(name, username, password, total_credit_gb, expire_date):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO resellers (name, username, password, total_credit_gb, used_credit_gb, expire_date, is_active)
            VALUES (?, ?, ?, ?, 0.0, ?, 1)
        """, (name.strip(), username.strip().lower(), password.strip(), float(total_credit_gb), str(expire_date)))
        conn.commit()
        res_id = c.lastrowid
        conn.close()
        return True, res_id
    except sqlite3.IntegrityError:
        conn.close()
        return False, "این نام کاربری قبلاً برای فروشنده دیگری ثبت شده است."
    except Exception as e:
        conn.close()
        return False, str(e)

def get_reseller_by_username(username):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM resellers WHERE username = ?", (username.strip().lower(),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_reseller_by_id(reseller_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM resellers WHERE id = ?", (int(reseller_id),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_reseller_by_tg(tg_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM resellers WHERE tg_id = ? AND is_active = 1", (int(tg_id),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def authenticate_reseller(username, password, tg_id=None):
    r = get_reseller_by_username(username)
    if not r:
        return False, "نام کاربری یافت نشد."
    if r["password"] != password.strip():
        return False, "رمز عبور نادرست است."
    if not r["is_active"]:
        return False, "حساب نمایندگی شما توسط مدیریت غیرفعال شده است."

    if tg_id:
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE resellers SET tg_id = ? WHERE id = ?", (int(tg_id), r["id"]))
        conn.commit()
        conn.close()
        r["tg_id"] = int(tg_id)

    return True, r

def unbind_reseller_tg(reseller_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE resellers SET tg_id = NULL WHERE id = ?", (int(reseller_id),))
    conn.commit()
    conn.close()

def get_all_resellers():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM resellers ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_reseller_credit(reseller_id, add_gb):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE resellers SET total_credit_gb = total_credit_gb + ? WHERE id = ?", (float(add_gb), int(reseller_id)))
    conn.commit()
    conn.close()

def update_reseller_expiry(reseller_id, new_expire_date):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE resellers SET expire_date = ? WHERE id = ?", (str(new_expire_date), int(reseller_id)))
    conn.commit()
    conn.close()

def toggle_reseller_status(reseller_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE resellers SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (int(reseller_id),))
    conn.commit()
    conn.close()

def delete_reseller(reseller_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM reseller_users WHERE reseller_id = ?", (int(reseller_id),))
    c.execute("DELETE FROM resellers WHERE id = ?", (int(reseller_id),))
    conn.commit()
    conn.close()

def deduct_reseller_credit(reseller_id, gb):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE resellers SET used_credit_gb = used_credit_gb + ? WHERE id = ?", (float(gb), int(reseller_id)))
    conn.commit()
    conn.close()

def add_reseller_user(reseller_id, hiddify_uuid, client_name, traffic_gb, days):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO reseller_users (reseller_id, hiddify_uuid, client_name, traffic_gb, days)
        VALUES (?, ?, ?, ?, ?)
    """, (int(reseller_id), str(hiddify_uuid), str(client_name), float(traffic_gb), int(days)))
    conn.commit()
    conn.close()

def get_reseller_users(reseller_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM reseller_users WHERE reseller_id = ? ORDER BY id DESC", (int(reseller_id),))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_reseller_stats(reseller_id):
    r = get_reseller_by_id(reseller_id)
    if not r:
        return None
    users = get_reseller_users(reseller_id)
    remaining_gb = max(0.0, round(r["total_credit_gb"] - r["used_credit_gb"], 2))
    return {
        "name": r["name"],
        "username": r["username"],
        "total_gb": r["total_credit_gb"],
        "used_gb": round(r["used_credit_gb"], 2),
        "remaining_gb": remaining_gb,
        "expire_date": r["expire_date"],
        "is_active": bool(r["is_active"]),
        "tg_id": r["tg_id"],
        "users_count": len(users)
    }


