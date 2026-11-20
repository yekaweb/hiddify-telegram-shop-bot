from telebot import types
from config import ADMIN_ID, CHANNEL_URL, SUPPORT_BOT_URL

def main_menu(user_id: int):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    b_buy = types.KeyboardButton("🛍 خرید اشتراک")
    b_test = types.KeyboardButton("🎁 دریافت اکانت تستی")
    b_my_subs = types.KeyboardButton("📥 اشتراک‌های من")
    b_query = types.KeyboardButton("🔍 استعلام وضعیت اشتراک")
    b_reseller = types.KeyboardButton("💼 پنل فروشندگان و همکاران")
    b_wallet = types.KeyboardButton("💳 کیف پول")
    b_invite = types.KeyboardButton("👥 دعوت دوستان")
    b_proxy = types.KeyboardButton("⚡️ پروکسی رایگان")
    b_tutorials = types.KeyboardButton("📱 راهنمای اتصال")
    b_support = types.KeyboardButton("💬 تیکت و پشتیبانی")
    b_channel = types.KeyboardButton("📢 کانال رسمی")
    b_rules = types.KeyboardButton("📜 قوانین و راهنما")

    markup.add(b_buy, b_test)
    markup.add(b_my_subs, b_query)
    markup.add(b_reseller, b_wallet)
    markup.add(b_invite, b_proxy)
    markup.add(b_tutorials, b_support)
    markup.add(b_channel, b_rules)

    if user_id == ADMIN_ID:
        markup.add(types.KeyboardButton("👑 پنل مدیریت ارشد و هیدیفای"))

    return markup

def plans_keyboard(plans):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for p in plans:
        btn_text = f"{p['name']} — {p['price_toman']:,} تومان"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"buy_plan_{p['id']}"))

    markup.add(types.InlineKeyboardButton("⭐️ پلن دلخواه (محاسبه‌گر حجم و روز)", callback_data="buy_custom_plan"))
    markup.add(types.InlineKeyboardButton("‹ بازگشت به منو", callback_data="back_to_main"))
    return markup

def order_checkout_keyboard(order_id: str, has_discount: bool = False, wallet_balance: int = 0, final_price: int = 0):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if wallet_balance >= final_price and final_price > 0:
        markup.add(types.InlineKeyboardButton(f"💰 پرداخت از موجودی کیف پول ({wallet_balance:,} ت)", callback_data=f"pay_wallet_{order_id}"))
    markup.add(types.InlineKeyboardButton("💳 پرداخت کارت‌به‌کارت", callback_data=f"pay_card_{order_id}"))
    markup.add(types.InlineKeyboardButton("🌐 درگاه‌های آنلاین ریالی", callback_data=f"pay_online_{order_id}"))
    if not has_discount:
        markup.add(types.InlineKeyboardButton("🎟 وارد کردن کد تخفیف", callback_data=f"apply_discount_{order_id}"))
    markup.add(types.InlineKeyboardButton("✏️ تنظیم نام دلخواه برای کانفیگ", callback_data=f"set_custom_name_{order_id}"))
    markup.add(types.InlineKeyboardButton("❌ انصراف و بازگشت", callback_data="cancel_order"))
    return markup

def wallet_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("👥 دریافت لینک دعوت و زیرمجموعه‌گیری", callback_data="open_referral_section"))
    markup.add(types.InlineKeyboardButton("🛍 خرید اشتراک با موجودی کیف پول", callback_data="buy_from_wallet"))
    return markup

