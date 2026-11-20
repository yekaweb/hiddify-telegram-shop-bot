import requests
import urllib3
import logging
import re
from datetime import datetime, timedelta
import config
from config import HIDDIFY_API_BASE, HIDDIFY_API_KEY, HIDDIFY_SUB_BASE, HIDDIFY_ADMIN_URL

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("HiddifyAPI")

UUID_REGEX = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')

def extract_uuid_from_text(text: str):
    """Extract first valid UUID from raw text, subscription URL or vless link."""
    if not text:
        return None
    match = UUID_REGEX.search(str(text))
    if match:
        return match.group(0).lower()
    return None

def gregorian_to_jalali(gy, gm, gd):
    """Convert Gregorian date to Jalali (Persian Solar Hijri) date."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy if gm > 2 else gy - 1
    days = (365 * gy) + ((gy2 + 4) // 4) - ((gy2 + 100) // 100) + ((gy2 + 400) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd

def format_subscription_report(udata: dict, sub_record: dict = None) -> str:
    """
    Format a complete, luxurious Persian report for a subscription account.
    Includes:
    - Online / offline status with exact last connection delta
    - Account status (active, quota exhausted, expired, disabled)
    - Total, used, and remaining traffic in GB and percentage
    - Graphical progress bar
    - Start date and expiration date in Shamsi & Gregorian
    - Remaining validity days
    - Clickable subscription URL
    """
    # 1. Connection / Online status
    last_online_str = udata.get("last_online")
    online_text = "⚪️ آفلاین (تاکنون متصل نشده)"
    
    if last_online_str and not str(last_online_str).startswith("0001") and str(last_online_str).lower() != "none":
        try:
            clean_ts = str(last_online_str).split(".")[0]
            last_dt = datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
            now_dt = datetime.now()
            diff_sec = max(0, (now_dt - last_dt).total_seconds())
            
            if diff_sec < 300:  # Within 5 minutes
                online_text = "🟢 آنلاین (متصل به سرور)"
            elif diff_sec < 3600:
                mins = max(1, int(diff_sec // 60))
                online_text = f"⚪️ آفلاین ({mins} دقیقه پیش)"
            elif diff_sec < 86400:
                hours = int(diff_sec // 3600)
                online_text = f"⚪️ آفلاین ({hours} ساعت پیش)"
            else:
                days_ago = int(diff_sec // 86400)
                online_text = f"⚪️ آفلاین ({days_ago} روز پیش)"
        except Exception:
            online_text = f"⚪️ {last_online_str}"

    # 2. Traffic consumption & remaining
    used_gb = float(udata.get("current_usage_GB") or 0.0)
    limit_gb = float(udata.get("usage_limit_GB") or (sub_record.get("traffic_gb") if sub_record else 0.0))
    
    if limit_gb > 0:
        remaining_gb = max(0.0, round(limit_gb - used_gb, 2))
        percent_used = min(100.0, (used_gb / limit_gb) * 100.0)
        percent_remaining = max(0.0, 100.0 - percent_used)
    else:
        remaining_gb = 0.0
        percent_used = 0.0
        percent_remaining = 0.0
        
    bar_len = 10
    filled = int(round((percent_used / 100.0) * bar_len))
    filled = min(max(filled, 0), bar_len)
    progress_bar = "▰" * filled + "▱" * (bar_len - filled)

    # 3. Validity & Expiration dates
    start_date_str = udata.get("start_date")
    package_days = int(udata.get("package_days") or (sub_record.get("days") if sub_record else 30))
    month_names = ['', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
    is_expired = False

    if not start_date_str or str(start_date_str).strip().lower() in ["none", "null", ""]:
        start_date_display = "⏳ ثبت نشده (شمارش پس از اولین اتصال)"
        expiry_date_display = f"⏳ {package_days} روز پس از اولین اتصال"
        days_left_display = f"⏳ {package_days} روز کامل (هنوز استارت نخورده)"
    else:
        try:
            start_dt = datetime.strptime(str(start_date_str)[:10], "%Y-%m-%d").date()
            expiry_dt = start_dt + timedelta(days=package_days)
            today = datetime.now().date()
            days_left = (expiry_dt - today).days
            
            s_jy, s_jm, s_jd = gregorian_to_jalali(start_dt.year, start_dt.month, start_dt.day)
            e_jy, e_jm, e_jd = gregorian_to_jalali(expiry_dt.year, expiry_dt.month, expiry_dt.day)
            
            start_date_display = f"{s_jd} {month_names[s_jm]} {s_jy} ({start_dt})"
            expiry_date_display = f"{e_jd} {month_names[e_jm]} {e_jy} ({expiry_dt})"
            
            if days_left > 0:
                days_left_display = f"🟢 {days_left} روز باقی‌مانده"
            elif days_left == 0:
                days_left_display = "⚠️ امروز منقضی می‌شود!"
                is_expired = True
            else:
                days_left_display = f"🔴 {abs(days_left)} روز پیش منقضی شده"
                is_expired = True
        except Exception:
            start_date_display = str(start_date_str)
            expiry_date_display = "—"
            days_left_display = f"{package_days} روز"

    # 4. Overall account status
    is_deleted = udata.get("deleted", False)
    is_enable = udata.get("enable", True)

    if is_deleted or not is_enable:
        account_status = "⛔️ غیرفعال / مسدود"
    elif limit_gb > 0 and used_gb >= limit_gb:
        account_status = "⚠️ پایان حجم ترافیک"
    elif is_expired:
        account_status = "🔴 منقضی شده (اتمام زمان)"
    else:
        account_status = "🟢 فعال و آماده اتصال"

    # 5. Name & Sub URL
    name = udata.get("name") or (sub_record.get("name") if sub_record else "اشتراک دلتا فورس")
    uuid = udata.get("uuid", "")
    sub_url = udata.get("sub_url") or f"{HIDDIFY_SUB_BASE}/{uuid}/"

    text = (
        f"🛡 <b>مشخصات کامل اشتراک: {name}</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🌐 <b>وضعیت اتصال:</b> {online_text}\n"
        f"📌 <b>وضعیت اکانت:</b> {account_status}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"📊 <b>حجم مجاز کل:</b> <code>{limit_gb:.2f} گیگابایت</code>\n"
        f"📥 <b>حجم مصرف شده:</b> <code>{used_gb:.2f} گیگابایت</code> ({percent_used:.1f}%)\n"
        f"📤 <b>حجم باقی‌مانده:</b> <code>{remaining_gb:.2f} گیگابایت</code> ({percent_remaining:.1f}%)\n"
        f"📈 <b>پیشرفت مصرف:</b> <code>[{progress_bar}] {percent_used:.1f}%</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🗓 <b>تاریخ شروع:</b> {start_date_display}\n"
        f"⏳ <b>تاریخ انقضا:</b> {expiry_date_display}\n"
        f"⏱ <b>اعتبار زمانی:</b> {days_left_display}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 <b>لینک هوشمند اتصال (سابسکریپشن):</b>\n"
        f"<code>{sub_url}</code>\n\n"
        f"💡 <i>جهت کپی لینک اتصال، کافی است یک بار روی لینک کادر بالا ضربه بزنید.</i>"
    )
    return text


class HiddifyClient:
    def __init__(self, base_url=HIDDIFY_API_BASE, api_key=HIDDIFY_API_KEY, sub_base=HIDDIFY_SUB_BASE):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.sub_base = sub_base.rstrip('/')
        self.headers = {
            "Hiddify-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.admin_url = getattr(config, "HIDDIFY_ADMIN_URL", f"{self.base_url}/")

    def get_server_status(self):
        """Fetch real-time CPU, RAM, Disk, usage and online users from Hiddify."""
        url = f"{self.base_url}/server_status/"
        try:
            resp = requests.get(url, headers=self.headers, verify=False, timeout=10)
            if resp.status_code == 200:
                return True, resp.json()
            return False, f"Status: {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def get_nodes(self):
        """Fetch child nodes status (e.g. Turkey node)."""
        url = f"{self.base_url}/nodes/"
        try:
            resp = requests.get(url, headers=self.headers, verify=False, timeout=10)
            if resp.status_code == 200:
                return True, resp.json()
            return False, f"Status: {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def get_all_users(self):
        """Fetch all users list."""
        url = f"{self.base_url}/user/"
        try:
            resp = requests.get(url, headers=self.headers, verify=False, timeout=10)
            if resp.status_code == 200:
                return True, resp.json()
            return False, f"Status: {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def create_user(self, name: str, usage_limit_gb: float, package_days: int, telegram_id: int = None, comment: str = ""):
        """Create a new user in Hiddify."""
        url = f"{self.base_url}/user/"
        payload = {
            "name": name,
            "usage_limit_GB": float(usage_limit_gb),
            "package_days": int(package_days),
            "comment": comment or f"Shop Order - TG: {telegram_id}",
            "mode": "no_reset"
        }
        if telegram_id:
            payload["telegram_id"] = int(telegram_id)

        try:
            resp = requests.post(url, headers=self.headers, json=payload, verify=False, timeout=12)
            if resp.status_code in (200, 201):
                user_data = resp.json()
                u_uuid = user_data.get("uuid")
                user_data["sub_url"] = self.get_sub_url(u_uuid)
                user_data["b64_sub_url"] = self.get_b64_sub_url(u_uuid)
                return True, user_data
            else:
                logger.error(f"Failed to create user. Status: {resp.status_code}, Resp: {resp.text}")
                return False, f"API Error {resp.status_code}: {resp.text}"
        except Exception as e:
            logger.error(f"Exception creating user: {e}")
            return False, str(e)

    def get_user(self, user_uuid: str):
        """Fetch user profile by UUID."""
        url = f"{self.base_url}/user/{user_uuid}/"
        try:
            resp = requests.get(url, headers=self.headers, verify=False, timeout=10)
            if resp.status_code == 200:
                user_data = resp.json()
                user_data["sub_url"] = self.get_sub_url(user_uuid)
                user_data["b64_sub_url"] = self.get_b64_sub_url(user_uuid)
                return True, user_data
            return False, f"Status: {resp.status_code}"
        except Exception as e:
            logger.error(f"Exception fetching user {user_uuid}: {e}")
            return False, str(e)

    def add_traffic_and_days(self, user_uuid: str, add_gb: float = 0, add_days: int = 0):
        """Extend user volume or package days."""
        ok, user_data = self.get_user(user_uuid)
        if not ok:
            return False, user_data

        curr_gb = user_data.get("usage_limit_GB", 0)
        curr_days = user_data.get("package_days", 0)

        new_gb = curr_gb + float(add_gb)
        new_days = curr_days + int(add_days)

        url = f"{self.base_url}/user/{user_uuid}/"
        payload = {
            "usage_limit_GB": new_gb,
            "package_days": new_days
        }

        try:
            resp = requests.patch(url, headers=self.headers, json=payload, verify=False, timeout=10)
            if resp.status_code == 200:
                return True, resp.json()
            return False, f"Status {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, str(e)

    def get_sub_url(self, user_uuid: str):
        return f"{self.sub_base}/{user_uuid}/"

    def get_b64_sub_url(self, user_uuid: str):
        return f"{self.sub_base}/sub/{user_uuid}/"

    def find_user_by_name_or_uuid(self, identifier: str):
        """Find a user profile by UUID, URL or username/name."""
        if not identifier:
            return False, "شناسه خالی است"

        # 1. Try UUID regex extraction
        u_uuid = extract_uuid_from_text(identifier)
        if u_uuid:
            ok, user_data = self.get_user(u_uuid)
            if ok:
                return True, user_data

        # 2. Search across all users by name or comment
        clean_name = identifier.strip().lower()
        ok, users = self.get_all_users()
        if ok and isinstance(users, list):
            for u in users:
                if str(u.get("uuid", "")).lower() == clean_name:
                    u["sub_url"] = self.get_sub_url(u.get("uuid"))
                    u["b64_sub_url"] = self.get_b64_sub_url(u.get("uuid"))
                    return True, u
                if str(u.get("name", "")).strip().lower() == clean_name:
                    u["sub_url"] = self.get_sub_url(u.get("uuid"))
                    u["b64_sub_url"] = self.get_b64_sub_url(u.get("uuid"))
                    return True, u
                if clean_name in str(u.get("comment", "")).lower():
                    u["sub_url"] = self.get_sub_url(u.get("uuid"))
                    u["b64_sub_url"] = self.get_b64_sub_url(u.get("uuid"))
                    return True, u
        return False, "اشتراک با این مشخصات یافت نشد."