def referral_keyboard(user_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    ref_url = f"https://t.me/DeltaForceNetbot?start=ref_{user_id}"
    share_text = "اتصال پرسرعت، بدون قطعی و با پینگ عالی به اینترنت آزاد با دلتا فورس نت! برای دریافت تست رایگان یا خرید اشتراک روی لینک زیر بزنید:"
    import urllib.parse
    encoded_share = urllib.parse.quote(f"{share_text}\n{ref_url}")
    share_link = f"https://t.me/share/url?url={ref_url}&text={urllib.parse.quote(share_text)}"
    markup.add(types.InlineKeyboardButton("📤 ارسال لینک دعوت برای دوستان", url=share_link))
    markup.add(types.InlineKeyboardButton("💳 مشاهده موجودی کیف پول", callback_data="open_wallet_section"))
    return markup

def gateways_keyboard(order_id: str):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💳 درگاه ریالی تون‌پیز (بزودی)", callback_data=f"gw_tonpees_{order_id}"))
    markup.add(types.InlineKeyboardButton("💳 درگاه ریالی تون‌یار (بزودی)", callback_data=f"gw_tonyar_{order_id}"))
    markup.add(types.InlineKeyboardButton("💳 درگاه ریالی ترونادو (بزودی)", callback_data=f"gw_tronado_{order_id}"))
    markup.add(types.InlineKeyboardButton("‹ بازگشت به روش‌های پرداخت", callback_data=f"back_to_order_{order_id}"))
    return markup

def card_payment_keyboard(order_id: str):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("📤 ارسال عکس فیش واریزی", callback_data=f"send_receipt_{order_id}"))
    markup.add(types.InlineKeyboardButton("‹ بازگشت", callback_data=f"back_to_order_{order_id}"))
    return markup

def admin_receipt_keyboard(order_id: str):
    markup = types.InlineKeyboardMarkup(row_width=2)
    b_approve = types.InlineKeyboardButton("✅ تایید و صدور آنی", callback_data=f"adm_app_{order_id}")
    b_reject = types.InlineKeyboardButton("❌ رد فیش", callback_data=f"adm_rej_{order_id}")
    markup.add(b_approve, b_reject)
    return markup

def sub_details_keyboard(sub_url: str, user_uuid: str = None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🌐 صفحه هوشمند اشتراک", url=sub_url),
        types.InlineKeyboardButton("📋 کپی لینک اتصال", callback_data=f"copy_sub_{user_uuid}" if user_uuid else "copy_sub")
    )
    markup.add(
        types.InlineKeyboardButton("🔄 تمدید اشتراک", callback_data=f"renew_sub_{user_uuid}" if user_uuid else "renew_sub"),
        types.InlineKeyboardButton("📱 راهنمای اتصال", callback_data="open_tutorials")
    )
    markup.add(types.InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="back_to_main"))
    return markup

def cancel_sub_query_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف و بازگشت", callback_data="cancel_sub_query"))
    return markup

def empty_subs_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🛍 خرید اشتراک جدید", callback_data="open_plans"))
    markup.add(types.InlineKeyboardButton("🎁 دریافت اکانت تستی (رایگان)", callback_data="get_free_test"))
    markup.add(types.InlineKeyboardButton("🔍 استعلام و اتصال لینک اشتراک", callback_data="query_sub_link"))
    markup.add(types.InlineKeyboardButton("‹ بازگشت به منوی اصلی", callback_data="back_to_main"))
    return markup

def reseller_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    b_new_user = types.KeyboardButton("➕ صدور اکانت مشتری")
    b_users_list = types.KeyboardButton("👥 لیست کاربران من")
    b_stats = types.KeyboardButton("📊 موجودی و آمار سهمیه")
    b_renew = types.KeyboardButton("🔄 تمدید اکانت مشتری")
    b_logout = types.KeyboardButton("🚪 خروج از حساب نمایندگی")
    b_back = types.KeyboardButton("‹ بازگشت به منوی کاربری")

    markup.add(b_new_user, b_users_list)
    markup.add(b_stats, b_renew)
    markup.add(b_logout, b_back)
    return markup

def reseller_cancel_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="reseller_cancel"))
    return markup

def admin_resellers_menu_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("➕ افزودن فروشنده جدید", callback_data="adm_add_reseller"))
    markup.add(types.InlineKeyboardButton("📋 لیست و آمار فروشندگان", callback_data="adm_list_resellers"))
    markup.add(types.InlineKeyboardButton("‹ بازگشت به مدیریت ارشد", callback_data="open_admin_panel"))
    return markup

def admin_reseller_detail_keyboard(reseller_id: int, is_active: bool):
    markup = types.InlineKeyboardMarkup(row_width=2)
    b_charge = types.InlineKeyboardButton("➕ شارژ سهمیه (گیگ)", callback_data=f"adm_chg_res_{reseller_id}")
    b_extend = types.InlineKeyboardButton("⏳ تمدید تاریخ انقضا", callback_data=f"adm_ext_res_{reseller_id}")
    toggle_txt = "🔴 مسدودسازی" if is_active else "🟢 فعال‌سازی"
    b_toggle = types.InlineKeyboardButton(toggle_txt, callback_data=f"adm_tog_res_{reseller_id}")
    b_unlink = types.InlineKeyboardButton("🔓 خروج تلگرام", callback_data=f"adm_unl_res_{reseller_id}")
    b_del = types.InlineKeyboardButton("🗑 حذف نماینده", callback_data=f"adm_del_res_{reseller_id}")
    b_back = types.InlineKeyboardButton("‹ بازگشت به لیست", callback_data="adm_list_resellers")
    markup.add(b_charge, b_extend)
    markup.add(b_toggle, b_unlink)
    markup.add(b_del, b_back)
    return markup

def admin_panel_keyboard(admin_url: str):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 وضعیت سرورها و نودها", callback_data="adm_server_status"),
        types.InlineKeyboardButton("👥 کاربران و آنلاین‌ها", callback_data="adm_users_list")
    )
    markup.add(
        types.InlineKeyboardButton("➕ ایجاد کاربر دستی", callback_data="adm_new_user"),
        types.InlineKeyboardButton("💳 تنظیم شماره کارت", callback_data="adm_set_card")
    )
    markup.add(
        types.InlineKeyboardButton("📦 مدیریت پلن‌ها", callback_data="adm_list_plans"),
        types.InlineKeyboardButton("🎟 ساخت کد تخفیف", callback_data="adm_new_discount")
    )
    markup.add(
        types.InlineKeyboardButton("💼 مدیریت فروشندگان / همکاران", callback_data="adm_resellers"),
        types.InlineKeyboardButton("📑 فیش‌های منتظر تایید", callback_data="adm_pending_receipts")
    )
    markup.add(
        types.InlineKeyboardButton("📢 پیام همگانی", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("🖥 ورود به پنل وب هیدیفای", url=admin_url)
    )
    markup.add(
        types.InlineKeyboardButton("‹ بازگشت به منوی کاربری", callback_data="back_to_main")
    )
    return markup

def admin_plans_list_keyboard(plans):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for p in plans:
        status_dot = "🟢" if p["is_active"] else "🔴"
        btn_text = f"{status_dot} {p['name']} — {p['price_toman']:,} تومان"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"adm_plan_view_{p['id']}"))
    
    markup.add(types.InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="adm_add_plan"))
    markup.add(types.InlineKeyboardButton("⚙️ تنظیم نرخ پلن دلخواه (گیگ و روز)", callback_data="adm_rates_setting"))
    markup.add(types.InlineKeyboardButton("‹ بازگشت به مدیریت", callback_data="open_admin_panel"))
    return markup

def admin_plan_detail_keyboard(plan_id: int, is_active: bool):
    markup = types.InlineKeyboardMarkup(row_width=2)
    b_price = types.InlineKeyboardButton("✏️ تغییر قیمت", callback_data=f"adm_edit_price_{plan_id}")
    toggle_txt = "🔴 غیرفعال‌سازی" if is_active else "🟢 فعال‌سازی"
    b_toggle = types.InlineKeyboardButton(toggle_txt, callback_data=f"adm_toggle_plan_{plan_id}")
    b_del = types.InlineKeyboardButton("🗑 حذف پلن", callback_data=f"adm_del_plan_{plan_id}")
    b_back = types.InlineKeyboardButton("‹ بازگشت به لیست", callback_data="adm_list_plans")
    markup.add(b_price, b_toggle)
    markup.add(b_del, b_back)
    return markup

