import os
import sys
import time
import uuid
import logging
from datetime import datetime, timedelta
import telebot
from telebot import types

import config
import database as db
from hiddify_api import HiddifyClient, extract_uuid_from_text, format_subscription_report, gregorian_to_jalali
import keyboards as kb

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("DeltaForceShop")

bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode="HTML")
hiddify = HiddifyClient()

# Initialize Database
db.init_db()

# User State Machine
USER_STATES = {}

def set_state(user_id, action, order_id=None, temp_data=None):
    USER_STATES[user_id] = {
        "action": action,
        "order_id": order_id,
        "temp_data": temp_data or {}
    }

def clear_state(user_id):
    if user_id in USER_STATES:
        del USER_STATES[user_id]

def get_state(user_id):
    return USER_STATES.get(user_id, {})

# ----------------- Interactive Utya Duck Animated Stickers -----------------

UTYA_STICKERS = {
    "WELCOME": "CAACAgIAAxUAAWsAAYm4I_MyNBaDXWrNIiBgLOQnSAACnhYAAqmhoUl3vDZi5x3Vyz0E",       # Wave 👋
    "SUCCESS": "CAACAgIAAxUAAWsAAYm4Dg3wKNOpXERM-SjiwSi8ewACiRYAAiRtqEmgs5Cl7C6yaT0E",       # Trophy 🏆
    "PARTY": "CAACAgIAAxUAAWsAAYm4evjj4Kp-wA3Ta0UjtzHcjAACknIAAmpkqEnvggE2BPv_Mj0E",         # Fireworks 🎆
    "GIFT": "CAACAgIAAxUAAWsAAYm4ag2ooR3BxS09va3RqUq_IAACJTQAAhoEQEmqYb9OMoLS9j0E",          # Gift Box 🎁
    "MONEY": "CAACAgIAAxUAAWsAAYm4q9FNx-rbcOtxedUvBfJa8QACwiQAAt-2eEuBossapGngyD0E",         # Money 💰
    "SEARCH": "CAACAgIAAxUAAWsAAYm4ILJQ1c97R5r4o_nZ1pMuOQACGUsAArka2Eq7PQ8qin9Npj0E",        # Magnifier 🔍
    "BUSINESS": "CAACAgIAAxUAAWsAAYm4aQbL2Txq_SYjZWokMLGXGQACURgAArxCoEnzGmJUCGyGWD0E",      # Suitcase / Business 🧳
    "COOL": "CAACAgIAAxUAAWsAAYm4Wn8Tl5zViLIpQ8z--drTHQACRisAAkc_eElkhCtjU_D2fD0E",          # Sunglasses Cool 😎
    "SUPPORT": "CAACAgIAAxUAAWsAAYm4qx6UAbSTneCJbDR-4_PrhwACgTsAAnipAUj9pG9INkJThT0E",       # Headset 🎧
    "ROCKET": "CAACAgIAAxUAAWsAAYm4eJTWadYcCK-h5vcgG1Kg6gACuzcAAt2VcUi2YGVardlUHD0E",        # Rocket 🚀
    "SHOPPING": "CAACAgIAAxUAAWsAAYm4d3NoWsqjV_3XQD4VLrSuIAAC2hkAAl60sUocVED83-8UGz0E",      # Shopping Bag 🛍
}

def send_sticker(chat_id, sticker_key):
    """Safely send an animated interactive Utya Duck sticker."""
    file_id = UTYA_STICKERS.get(sticker_key)
    if file_id:
        try:
            bot.send_sticker(chat_id, file_id)
        except Exception as e:
            logger.warning(f"Failed to send sticker {sticker_key}: {e}")

# ----------------- Start & Main Menu Handlers -----------------

@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "کاربر"

    # Check for referral parameter or deep link routing
    inviter_id = None
    direct_route = None
    parts = message.text.split()
    if len(parts) > 1:
        param = parts[1].strip()
        param_lower = param.lower()
        if param.startswith("ref_"):
            try:
                inviter_id = int(param.replace("ref_", ""))
            except ValueError:
                pass
        elif param.isdigit():
            inviter_id = int(param)
        elif param_lower in ["invite", "referral", "ref"]:
            direct_route = "invite"
        elif param_lower in ["wallet", "balance"]:
            direct_route = "wallet"
        elif param_lower in ["buy", "plans", "shop"]:
            direct_route = "buy"
        elif param_lower in ["test"]:
            direct_route = "test"

    is_new_invite = db.save_or_update_user(user_id, username, first_name, invited_by=inviter_id)
    clear_state(user_id)

    # Notify inviter of new registration
    if is_new_invite and inviter_id:
        try:
            bot.send_message(
                inviter_id,
                f"🎉 <b>یک دوست جدید با لینک اختصاصی شما عضو ربات شد!</b>\n\n"
                f"👤 نام: <b>{first_name}</b>\n"
                f"🆔 شناسه: <code>{user_id}</code>\n\n"
                f"💡 <i>به محض اولین خرید این کاربر، ۱۰٪ از مبلغ فاکتور به کیف پول شما واریز خواهد شد.</i>"
            )
        except Exception as e:
            logger.warning(f"Could not notify inviter {inviter_id}: {e}")

    markup = kb.main_menu(user_id)

    # Handle direct deep link actions (e.g. from channel buttons)
    if direct_route == "invite":
        show_referral(user_id)
        return
    elif direct_route == "wallet":
        show_wallet(user_id)
        return
    elif direct_route == "buy":
        plans = db.get_active_plans()
        bot.send_message(user_id, "🛍 <b>لطفاً یکی از پلن‌های اشتراک زیر را انتخاب فرمایید:</b>", reply_markup=kb.plans_keyboard(plans))
        return
    elif direct_route == "test":
        handle_get_test(user_id)
        return

    if user_id == config.ADMIN_ID:
        welcome_text = (
            f"👑 <b>درود بر شما مدیر ارشد دلتا فورس نت ({first_name})</b>\n\n"
            "شما با دسترسی نامحدود به سرور، پنل هیدیفای و فروشگاه وارد شدید.\n"
            "از طریق دکمه <b>«👑 پنل مدیریت ارشد و هیدیفای»</b> یا دستور <code>/admin</code> می‌توانید وضعیت زنده سرورها، کاربران آنلاین، نود ترکیه و ساخت یوزر را مدیریت کنید.\n\n"
            "👇 منوی اصلی سیستم برای شما فعال شد:"
        )
        inline_btn = types.InlineKeyboardMarkup()
        inline_btn.add(types.InlineKeyboardButton("👑 باز کردن پنل مدیریت ارشد", callback_data="open_admin_panel"))
        bot.send_message(user_id, welcome_text, reply_markup=markup)
        bot.send_message(user_id, "دسترسی سریع مدیریت:", reply_markup=inline_btn)
        return

    welcome_text = (
        f"👋 <b>سلام {first_name} عزیز، به سامانه هوشمند «دلتا فورس نت» خوش آمدید!</b>\n\n"
        "🚀 <b>مدرن‌ترین بستر ارائه سرویس‌های ضدفیلتر و پرسرعت بر پایه Sing-box & V2Ray:</b>\n"
        "🔒 تونل‌های پایدار، پینگ عالی مخصوص گیمینگ، ترید و استریم بدون افت کیفیت.\n\n"
        "⭐️ <b>امکانات سامانه:</b>\n"
        "▫️ تمدید و تحویل تمام خودکار ۲۴ ساعته\n"
        "▫️ استعلام حجم و روزهای باقیمانده لحظه‌ای\n"
        "▫️ پشتیبانی از تمام سیستم‌عامل‌ها (Android, iOS, Windows, Mac)\n"
        "▫️ امکان انتخاب پلن‌های آماده یا حجم دلخواه به انتخاب شما\n\n"
        "👇 <i>لطفاً یکی از گزینه‌های زیر را انتخاب فرمایید:</i>"
    )
    bot.send_message(user_id, welcome_text, reply_markup=markup)

@bot.message_handler(commands=["admin"])
def handle_admin_command(message):
    if message.from_user.id == config.ADMIN_ID:
        show_admin_panel(message.from_user.id)
    else:
        bot.reply_to(message, "⛔️ شما دسترسی به این بخش را ندارید.")

# ----------------- Main Menu Text Router -----------------

@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text_menu(message):
    user_id = message.from_user.id
    text = message.text.strip()
    state = get_state(user_id)

    # Active states
    if state.get("action") == "WAITING_SUB_QUERY":
        process_subscription_query(message)
        return
    elif state.get("action") == "WAITING_DISCOUNT":
        process_discount_code(message, state.get("order_id"))
        return
    elif state.get("action") == "WAITING_CUSTOM_NAME":
        process_custom_name(message, state.get("order_id"))
        return
    elif state.get("action") == "WAITING_CUSTOM_GB":
        process_custom_gb(message)
        return
    elif state.get("action") == "WAITING_CUSTOM_DAYS":
        process_custom_days(message)
        return
    elif state.get("action") == "ADMIN_SET_CARD":
        process_admin_set_card(message)
        return
    elif state.get("action") == "ADMIN_NEW_USER":
        process_admin_new_user(message)
        return
    elif state.get("action") == "ADMIN_EDIT_PRICE":
        process_admin_edit_price(message)
        return
    elif state.get("action") == "ADMIN_ADD_PLAN":
        process_admin_add_plan(message)
        return
    elif state.get("action") == "ADMIN_SET_RATES":
        process_admin_set_rates(message)
        return
    elif state.get("action") == "ADMIN_NEW_DISCOUNT":
        process_admin_new_discount(message)
        return
    elif state.get("action") == "ADMIN_BROADCAST":
        process_admin_broadcast(message)
        return
    elif state.get("action") == "WAITING_RESELLER_LOGIN":
        process_reseller_login(message)
        return
    elif state.get("action") == "RESELLER_CLIENT_NAME":
        process_reseller_client_name(message)
        return
    elif state.get("action") == "RESELLER_CLIENT_GB":
        process_reseller_client_gb(message)
        return
    elif state.get("action") == "RESELLER_CLIENT_DAYS":
        process_reseller_client_days(message)
        return
    elif state.get("action") == "RESELLER_RENEW_GB":
        process_reseller_renew_gb(message)
        return
    elif state.get("action") == "ADMIN_ADD_RES_NAME":
        process_admin_res_name(message)
        return
    elif state.get("action") == "ADMIN_ADD_RES_CRED":
        process_admin_res_cred(message)
        return
    elif state.get("action") == "ADMIN_ADD_RES_GB":
        process_admin_res_gb(message)
        return
    elif state.get("action") == "ADMIN_ADD_RES_DAYS":
        process_admin_res_days(message)
        return
    elif state.get("action") == "ADMIN_CHG_RES_GB":
        process_admin_chg_res_gb(message)
        return
    elif state.get("action") == "ADMIN_EXT_RES_DAYS":
        process_admin_ext_res_days(message)
        return

    # Standard Menu Buttons
    if text == "🛍 خرید اشتراک":
        show_plans(user_id)
    elif text in ["🎁 دریافت اکانت تستی", "🎁 دریافت اکانت تستی (رایگان)"]:
        handle_free_test_account(user_id)
    elif text == "📥 اشتراک‌های من":
        show_my_subscriptions(user_id)
    elif text in ["🔍 استعلام وضعیت اشتراک", "🔍 استعلام لینک اشتراک", "استعلام اشتراک", "استعلام", "🔍 استعلام"]:
        ask_subscription_link(user_id)
    elif text in ["💼 پنل فروشندگان و همکاران", "💼 پنل فروشندگان", "پنل فروشندگان", "فروشندگان"]:
        handle_reseller_entry(user_id)
    elif text == "➕ صدور اکانت مشتری":
        handle_reseller_new_user(user_id)
    elif text == "👥 لیست کاربران من":
        handle_reseller_users_list(user_id)
    elif text == "📊 موجودی و آمار سهمیه":
        handle_reseller_stats(user_id)
    elif text == "🔄 تمدید اکانت مشتری":
        handle_reseller_renew_prompt(user_id)
    elif text == "🚪 خروج از حساب نمایندگی":
        handle_reseller_logout(user_id)
    elif text == "‹ بازگشت به منوی کاربری":
        show_user_main_menu(user_id)
    elif text == "💳 کیف پول":
        show_wallet(user_id)
    elif text == "👥 دعوت دوستان":
        show_referral(user_id)
    elif text == "⚡️ پروکسی رایگان":
        show_proxy(user_id)
    elif text == "📱 راهنمای اتصال":
        show_tutorials(user_id)
    elif text == "💬 تیکت و پشتیبانی":
        show_support(user_id)
    elif text == "📢 کانال رسمی":
        show_channel(user_id)
    elif text == "📜 قوانین و راهنما":
        show_rules(user_id)
    elif text in ["👑 پنل مدیریت ارشد و هیدیفای", "⚙️ پنل مدیریت فروشگاه"] and user_id == config.ADMIN_ID:
        show_admin_panel(user_id)
    else:
        # Auto-detect subscription link, UUID or config sent in chat
        extracted_uuid = extract_uuid_from_text(text)
        if extracted_uuid or text.startswith(("http://", "https://", "vless://", "vmess://", "trojan://", "ss://", "tuic://", "hy2://")):
            process_subscription_query(message, forced_uuid=extracted_uuid)
            return

# ----------------- Free Test Account Handler -----------------

def handle_free_test_account(user_id):
    existing = db.get_user_test_account(user_id)
    if existing:
        u_uuid = existing["hiddify_uuid"]
        ok, udata = hiddify.get_user(u_uuid)
        if ok:
            usage = float(udata.get("current_usage_GB", 0))
            is_deleted = udata.get("deleted", False)

            # If the user consumed traffic (> 0.01 GB / 10 MB)
            if usage > 0.01:
                text = (
                    "⚠️ <b>کاربر گرامی، شما قبلاً سهمیه اکانت تستی خود را دریافت و مصرف کرده‌اید.</b>\n"
                    "➖➖➖➖➖➖➖➖➖➖\n"
                    f"📊 میزان مصرف شما: <b>{round(usage, 2)} گیگابایت</b>\n\n"
                    "طبق قوانین سامانه، هر کاربر تنها یک‌بار مجاز به مصرف ترافیک تستی می‌باشد.\n"
                    "جهت اتصال دائمی با سرعت و پینگ عالی، لطفاً از بخش <b>«🛍 خرید اشتراک»</b> پلن مورد نظرتان را تهیه فرمایید."
                )
                bot.send_message(user_id, text)
                return
            else:
                # Usage is 0, check if still active
                if not is_deleted:
                    sub_url = udata.get("sub_url")
                    text = (
                        "ℹ️ <b>کاربر گرامی، شما یک اکانت تستی فعال و مصرف‌نشده دارید!</b>\n"
                        "➖➖➖➖➖➖➖➖➖➖\n"
                        "این اشتراک هنوز معتبر است و از ترافیک آن استفاده نکرده‌اید.\n\n"
                        "📊 <b>حجم:</b> ۱ گیگابایت\n"
                        "⏳ <b>اعتبار:</b> ۳۰ روز\n"
                        "🌍 <b>سرورها:</b> سوییس و ترکیه\n"
                        "➖➖➖➖➖➖➖➖➖➖\n"
                        f"🔗 <b>لینک اتصال شما:</b>\n<code>{sub_url}</code>\n\n"
                        "💡 <i>لینک بالا را در برنامه متناسب با دستگاه خود (v2rayNG / Streisand / v2rayN / Hiddify) وارد فرمایید.</i>"
                    )
                    markup = kb.sub_details_keyboard(sub_url)
                    bot.send_message(user_id, text, reply_markup=markup)
                    return
        # If it was expired/deleted with 0 usage, allow them to get a fresh test account!

    # Issue a brand new free 1 GB / 30 Days test account!
    bot.send_message(user_id, "⏳ در حال صدور اکانت تستی رایگان ۱ گیگابایتی (۳۰ روزه) شما...")

    client_name = f"test-{user_id % 10000}-{int(time.time()) % 1000}"
    ok, result = hiddify.create_user(
        name=client_name,
        usage_limit_gb=1.0,
        package_days=30,
        telegram_id=user_id,
        comment="Free Test 1GB 30D"
    )

    if not ok:
        bot.send_message(user_id, f"❌ خطا در صدور اکانت تستی. لطفاً به پشتیبانی پیام دهید:\n{config.SUPPORT_BOT_USERNAME}")
        return

    user_uuid = result.get("uuid")
    sub_url = result.get("sub_url")

    db.save_test_account(user_id, user_uuid, traffic_gb=1.0, days=30)
    db.add_user_subscription(user_id, user_uuid, "🎁 اکانت تستی (۱ گیگ / ۳۰ روز)", 1.0, 30)

    success_text = (
        "🎉 <b>اکانت تستی رایگان ۱ گیگابایتی شما صادر شد!</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "📊 <b>حجم هدیه:</b> ۱ گیگابایت (1.0 GB)\n"
        "⏳ <b>مدت اعتبار:</b> ۳۰ روز کامل\n"
        "🌍 <b>سرورها:</b> سوییس و ترکیه (پرسرعت بدون قطعی)\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 <b>لینک اختصاصی سابسکریپشن:</b>\n<code>{sub_url}</code>\n\n"
        "💡 <b>راهنمای اتصال:</b>\n"
        "لینک بالا را کپی کرده و در برنامه متناسب با دستگاه خود (V2rayNG / Streisand / v2rayN / Hiddify) وارد فرمایید.\n\n"
        "⭐️ <i>در صورت رضایت از کیفیت، می‌توانید با کلیک روی «🛍 خرید اشتراک» سرویس نامحدود خود را تهیه کنید.</i>"
    )
    markup = kb.sub_details_keyboard(sub_url)
    bot.send_message(user_id, success_text, reply_markup=markup)

# ----------------- Plans & Ordering -----------------

def show_plans(user_id):
    plans = db.get_active_plans()
    text = (
        "💎 <b>لیست پلن‌های پرسرعت دلتا فورس نت</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "▫️ سرورهای اختصاصی لوکیشن اروپا (سوییس / ترکیه)\n"
        "▫️ بدون محدودیت تعداد کاربر و دستگاه\n"
        "▫️ ترافیک ۱۰۰٪ واقعی و اختصاصی بدون افت سرعت\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "یکی از پلن‌های زیر را انتخاب کنید یا از دکمه <b>«پلن دلخواه»</b> برای تعیین حجم دلخواهتان استفاده فرمایید:"
    )
    markup = kb.plans_keyboard(plans)
    bot.send_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_plan_"))
def handle_select_plan(call):
    user_id = call.from_user.id
    plan_id = int(call.data.replace("buy_plan_", ""))
    plan = db.get_plan(plan_id)
    if not plan:
        bot.answer_callback_query(call.id, "پلن یافت نشد!")
        return

    order_id = f"DF-{int(time.time())}-{user_id % 10000}"
    db.create_order(
        order_id=order_id,
        tg_id=user_id,
        plan_name=plan["name"],
        traffic_gb=plan["traffic_gb"],
        days=plan["days"],
        original_price=plan["price_toman"],
        final_price=plan["price_toman"]
    )

    send_order_invoice(user_id, order_id, call.message.message_id)
    bot.answer_callback_query(call.id)

def send_order_invoice(user_id, order_id, edit_message_id=None):
    order = db.get_order(order_id)
    if not order:
        return

    invoice_text = (
        "📑 <b>پیش‌فاکتور و خلاصه سفارش شما</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"📦 <b>پلن انتخابی:</b> {order['plan_name']}\n"
        f"📊 <b>حجم اشتراک:</b> {order['traffic_gb']} گیگابایت\n"
        f"⏳ <b>مدت زمان:</b> {order['days']} روز\n"
        f"🌍 <b>لوکیشن‌ها:</b> مولتی لوکیشن (سوییس + ترکیه)\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
    )

    if order.get("custom_name"):
        invoice_text += f"👤 <b>نام اشتراک:</b> {order['custom_name']}\n"

    if order.get("discount_code"):
        invoice_text += f"🎟 <b>کد تخفیف:</b> <code>{order['discount_code']}</code>\n"
        invoice_text += f"💵 <b>قیمت اصلی:</b> <s>{order['original_price']:,} تومان</s>\n"
        invoice_text += f"💳 <b>مبلغ قابل پرداخت:</b> <b>{order['final_price']:,} تومان</b>\n"
    else:
        invoice_text += f"💳 <b>مبلغ قابل پرداخت:</b> <b>{order['final_price']:,} تومان</b>\n"

    invoice_text += (
        "➖➖➖➖➖➖➖➖➖➖\n"
        "لطفاً روش پرداخت خود را از دکمه‌های زیر انتخاب فرمایید:"
    )

    u = db.get_user(user_id)
    wallet_balance = u["wallet_balance"] if u else 0
    markup = kb.order_checkout_keyboard(order_id, has_discount=bool(order.get("discount_code")), wallet_balance=wallet_balance, final_price=order["final_price"])

    if edit_message_id:
        try:
            bot.edit_message_text(invoice_text, user_id, edit_message_id, reply_markup=markup)
            return
        except Exception:
            pass

    bot.send_message(user_id, invoice_text, reply_markup=markup)

# ----------------- Custom Plan Flow -----------------

@bot.callback_query_handler(func=lambda call: call.data == "buy_custom_plan")
def handle_custom_plan(call):
    user_id = call.from_user.id
    min_gb = db.get_setting("min_custom_gb", "5")
    max_gb = db.get_setting("max_custom_gb", "300")
    rate_gb = int(db.get_setting("price_per_gb", "6000"))

    text = (
        "⭐️ <b>محاسبه‌گر پلن دلخواه دلتا فورس</b>\n\n"
        f"نرخ هر گیگابایت: <b>{rate_gb:,} تومان</b>\n\n"
        f"لطفاً مقدار حجم مورد نظر خود را به <b>گیگابایت</b> به صورت یک عدد انگلیسی ارسال کنید:\n"
        f"(حداقل {min_gb} گیگ و حداکثر {max_gb} گیگ)"
    )
    set_state(user_id, "WAITING_CUSTOM_GB")
    bot.edit_message_text(text, user_id, call.message.message_id)
    bot.answer_callback_query(call.id)

def process_custom_gb(message):
    user_id = message.from_user.id
    try:
        gb = float(message.text.strip())
        min_gb = float(db.get_setting("min_custom_gb", "5"))
        max_gb = float(db.get_setting("max_custom_gb", "300"))
        if gb < min_gb or gb > max_gb:
            bot.reply_to(message, f"حجم باید بین {int(min_gb)} تا {int(max_gb)} گیگ باشد. لطفاً دوباره وارد کنید:")
            return
    except ValueError:
        bot.reply_to(message, "لطفاً فقط یک عدد انگلیسی معتبر ارسال فرمایید (مثلاً: 25):")
        return

    rate_day = int(db.get_setting("price_per_day", "1000"))
    min_days = db.get_setting("min_custom_days", "10")
    max_days = db.get_setting("max_custom_days", "180")

    set_state(user_id, "WAITING_CUSTOM_DAYS", temp_data={"gb": gb})
    bot.reply_to(message, f"حجم انتخاب شده: <b>{gb} گیگابایت</b>\n\nحالا مدت اعتبار را به <b>تعداد روز</b> وارد کنید (نرخ هر روز {rate_day:,} تومان):\n(حداقل {min_days} روز و حداکثر {max_days} روز)")

def process_custom_days(message):
    user_id = message.from_user.id
    state = get_state(user_id)
    gb = state.get("temp_data", {}).get("gb", 10.0)

    try:
        days = int(message.text.strip())
        min_days = int(db.get_setting("min_custom_days", "10"))
        max_days = int(db.get_setting("max_custom_days", "180"))
        if days < min_days or days > max_days:
            bot.reply_to(message, f"تعداد روز باید بین {min_days} تا {max_days} روز باشد. لطفاً دوباره وارد کنید:")
            return
    except ValueError:
        bot.reply_to(message, "لطفاً فقط یک عدد صحیح انگلیسی ارسال کنید (مثلاً: 30):")
        return

    clear_state(user_id)

    rate_gb = int(db.get_setting("price_per_gb", "6000"))
    rate_day = int(db.get_setting("price_per_day", "1000"))
    total_price = int((gb * rate_gb) + (days * rate_day))

    order_id = f"DF-CUST-{int(time.time())}-{user_id % 10000}"
    db.create_order(
        order_id=order_id,
        tg_id=user_id,
        plan_name=f"⭐️ پلن دلخواه ({gb} گیگ / {days} روز)",
        traffic_gb=gb,
        days=days,
        original_price=total_price,
        final_price=total_price
    )

    send_order_invoice(user_id, order_id)

# ----------------- Discount & Custom Name Handlers -----------------

@bot.callback_query_handler(func=lambda call: call.data.startswith("apply_discount_"))
def handle_ask_discount(call):
    user_id = call.from_user.id
    order_id = call.data.replace("apply_discount_", "")
    set_state(user_id, "WAITING_DISCOUNT", order_id=order_id)
    bot.send_message(user_id, "🎟 لطفاً کد تخفیف خود را ارسال کنید:")
    bot.answer_callback_query(call.id)

def process_discount_code(message, order_id):
    user_id = message.from_user.id
    code = message.text.strip().upper()
    clear_state(user_id)

    order = db.get_order(order_id)
    if not order:
        bot.reply_to(message, "سفارش یافت نشد.")
        return

    ok, msg, final_price = db.check_discount(code, order["original_price"])
    if not ok:
        bot.reply_to(message, f"❌ {msg}")
        send_order_invoice(user_id, order_id)
        return

    conn = db.get_connection()
    c = conn.cursor()
    c.execute("UPDATE orders SET discount_code = ?, final_price = ? WHERE order_id = ?", (code, final_price, order_id))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"✅ {msg}")
    send_order_invoice(user_id, order_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_custom_name_"))
def handle_ask_custom_name(call):
    user_id = call.from_user.id
    order_id = call.data.replace("set_custom_name_", "")
    set_state(user_id, "WAITING_CUSTOM_NAME", order_id=order_id)
    bot.send_message(user_id, "✏️ لطفاً یک نام انگلیسی دلخواه برای اشتراک خود ارسال کنید (مثلاً: ali-iphone):")
    bot.answer_callback_query(call.id)

def process_custom_name(message, order_id):
    user_id = message.from_user.id
    name = message.text.strip()
    clear_state(user_id)

    conn = db.get_connection()
    c = conn.cursor()
    c.execute("UPDATE orders SET custom_name = ? WHERE order_id = ?", (name, order_id))
    conn.commit()
    conn.close()

    bot.reply_to(message, f"✅ نام اشتراک روی <b>{name}</b> تنظیم شد.")
    send_order_invoice(user_id, order_id)

# ----------------- Payment Flow (Card & Gateways) -----------------

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_card_"))
def handle_pay_card(call):
    user_id = call.from_user.id
    order_id = call.data.replace("pay_card_", "")
    order = db.get_order(order_id)
    if not order:
        bot.answer_callback_query(call.id, "سفارش یافت نشد!")
        return

    card_num = db.get_setting("card_number", config.DEFAULT_CARD_NUMBER)
    card_holder = db.get_setting("card_holder", config.DEFAULT_CARD_HOLDER)

    text = (
        "💳 <b>پرداخت امن کارت به کارت</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"💵 <b>مبلغ دقیق قابل واریز:</b> <code>{order['final_price']:,}</code> تومان\n\n"
        f"🔢 <b>شماره کارت:</b>\n<code>{card_num}</code>\n"
        f"👤 <b>به نام:</b> {card_holder}\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "⚠️ <b>نکات مهم:</b>\n"
        "۱. لطفاً مبلغ را دقیقاً معادل فاکتور واریز فرمایید.\n"
        "۲. پس از واریز، روی دکمه <b>«ارسال عکس فیش واریزی»</b> در زیر کلیک کرده و عکس فیش را بفرستید.\n"
        "۳. به محض تایید توسط واحد مالی، اشتراک شما به صورت خودکار صادر و تحویل داده می‌شود."
    )
    markup = kb.card_payment_keyboard(order_id)
    bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("send_receipt_"))
def handle_ask_receipt(call):
    user_id = call.from_user.id
    order_id = call.data.replace("send_receipt_", "")
    set_state(user_id, "WAITING_RECEIPT", order_id=order_id)
    bot.send_message(user_id, "📸 لطفاً <b>عکس واضح فیش واریزی</b> را همین‌جا ارسال کنید:")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_online_"))
def handle_pay_online(call):
    user_id = call.from_user.id
    order_id = call.data.replace("pay_online_", "")
    text = (
        "🌐 <b>درگاه‌های پرداخت آنلاین ریالی</b>\n\n"
        "یکی از درگاه‌های مورد نظر را انتخاب کنید:\n"
        "<i>(به زودی پس از اتصال مرچنت‌ها فعال خواهند شد)</i>"
    )
    markup = kb.gateways_keyboard(order_id)
    bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_order_"))
def handle_back_order(call):
    user_id = call.from_user.id
    order_id = call.data.replace("back_to_order_", "")
    clear_state(user_id)
    send_order_invoice(user_id, order_id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_order")
def handle_cancel_order(call):
    user_id = call.from_user.id
    clear_state(user_id)
    bot.delete_message(user_id, call.message.message_id)
    bot.send_message(user_id, "❌ سفارش لغو شد.", reply_markup=kb.main_menu(user_id))
    bot.answer_callback_query(call.id)

# ----------------- Receipt Photo Upload Handler -----------------

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    user_id = message.from_user.id
    state = get_state(user_id)

    if state.get("action") != "WAITING_RECEIPT":
        return

    order_id = state.get("order_id")
    order = db.get_order(order_id)
    if not order:
        bot.reply_to(message, "سفارش نامعتبر است.")
        clear_state(user_id)
        return

    photo_id = message.photo[-1].file_id
    clear_state(user_id)

    db.update_order_status(order_id, "pending_approval", receipt_photo_id=photo_id)

    bot.reply_to(
        message,
        "✅ <b>فیش واریزی شما با موفقیت دریافت شد!</b>\n\n"
        "اطلاعات فاکتور جهت بررسی به واحد حسابداری دلتا فورس نت ارسال گردید.\n"
        "به محض تایید، کانفیگ شما به صورت لحظه‌ای صادر و در همین چت برایتان ارسال می‌شود."
    )

    admin_caption = (
        "🔔 <b>اعلان فیش واریزی جدید!</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🆔 <b>شماره سفارش:</b> <code>{order_id}</code>\n"
        f"👤 <b>کاربر:</b> {message.from_user.first_name} (@{message.from_user.username or 'ندارد'})\n"
        f"🔢 <b>شناسه عددی:</b> <code>{user_id}</code>\n"
        f"📦 <b>پلن:</b> {order['plan_name']}\n"
        f"📊 <b>حجم:</b> {order['traffic_gb']} GB | ⏳ <b>مدت:</b> {order['days']} روز\n"
        f"💵 <b>مبلغ قابل پرداخت:</b> <b>{order['final_price']:,} تومان</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "لطفاً وضعیت را مشخص فرمایید:"
    )
    markup = kb.admin_receipt_keyboard(order_id)
    try:
        bot.send_photo(config.ADMIN_ID, photo_id, caption=admin_caption, reply_markup=markup)
    except Exception as e:
        logger.error(f"Failed to forward receipt to admin: {e}")

# ----------------- Admin Receipt Approval & Delivery -----------------

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_app_"))
def handle_admin_approve(call):
    if call.from_user.id != config.ADMIN_ID:
        return

    order_id = call.data.replace("adm_app_", "")
    order = db.get_order(order_id)
    if not order:
        bot.answer_callback_query(call.id, "سفارش یافت نشد!")
        return

    if order["status"] == "completed":
        bot.answer_callback_query(call.id, "این سفارش قبلاً تایید و صادر شده است.")
        return

    # Check if this order is a renewal
    is_renewal = str(order.get("plan_name", "")).startswith("تمدید") or (order.get("custom_name") and str(order.get("custom_name")).startswith("renew:"))
    target_uuid = order.get("hiddify_uuid")
    if not target_uuid and order.get("custom_name") and str(order.get("custom_name")).startswith("renew:"):
        target_uuid = str(order.get("custom_name")).replace("renew:", "").strip()

    if is_renewal and target_uuid:
        ok, result = hiddify.add_traffic_and_days(target_uuid, add_gb=order["traffic_gb"], add_days=order["days"])
        if not ok:
            bot.send_message(config.ADMIN_ID, f"❌ خطا در تمدید کاربر در هیدیفای:\n{result}")
            bot.answer_callback_query(call.id, "خطا در تمدید هیدیفای!")
            return
        user_uuid = target_uuid
        client_name = order.get("custom_name") or "اشتراک تمدید شده"
        sub_url = hiddify.get_sub_url(user_uuid)
    else:
        client_name = order.get("custom_name") or f"df-{order['tg_id'] % 10000}-{int(time.time()) % 1000}"
        ok, result = hiddify.create_user(
            name=client_name,
            usage_limit_gb=order["traffic_gb"],
            package_days=order["days"],
            telegram_id=order["tg_id"],
            comment=f"Order {order_id}"
        )
        if not ok:
            bot.send_message(config.ADMIN_ID, f"❌ خطا در صدور کاربر در هیدیفای:\n{result}")
            bot.answer_callback_query(call.id, "خطا در اتصال به هیدیفای!")
            return
        user_uuid = result.get("uuid")
        sub_url = result.get("sub_url")

    db.update_order_status(order_id, "completed", hiddify_uuid=user_uuid)
    db.add_user_subscription(order["tg_id"], user_uuid, client_name, order["traffic_gb"], order["days"])

    # Process 10% referral reward for the inviter
    buyer = db.get_user(order["tg_id"])
    if buyer and buyer.get("invited_by"):
        inviter_id = buyer["invited_by"]
        reward = int(order["final_price"] * 0.10)
        if reward > 0:
            db.add_wallet_balance(inviter_id, reward)
            db.record_referral_reward(inviter_id, order["tg_id"], order_id, order["final_price"], reward)
            inviter = db.get_user(inviter_id)
            new_balance = inviter["wallet_balance"] if inviter else reward
            try:
                bot.send_message(
                    inviter_id,
                    f"🎁 <b>پاداش دعوت جدید واریز شد!</b>\n"
                    f"➖➖➖➖➖➖➖➖➖➖\n"
                    f"یکی از دوستان دعوت‌شده شما اشتراک خریداری کرد و <b>۱۰٪ از مبلغ سفارش</b> به کیف پول شما اضافه شد:\n\n"
                    f"💰 <b>مبلغ پاداش:</b> <code>+{reward:,} تومان</code>\n"
                    f"💳 <b>موجودی جدید کیف پول:</b> <code>{new_balance:,} تومان</code>\n\n"
                    f"💡 <i>می‌توانید از این موجودی برای خرید اشتراک‌های پرسرعت دلتا فورس نت استفاده کنید.</i>"
                )
            except Exception as e:
                logger.warning(f"Failed to notify inviter {inviter_id}: {e}")

    bot.edit_message_caption(
        f"✅ <b>سفارش {order_id} با موفقیت تایید شد.</b>\nاشتراک با شناسه <code>{user_uuid}</code> {'تمدید' if is_renewal else 'صادر'} و برای مشتری ارسال گردید.",
        config.ADMIN_ID,
        call.message.message_id
    )
    bot.answer_callback_query(call.id, "تایید شد و سرویس تحویل گردید!")

    delivery_msg = (
        "🎉 <b>تبریک! پرداخت شما تایید و اشتراک تمدید شد</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"📦 <b>پلن:</b> {order['plan_name']}\n"
        f"📊 <b>حجم افزوده شده:</b> {order['traffic_gb']} گیگابایت\n"
        f"⏳ <b>اعتبار افزوده شده:</b> {order['days']} روز\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 <b>لینک هوشمند سابسکریپشن شما:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        "💡 <i>حجم و زمان به اشتراک قبلی شما اضافه شد و نیازی به تغییر یا تعویض کانفیگ ندارید.</i>"
    ) if is_renewal else (
        "🎉 <b>تبریک! پرداخت شما تایید و اشتراک صادر شد</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"📦 <b>پلن:</b> {order['plan_name']}\n"
        f"📊 <b>حجم:</b> {order['traffic_gb']} گیگابایت\n"
        f"⏳ <b>اعتبار:</b> {order['days']} روز\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 <b>لینک هوشمند سابسکریپشن شما:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        "💡 <b>نحوه اتصال:</b>\n"
        "کافیست لینک بالا را کپی کرده و در برنامه متناسب با سیستم‌عامل خود (V2rayNG, Streisand, v2rayN, Hiddify) در بخش Import از کلیپ‌بورد وارد نمایید."
    )
    markup = kb.sub_details_keyboard(sub_url, user_uuid=user_uuid)
    try:
        bot.send_message(order["tg_id"], delivery_msg, reply_markup=markup)
    except Exception as e:
        logger.error(f"Failed to deliver to user {order['tg_id']}: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_rej_"))
def handle_admin_reject(call):
    if call.from_user.id != config.ADMIN_ID:
        return

    order_id = call.data.replace("adm_rej_", "")
    order = db.get_order(order_id)
    if not order:
        return

    db.update_order_status(order_id, "cancelled")
    bot.edit_message_caption(
        f"❌ <b>سفارش {order_id} توسط ادمین رد شد.</b>",
        config.ADMIN_ID,
        call.message.message_id
    )
    bot.answer_callback_query(call.id, "سفارش رد شد.")

    try:
        bot.send_message(
            order["tg_id"],
            f"❌ <b>فیش ارسالی برای سفارش {order_id} مورد تایید قرار نگرفت.</b>\n"
            "در صورت وجود هرگونه مغایرت، لطفاً با پشتیبانی در ارتباط باشید:\n"
            f"{config.SUPPORT_BOT_USERNAME}"
        )
    except Exception:
        pass

# ----------------- User Secondary Menus & Subscription Management -----------------

def ask_subscription_link(user_id):
    """Prompt the user to send their subscription link or config."""
    set_state(user_id, "WAITING_SUB_QUERY")
    text = (
        "🔍 <b>استعلام وضعیت و مشخصات اشتراک</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "لطفاً <b>لینک سابسکریپشن</b>، یکی از کانفیگ‌ها یا شناسه (UUID) اشتراک خود را در پاسخ به این پیام ارسال نمایید:\n\n"
        "📌 <i>نمونه ورودی‌های قابل قبول:</i>\n"
        "• لینک سابسکریپشن: <code>https://freedom.thedragon.top/.../UUID/</code>\n"
        "• کانفیگ اختصاصی: <code>vless://UUID@...</code>\n"
        "• شناسه اختصاصی (UUID)\n\n"
        "💡 <b>امکانات استعلام:</b>\n"
        "نمایش آنلاین/آفلاین بودن با زمان دقیق، حجم مصرفی، حجم باقی‌مانده، تاریخ دقیق انقضا، نوار پیشرفت مصرف و اتصال خودکار به لیست «اشتراک‌های من»."
    )
    markup = kb.cancel_sub_query_keyboard()
    bot.send_message(user_id, text, reply_markup=markup)

def process_subscription_query(message, forced_uuid=None):
    """Process user subscription link/query, display full specs, and save to their account."""
    user_id = message.from_user.id
    raw_text = message.text.strip()
    clear_state(user_id)

    u_uuid = forced_uuid or extract_uuid_from_text(raw_text)

    # 1. Search by UUID if extracted
    if u_uuid:
        ok, udata = hiddify.get_user(u_uuid)
        if ok:
            # Automatically link to user subscriptions in database
            db.add_user_subscription(
                tg_id=user_id,
                hiddify_uuid=u_uuid,
                name=udata.get("name") or "اشتراک من",
                traffic_gb=float(udata.get("usage_limit_GB") or 0.0),
                days=int(udata.get("package_days") or 30)
            )
            text = format_subscription_report(udata)
            sub_url = udata.get("sub_url") or hiddify.get_sub_url(u_uuid)
            markup = kb.sub_details_keyboard(sub_url, user_uuid=u_uuid)
            bot.reply_to(message, text, reply_markup=markup)
            bot.send_message(user_id, "✅ <b>این اشتراک با موفقیت استعلام شد و به لیست «📥 اشتراک‌های من» شما اضافه گردید.</b>")
            return

    # 2. Search across users by username / name in Hiddify
    ok, udata = hiddify.find_user_by_name_or_uuid(raw_text)
    if ok:
        found_uuid = udata.get("uuid")
        db.add_user_subscription(
            tg_id=user_id,
            hiddify_uuid=found_uuid,
            name=udata.get("name") or "اشتراک من",
            traffic_gb=float(udata.get("usage_limit_GB") or 0.0),
            days=int(udata.get("package_days") or 30)
        )
        text = format_subscription_report(udata)
        sub_url = udata.get("sub_url") or hiddify.get_sub_url(found_uuid)
        markup = kb.sub_details_keyboard(sub_url, user_uuid=found_uuid)
        bot.reply_to(message, text, reply_markup=markup)
        bot.send_message(user_id, "✅ <b>این اشتراک با موفقیت استعلام شد و به لیست «📥 اشتراک‌های من» شما اضافه گردید.</b>")
        return

    # 3. Not found
    error_msg = (
        "❌ <b>اشتراک یافت نشد!</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "متأسفانه اشتراکی با این لینک یا مشخصات در سرور شناسایی نشد.\n\n"
        "لطفاً موارد زیر را بررسی فرمایید:\n"
        "▫️ لینک سابسکریپشن یا کانفیگ را به صورت کامل ارسال نمایید.\n"
        "▫️ اشتراک شما متعلق به سرورهای دلتا فورس باشد.\n\n"
        "در صورت بروز هرگونه سوال، می‌توانید با <b>«💬 تیکت و پشتیبانی»</b> در ارتباط باشید."
    )
    bot.reply_to(message, error_msg, reply_markup=kb.main_menu(user_id))

def show_my_subscriptions(user_id):
    """Display all user subscriptions with full real-time details."""
    subs = db.get_user_subscriptions(user_id)

    # If no subscriptions in local DB, search Hiddify for matching telegram_id
    if not subs:
        ok, all_users = hiddify.get_all_users()
        if ok and isinstance(all_users, list):
            found_users = [u for u in all_users if u.get("telegram_id") == user_id]
            for u in found_users:
                db.add_user_subscription(
                    tg_id=user_id,
                    hiddify_uuid=u["uuid"],
                    name=u.get("name") or "اشتراک دلتا فورس",
                    traffic_gb=float(u.get("usage_limit_GB") or 0.0),
                    days=int(u.get("package_days") or 30)
                )
            if found_users:
                subs = db.get_user_subscriptions(user_id)

    if not subs:
        text = (
            "📭 <b>شما در حال حاضر هیچ اشتراک ثبت‌شده‌ای ندارید.</b>\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "💡 اگر قبلاً اشتراک تهیه کرده‌اید، کافیست <b>لینک سابسکریپشن</b> خود را در چت ارسال فرمایید یا دکمه «🔍 استعلام و اتصال لینک اشتراک» را لمس کنید تا بلافاصله به حسابتان اضافه شود.\n\n"
            "🛍 جهت تهیه اشتراک پرسرعت جدید یا دریافت اکانت تستی رایگان، از گزینه‌های زیر استفاده فرمایید:"
        )
        markup = kb.empty_subs_keyboard()
        bot.send_message(user_id, text, reply_markup=markup)
        return

    bot.send_message(user_id, f"📋 <b>لیست اشتراک‌های شما ({len(subs)} مورد):</b>\nدر حال دریافت آخرین وضعیت لحظه‌ای از سرور...")

    for s in subs:
        u_uuid = s["hiddify_uuid"]
        ok, udata = hiddify.get_user(u_uuid)
        if ok:
            text = format_subscription_report(udata, sub_record=s)
            sub_url = udata.get("sub_url") or hiddify.get_sub_url(u_uuid)
            markup = kb.sub_details_keyboard(sub_url, user_uuid=u_uuid)
            bot.send_message(user_id, text, reply_markup=markup)
        else:
            text = (
                f"🛡 <b>اشتراک: {s.get('name') or 'کانفیگ من'}</b>\n"
                f"➖➖➖➖➖➖➖➖➖➖\n"
                f"❌ <b>وضعیت در سرور:</b> این اشتراک در سرور یافت نشد (احتمالاً حذف یا منقضی شده است).\n"
                f"شناسه اشتراک: <code>{u_uuid}</code>"
            )
            bot.send_message(user_id, text)

def show_wallet(user_id):
    u = db.get_user(user_id)
    balance = u["wallet_balance"] if u else 0
    invites, earned = db.get_user_referral_stats(user_id)
    text = (
        "💳 <b>کیف پول هوشمند دلتا فورس نت</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"💰 <b>موجودی فعلی شما:</b> <b>{balance:,} تومان</b>\n\n"
        f"👥 <b>تعداد دوستان دعوت‌شده:</b> <b>{invites} نفر</b>\n"
        f"🎁 <b>کل پاداش‌های دریافتی:</b> <b>{earned:,} تومان</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "💡 <b>مزیت ویژه:</b>\n"
        "با موجودی کیف پول خود می‌توانید بدون نیاز به کارت‌به‌کارت یا ارسال فیش، مستقیماً اشتراک‌های پرسرعت VPN دلتا فورس را خریداری یا تمدید فرمایید!\n\n"
        "🔗 برای کسب درآمد و افزایش موجودی، لینک اختصاصی خود را از دکمه زیر برای دوستان بفرستید (۱۰٪ از هر خرید مستقیماً به کیف پول شما واریز می‌شود)."
    )
    markup = kb.wallet_keyboard()
    bot.send_message(user_id, text, reply_markup=markup)

def show_referral(user_id):
    ref_link = f"https://t.me/DeltaForceNetbot?start=ref_{user_id}"
    invites, earned = db.get_user_referral_stats(user_id)
    u = db.get_user(user_id)
    balance = u["wallet_balance"] if u else 0

    import urllib.parse
    share_text = (
        "🛡️ اینترنت ضدفیلتر، پرسرعت و پایدار «دلتا فورس نت»\n"
        "🎁 همین الان ۱ گیگابایت اکانت تستی رایگان ۳۰ روزه هدیه بگیر:\n"
    )
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_text)}"

    caption = (
        "💎 <b>باشگاه مشتریان و سیستم کسب درآمد دلتا فورس نت</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "⚡️ <b>«با دوستانت، رایگان متصل شو»</b>\n\n"
        "با معرفی دلتا فورس نت به دوستان و آشنایان، لذت اینترنت آزاد و پرسرعت را به آن‌ها هدیه دهید و پاداش دائمی بگیرید:\n\n"
        "🎁 <b>۱۰٪ از مبلغ هر خرید یا تمدید آن‌ها</b> به صورت آنی و خودکار به کیف پول شما واریز می‌شود!\n"
        "💰 با موجودی کیف پول خود می‌توانید سرویس‌هایتان را <b>کاملاً رایگان</b> تمدید یا خریداری فرمایید.\n\n"
        "📊 <b>کارنامه و آمار تیم شما:</b>\n"
        f"▫️ دوستان دعوت‌شده: <b>{invites:,} نفر</b>\n"
        f"▫️ مجموع پاداش کسب‌شده: <b>{earned:,} تومان</b>\n"
        f"▫️ موجودی قابل استفاده کیف پول: <b>{balance:,} تومان</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "🔗 <b>لینک اختصاصی دعوت شما:</b>\n"
        f"<code>{ref_link}</code>"
    )

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🚀 ارسال لینک دعوت برای دوستان", url=share_url),
        types.InlineKeyboardButton("💳 مشاهده موجودی کیف پول", callback_data="open_wallet_section")
    )

    banner_path = "/opt/deltaforce-shop/referral_banner.jpg"
    if os.path.exists(banner_path):
        try:
            with open(banner_path, "rb") as photo:
                bot.send_photo(user_id, photo, caption=caption, reply_markup=markup)
            return
        except Exception as e:
            logger.error(f"Error sending referral photo: {e}")

    bot.send_message(user_id, caption, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "open_referral_section")
def cb_open_referral_section(call):
    show_referral(call.from_user.id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "open_wallet_section")
def cb_open_wallet_section(call):
    show_wallet(call.from_user.id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "buy_from_wallet")
def cb_buy_from_wallet(call):
    plans = db.get_active_plans()
    markup = kb.plans_keyboard(plans)
    text = (
        "🛍 <b>خرید اشتراک با استفاده از موجودی کیف پول</b>\n\n"
        "لطفاً یکی از پلن‌های زیر را انتخاب فرمایید (در مرحله بعد گزینه پرداخت از کیف پول را انتخاب کنید):"
    )
    bot.send_message(call.from_user.id, text, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_wallet_"))
def handle_pay_wallet(call):
    user_id = call.from_user.id
    order_id = call.data.replace("pay_wallet_", "")
    order = db.get_order(order_id)
    if not order:
        bot.answer_callback_query(call.id, "سفارش یافت نشد!")
        return

    if order["status"] == "completed":
        bot.answer_callback_query(call.id, "این سفارش قبلاً پرداخت شده است.")
        return

    final_price = order["final_price"]
    success = db.deduct_wallet_balance(user_id, final_price)
    if not success:
        bot.answer_callback_query(call.id, "موجودی کیف پول شما برای این سفارش کافی نیست!", show_alert=True)
        return

    # Check if renewal
    is_renewal = str(order.get("plan_name", "")).startswith("تمدید") or (order.get("custom_name") and str(order.get("custom_name")).startswith("renew:"))
    target_uuid = order.get("hiddify_uuid")
    if not target_uuid and order.get("custom_name") and str(order.get("custom_name")).startswith("renew:"):
        target_uuid = str(order.get("custom_name")).replace("renew:", "").strip()

    if is_renewal and target_uuid:
        ok, result = hiddify.add_traffic_and_days(target_uuid, add_gb=order["traffic_gb"], add_days=order["days"])
        if not ok:
            db.add_wallet_balance(user_id, final_price)
            bot.answer_callback_query(call.id, "خطا در اتصال به سرور! مبلغ به کیف پول عودت داده شد.", show_alert=True)
            return
        user_uuid = target_uuid
        client_name = order.get("custom_name") or "اشتراک تمدید شده"
        sub_url = hiddify.get_sub_url(user_uuid)
    else:
        client_name = order.get("custom_name") or f"df-{order['tg_id'] % 10000}-{int(time.time()) % 1000}"
        ok, result = hiddify.create_user(
            name=client_name,
            usage_limit_gb=order["traffic_gb"],
            package_days=order["days"],
            telegram_id=order["tg_id"],
            comment=f"Order {order_id} (Wallet Paid)"
        )

        if not ok:
            db.add_wallet_balance(user_id, final_price)
            bot.answer_callback_query(call.id, "خطا در اتصال به سرور! مبلغ به کیف پول عودت داده شد.", show_alert=True)
            return

        user_uuid = result.get("uuid")
        sub_url = result.get("sub_url")

    db.update_order_status(order_id, "completed", hiddify_uuid=user_uuid)
    db.add_user_subscription(order["tg_id"], user_uuid, client_name, order["traffic_gb"], order["days"])

    # Process 10% referral reward for the inviter
    buyer = db.get_user(user_id)
    if buyer and buyer.get("invited_by"):
        inviter_id = buyer["invited_by"]
        reward = int(final_price * 0.10)
        if reward > 0:
            db.add_wallet_balance(inviter_id, reward)
            db.record_referral_reward(inviter_id, user_id, order_id, final_price, reward)
            inviter = db.get_user(inviter_id)
            new_balance = inviter["wallet_balance"] if inviter else reward
            try:
                bot.send_message(
                    inviter_id,
                    f"🎁 <b>پاداش دعوت جدید واریز شد!</b>\n"
                    f"➖➖➖➖➖➖➖➖➖➖\n"
                    f"یکی از دوستان دعوت‌شده شما اشتراک خریداری کرد و <b>۱۰٪ از مبلغ سفارش</b> به کیف پول شما اضافه شد:\n\n"
                    f"💰 <b>مبلغ پاداش:</b> <code>+{reward:,} تومان</code>\n"
                    f"💳 <b>موجودی جدید کیف پول:</b> <code>{new_balance:,} تومان</code>\n\n"
                    f"💡 <i>می‌توانید از این موجودی برای خرید اشتراک‌های پرسرعت دلتا فورس نت استفاده کنید.</i>"
                )
            except Exception as e:
                logger.warning(f"Failed to notify inviter {inviter_id}: {e}")

    bot.answer_callback_query(call.id, "✅ پرداخت با موفقیت انجام شد!")

    delivery_msg = (
        "🎉 <b>تبریک! پرداخت با موفقیت انجام و اشتراک تمدید شد</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"📦 <b>پلن:</b> {order['plan_name']}\n"
        f"📊 <b>حجم افزوده شده:</b> {order['traffic_gb']} گیگابایت\n"
        f"⏳ <b>اعتبار افزوده شده:</b> {order['days']} روز\n"
        f"💰 <b>مبلغ پرداختی:</b> {final_price:,} تومان (کسر از کیف پول)\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 <b>لینک هوشمند سابسکریپشن شما:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        "💡 <i>حجم و زمان به اشتراک قبلی شما افزوده شد و نیازی به تغییر کانفیگ ندارید.</i>"
    ) if is_renewal else (
        "🎉 <b>تبریک! پرداخت از کیف پول با موفقیت انجام و اشتراک صادر شد</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"📦 <b>پلن:</b> {order['plan_name']}\n"
        f"📊 <b>حجم:</b> {order['traffic_gb']} گیگابایت\n"
        f"⏳ <b>اعتبار:</b> {order['days']} روز\n"
        f"💰 <b>مبلغ پرداختی:</b> {final_price:,} تومان (کسر از کیف پول)\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 <b>لینک هوشمند سابسکریپشن شما:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        "💡 <b>نحوه اتصال:</b>\n"
        "کافیست لینک بالا را کپی کرده و در برنامه متناسب با سیستم‌عامل خود (Hiddify, Streisand, V2rayNG, v2rayN) وارد نمایید."
    )
    markup = kb.sub_details_keyboard(sub_url, user_uuid=user_uuid)
    try:
        bot.edit_message_text(delivery_msg, user_id, call.message.message_id, reply_markup=markup)
    except Exception:
        bot.send_message(user_id, delivery_msg, reply_markup=markup)

    try:
        bot.send_message(
            config.ADMIN_ID,
            f"⚡️ <b>سفارش جدید پرداخت‌شده با کیف پول</b>\n"
            f"👤 خریدار: {call.from_user.first_name} (<code>{user_id}</code>)\n"
            f"📦 پلن: {order['plan_name']}\n"
            f"💰 مبلغ: {final_price:,} تومان\n"
            f"🆔 سفارش: <code>{order_id}</code>\n"
            f"🔑 شناسه کاربر: <code>{user_uuid}</code>"
        )
    except Exception as e:
        logger.warning(f"Failed to notify admin: {e}")

def show_proxy(user_id):
    text = (
        "⚡️ <b>پروکسی‌های رایگان تلگرام</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "⚠️ <b>در حال حاضر این بخش غیرفعال می‌باشد.</b>\n\n"
        "برای اتصال فوق‌سریع و بدون قطعی، می‌توانید از بخش <b>«🛍 خرید اشتراک»</b> سرویس اختصاصی و پرسرعت تهیه فرمایید یا در کانال ما عضو شوید:\n"
        f"👉 {config.CHANNEL_USERNAME}"
    )
    bot.send_message(user_id, text)

def show_tutorials(user_id):
    text = (
        "📱 <b>راهنمای اتصال و دانلود برنامه‌ها</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "برای اتصال به اشتراک خود، نرم‌افزار مربوط به دستگاه خود را نصب فرمایید:\n\n"
        "🤖 <b>اندروید (Android):</b>\n"
        "▫️ v2rayNG / Hiddify App\n"
        "🍏 <b>آیفون و آیپد (iOS):</b>\n"
        "▫️ Streisand / V2Box / FoXray\n"
        "💻 <b>ویندوز (Windows):</b>\n"
        "▫️ v2rayN / Hiddify Next\n\n"
        f"آموزش‌های ویدیویی گام‌به‌گام در کانال قرار داده شده‌اند:\n{config.CHANNEL_URL}"
    )
    bot.send_message(user_id, text)

def show_support(user_id):
    text = (
        "💬 <b>واحد پشتیبانی ۲۴ ساعته دلتا فورس نت</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "کارشناسان ما به صورت شبانه‌روزی آماده پاسخگویی، رفع مشکلات اتصال و مشاوره به شما هستند.\n\n"
        f"جهت ارتباط با پشتیبانی، وارد ربات زیر شوید و پیام خود را بفرستید:\n"
        f"👉 <b>{config.SUPPORT_BOT_USERNAME}</b>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💬 ورود به ربات پشتیبان", url=config.SUPPORT_BOT_URL))
    bot.send_message(user_id, text, reply_markup=markup)

def show_channel(user_id):
    text = (
        "📢 <b>کانال رسمی اخبار و سرورهای دلتا فورس نت</b>\n\n"
        "جهت اطلاع از آخرین وضعیت سرورها، کدهای تخفیف مناسبتی و کانفیگ‌های رایگان در کانال ما عضو شوید:\n"
        f"👉 <b>{config.CHANNEL_USERNAME}</b>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 عضویت در کانال", url=config.CHANNEL_URL))
    bot.send_message(user_id, text, reply_markup=markup)

def show_rules(user_id):
    text = (
        "📜 <b>قوانین و راهنمای سرویس‌های دلتا فورس نت</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "۱. تمام سرویس‌ها با تضمین اتصال و پایداری در طول دوره اعتبار ارائه می‌شوند.\n"
        "۲. در صورت بروز هرگونه اختلال زیرساختی در اینترنت کشور، لوکیشن‌ها و کانفیگ‌های جایگزین به صورت رایگان آپدیت می‌گردند.\n"
        "۳. استفاده از سرویس‌ها برای مقاصد فیشینگ، اسپم و نفوذ ممنوع می‌باشد."
    )
    bot.send_message(user_id, text)

# ----------------- Reseller Engine & Partner Panel -----------------

def handle_reseller_entry(user_id):
    """Handle entry to the Reseller/Partner section."""
    reseller = db.get_reseller_by_tg(user_id)
    if reseller:
        if not reseller["is_active"]:
            bot.send_message(user_id, "⛔️ حساب نمایندگی شما توسط مدیریت غیرفعال شده است.", reply_markup=kb.main_menu(user_id))
            return
        # Check expiry
        today = datetime.now().date()
        try:
            exp_date = datetime.strptime(reseller["expire_date"], "%Y-%m-%d").date()
            if exp_date < today:
                bot.send_message(user_id, f"⚠️ حساب نمایندگی شما در تاریخ <b>{reseller['expire_date']}</b> منقضی شده است.\nجهت تمدید سهمیه با مدیریت تماس حاصل فرمایید.", reply_markup=kb.main_menu(user_id))
                return
        except Exception:
            pass
        show_reseller_dashboard(user_id, reseller)
    else:
        set_state(user_id, "WAITING_RESELLER_LOGIN")
        send_sticker(user_id, "BUSINESS")
        text = (
            "💼 <b>ورود به پنل اختصاصی فروشندگان و همکاران</b>\n"
            "➖➖➖➖➖➖➖➖➖➖\n"
            "جهت دسترسی به داشبورد و صدور مستقیم اشتراک برای مشتریان، لطفاً <b>نام کاربری و رمز عبور</b> خود را با یک فاصله ارسال نمایید:\n\n"
            "📌 <b>فرمت ارسال:</b>\n"
            "<code>[نام_کاربری] [رمز_عبور]</code>\n\n"
            "مثال:\n"
            "<code>reza_vpn secret123</code>\n\n"
            "💡 <i>در صورت تمایل به همکاری و دریافت پنل فروش، با مدیریت در ارتباط باشید.</i>"
        )
        bot.send_message(user_id, text, reply_markup=kb.reseller_cancel_keyboard())

def process_reseller_login(message):
    """Verify reseller credentials and bind their Telegram ID."""
    user_id = message.from_user.id
    clear_state(user_id)
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ لطفاً نام کاربری و رمز عبور را با یک فاصله بفرستید.\nمثال: <code>reza_vpn secret123</code>", reply_markup=kb.main_menu(user_id))
        return

    username = parts[0]
    password = parts[1]
    ok, res = db.authenticate_reseller(username, password, tg_id=user_id)
    if not ok:
        bot.reply_to(message, f"❌ <b>خطا در ورود:</b>\n{res}", reply_markup=kb.main_menu(user_id))
        return

    send_sticker(user_id, "COOL")
    bot.reply_to(message, f"🎉 <b>خوش آمدید همکار گرامی ({res['name']})!</b>\nاکانت تلگرام شما با موفقیت به پنل نمایندگی متصل شد.")
    show_reseller_dashboard(user_id, res)

def show_reseller_dashboard(user_id, reseller=None):
    """Display reseller dashboard with full volume statistics."""
    if not reseller:
        reseller = db.get_reseller_by_tg(user_id)
    if not reseller:
        handle_reseller_entry(user_id)
        return

    stats = db.get_reseller_stats(reseller["id"])
    total_gb = stats["total_gb"]
    used_gb = stats["used_gb"]
    remaining_gb = stats["remaining_gb"]
    users_count = stats["users_count"]
    expire_date = stats["expire_date"]

    month_names = ['', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
    days_left_txt = "—"
    shamsi_exp = "—"
    try:
        exp_dt = datetime.strptime(expire_date, "%Y-%m-%d").date()
        today = datetime.now().date()
        days_left = (exp_dt - today).days
        jy, jm, jd = gregorian_to_jalali(exp_dt.year, exp_dt.month, exp_dt.day)
        shamsi_exp = f"{jd} {month_names[jm]} {jy}"
        days_left_txt = f"{days_left} روز دیگر" if days_left > 0 else "منقضی شده"
    except Exception:
        pass

    percent_used = (used_gb / total_gb * 100.0) if total_gb > 0 else 0.0
    bar_len = 10
    filled = min(max(int(round((percent_used / 100.0) * bar_len)), 0), bar_len)
    p_bar = "▰" * filled + "▱" * (bar_len - filled)

    text = (
        f"💼 <b>پنل مدیریت همکاران | {reseller['name']}</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 <b>نام کاربری:</b> <code>{reseller['username']}</code>\n"
        f"🟢 <b>وضعیت حساب:</b> فعال و مجاز به صدور\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"📊 <b>سقف سهمیه کل:</b> <code>{total_gb:.2f} گیگابایت</code>\n"
        f"📥 <b>حجم صادر شده:</b> <code>{used_gb:.2f} گیگابایت</code> ({percent_used:.1f}%)\n"
        f"📤 <b>حجم باقی‌مانده:</b> <code>{remaining_gb:.2f} گیگابایت</code>\n"
        f"📈 <b>پیشرفت سهمیه:</b> <code>[{p_bar}] {percent_used:.1f}%</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"👥 <b>تعداد مشتریان صادر شده:</b> <b>{users_count} نفر</b>\n"
        f"⏳ <b>اعتبار نمایندگی تا:</b> {shamsi_exp} ({expire_date})\n"
        f"⏱ <b>فرصت باقی‌مانده:</b> <b>{days_left_txt}</b>\n\n"
        f"👇 <i>از گزینه‌های زیر جهت صدور آنی اکانت یا مشاهده مشتریان استفاده فرمایید:</i>"
    )
    bot.send_message(user_id, text, reply_markup=kb.reseller_main_menu())

def handle_reseller_new_user(user_id):
    """Start flow to issue a new client account for reseller."""
    reseller = db.get_reseller_by_tg(user_id)
    if not reseller:
        handle_reseller_entry(user_id)
        return

    stats = db.get_reseller_stats(reseller["id"])
    if stats["remaining_gb"] < 1.0:
        bot.send_message(user_id, "⚠️ <b>سهمیه حجم شما به پایان رسیده است!</b>\nجهت شارژ سهمیه مجدد با مدیریت فروشگاه در ارتباط باشید.", reply_markup=kb.reseller_main_menu())
        return

    set_state(user_id, "RESELLER_CLIENT_NAME", temp_data={"reseller_id": reseller["id"]})
    text = (
        "➕ <b>صدور اکانت جدید برای مشتری (گام ۱ از ۳)</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"📊 موجودی قابل صدور شما: <b>{stats['remaining_gb']} گیگابایت</b>\n\n"
        "لطفاً یک <b>نام دلخواه برای مشتری</b> ارسال فرمایید (حروف انگلیسی یا فارسی):\n"
        "مثال: <code>ali-phone</code> یا <code>مشتری ۱</code>"
    )
    bot.send_message(user_id, text, reply_markup=kb.reseller_cancel_keyboard())

def process_reseller_client_name(message):
    user_id = message.from_user.id
    client_name = message.text.strip().replace(" ", "-")
    state = get_state(user_id)
    temp = state.get("temp_data", {})
    temp["client_name"] = client_name
    set_state(user_id, "RESELLER_CLIENT_GB", temp_data=temp)

    reseller = db.get_reseller_by_id(temp["reseller_id"])
    stats = db.get_reseller_stats(reseller["id"])

    text = (
        f"👤 نام مشتری: <b>{client_name}</b>\n\n"
        "📊 <b>گام ۲ از ۳:</b>\n"
        f"لطفاً مقدار <b>حجم مجاز (به گیگابایت)</b> را به صورت یک عدد انگلیسی بفرستید:\n"
        f"(حداکثر سهمیه باقی‌مانده شما: <b>{stats['remaining_gb']} GB</b>)"
    )
    bot.send_message(user_id, text, reply_markup=kb.reseller_cancel_keyboard())

def process_reseller_client_gb(message):
    user_id = message.from_user.id
    raw = message.text.strip()
    try:
        gb = float(raw)
        if gb <= 0:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "❌ لطفاً مقدار حجم را به صورت یک عدد معتبر ارسال کنید (مثلاً: <code>20</code> یا <code>15.5</code>).")
        return

    state = get_state(user_id)
    temp = state.get("temp_data", {})
    reseller = db.get_reseller_by_id(temp["reseller_id"])
    stats = db.get_reseller_stats(reseller["id"])

    if gb > stats["remaining_gb"]:
        bot.reply_to(message, f"❌ حجم درخواستی ({gb} GB) بیشتر از سهمیه باقی‌مانده شما ({stats['remaining_gb']} GB) است!\nلطفاً عددی کمتر ارسال کنید.")
        return

    temp["traffic_gb"] = gb
    set_state(user_id, "RESELLER_CLIENT_DAYS", temp_data=temp)

    text = (
        f"👤 مشتری: <b>{temp['client_name']}</b> | حجم: <b>{gb} گیگ</b>\n\n"
        "⏳ <b>گام ۳ از ۳:</b>\n"
        "لطفاً <b>تعداد روزهای اعتبار</b> را به صورت عدد انگلیسی بفرستید (مثلاً: <code>30</code>):"
    )
    bot.send_message(user_id, text, reply_markup=kb.reseller_cancel_keyboard())

def process_reseller_client_days(message):
    user_id = message.from_user.id
    raw = message.text.strip()
    try:
        days = int(raw)
        if days <= 0:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "❌ لطفاً تعداد روزها را به صورت یک عدد معتبر ارسال کنید (مثلاً: <code>30</code>).")
        return

    state = get_state(user_id)
    temp = state.get("temp_data", {})
    clear_state(user_id)

    reseller = db.get_reseller_by_id(temp["reseller_id"])
    client_name = temp["client_name"]
    gb = temp["traffic_gb"]

    stats = db.get_reseller_stats(reseller["id"])
    if gb > stats["remaining_gb"]:
        bot.send_message(user_id, "❌ خطای عدم موجودی سهمیه کافی!", reply_markup=kb.reseller_main_menu())
        return

    bot.send_message(user_id, "⏳ در حال ساخت و ثبت آنی کاربر در پنل هیدیفای...")

    hiddify_name = f"{reseller['username'][:6]}-{client_name}"
    hiddify_comment = f"[Reseller: {reseller['name']} (@{reseller['username']})] - Client: {client_name}"

    ok, result = hiddify.create_user(
        name=hiddify_name,
        usage_limit_gb=gb,
        package_days=days,
        telegram_id=None,
        comment=hiddify_comment
    )

    if not ok:
        bot.send_message(user_id, f"❌ خطا در صدور کاربر در هیدیفای:\n{result}", reply_markup=kb.reseller_main_menu())
        return

    user_uuid = result.get("uuid")
    sub_url = result.get("sub_url")

    # Deduct credit & record
    db.deduct_reseller_credit(reseller["id"], gb)
    db.add_reseller_user(reseller["id"], user_uuid, client_name, gb, days)

    send_sticker(user_id, "SUCCESS")

    forward_card = (
        "🎉 <b>اشتراک پرسرعت دلتا فورس نت صادر شد</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 <b>نام کاربر:</b> {client_name}\n"
        f"📊 <b>حجم مجاز:</b> {gb} گیگابایت\n"
        f"⏳ <b>مدت زمان:</b> {days} روز\n"
        f"🌍 <b>سرورها:</b> لوکیشن اروپا (سوییس و ترکیه - فوق‌العاده پایدار)\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 <b>لینک هوشمند سابسکریپشن:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        "💡 <b>نحوه اتصال:</b>\n"
        "لینک بالا را کپی نموده و در برنامه‌های متناسب با دستگاه خود (V2rayNG / Streisand / v2rayN / Hiddify) در بخش Add Subscription یا Import from clipboard وارد فرمایید."
    )

    sub_markup = kb.sub_details_keyboard(sub_url, user_uuid=user_uuid)

    bot.send_message(
        user_id,
        "✅ <b>اکانت مشتری با موفقیت صادر شد!</b>\n"
        f"از سهمیه شما مقدار <b>{gb} GB</b> کسر گردید.\n\n"
        "👇 <i>پیام زیر را مستقیماً برای مشتری خود فوروارد نمایید:</i>",
        reply_markup=kb.reseller_main_menu()
    )
    bot.send_message(user_id, forward_card, reply_markup=sub_markup)

def handle_reseller_users_list(user_id):
    """Show list of all clients issued by this reseller."""
    reseller = db.get_reseller_by_tg(user_id)
    if not reseller:
        handle_reseller_entry(user_id)
        return

    users = db.get_reseller_users(reseller["id"])
    if not users:
        bot.send_message(user_id, "📭 شما تاکنون هیچ اکانتی برای مشتریان صادر نکرده‌اید.", reply_markup=kb.reseller_main_menu())
        return

    bot.send_message(user_id, f"👥 <b>لیست مشتریان صادر شده توسط شما ({len(users)} نفر):</b>\nدر حال دریافت وضعیت از سرور...")

    for u in users[:15]:
        ok, udata = hiddify.get_user(u["hiddify_uuid"])
        if ok:
            text = format_subscription_report(udata)
            sub_url = udata.get("sub_url") or hiddify.get_sub_url(u["hiddify_uuid"])
            markup = kb.sub_details_keyboard(sub_url, user_uuid=u["hiddify_uuid"])
            bot.send_message(user_id, text, reply_markup=markup)
        else:
            text = f"👤 <b>مشتری: {u['client_name']}</b>\nشناسه: <code>{u['hiddify_uuid']}</code>\nوضعیت: در سرور یافت نشد."
            bot.send_message(user_id, text)

def handle_reseller_stats(user_id):
    """Show reseller statistics."""
    show_reseller_dashboard(user_id)

def handle_reseller_renew_prompt(user_id):
    """Prompt reseller to select which client to extend."""
    reseller = db.get_reseller_by_tg(user_id)
    if not reseller:
        handle_reseller_entry(user_id)
        return

    users = db.get_reseller_users(reseller["id"])
    if not users:
        bot.send_message(user_id, "📭 شما هنوز کاربری برای تمدید ندارید.", reply_markup=kb.reseller_main_menu())
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for u in users[:12]:
        markup.add(types.InlineKeyboardButton(f"👤 {u['client_name']} ({u['traffic_gb']} GB)", callback_data=f"res_rnw_{u['hiddify_uuid']}"))
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="reseller_cancel"))

    bot.send_message(user_id, "🔄 <b>لطفاً مشتری مورد نظر جهت تمدید یا افزایش حجم را انتخاب فرمایید:</b>", reply_markup=markup)

def handle_reseller_logout(user_id):
    """Logout reseller from current telegram session."""
    reseller = db.get_reseller_by_tg(user_id)
    if reseller:
        db.unbind_reseller_tg(reseller["id"])
    bot.send_message(user_id, "🚪 شما با موفقیت از پنل نمایندگی خارج شدید.", reply_markup=kb.main_menu(user_id))

def show_user_main_menu(user_id):
    """Return to user main menu."""
    clear_state(user_id)
    bot.send_message(user_id, "منوی اصلی:", reply_markup=kb.main_menu(user_id))

# ----------------- Admin Reseller Management Handlers -----------------

@bot.callback_query_handler(func=lambda call: call.data == "adm_resellers")
def handle_adm_resellers(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    resellers = db.get_all_resellers()
    total_res = len(resellers)
    total_credit = sum(r["total_credit_gb"] for r in resellers)
    total_used = sum(r["used_credit_gb"] for r in resellers)
    active_count = sum(1 for r in resellers if r["is_active"])

    text = (
        "💼 <b>سیستم مدیریت فروشندگان و همکاران (Resellers)</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"👥 <b>کل نمایندگان تعریف شده:</b> <b>{total_res} نفر</b> (🟢 {active_count} فعال)\n"
        f"📊 <b>مجموع سهمیه تخصیص یافته:</b> <b>{total_credit:.1f} گیگابایت</b>\n"
        f"📥 <b>مجموع حجم صادر شده:</b> <b>{total_used:.1f} گیگابایت</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "عملیات مورد نظر را انتخاب فرمایید:"
    )
    markup = kb.admin_resellers_menu_keyboard()
    bot.edit_message_text(text, call.from_user.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "adm_list_resellers")
def handle_adm_list_resellers(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    resellers = db.get_all_resellers()
    if not resellers:
        bot.answer_callback_query(call.id, "هیچ فروشنده‌ای ثبت نشده است.")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ افزودن اولین فروشنده", callback_data="adm_add_reseller"))
        markup.add(types.InlineKeyboardButton("‹ بازگشت به مدیریت", callback_data="open_admin_panel"))
        bot.edit_message_text("📭 در حال حاضر هیچ فروشنده‌ای در سیستم تعریف نشده است.", call.from_user.id, call.message.message_id, reply_markup=markup)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for r in resellers:
        status_dot = "🟢" if r["is_active"] else "🔴"
        rem_gb = max(0.0, r["total_credit_gb"] - r["used_credit_gb"])
        btn_text = f"{status_dot} {r['name']} (@{r['username']}) | باقی: {rem_gb:.0f} GB"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"adm_res_view_{r['id']}"))

    markup.add(types.InlineKeyboardButton("➕ افزودن فروشنده جدید", callback_data="adm_add_reseller"))
    markup.add(types.InlineKeyboardButton("‹ بازگشت به بخش فروشندگان", callback_data="adm_resellers"))

    bot.edit_message_text("📋 <b>لیست نمایندگان و همکاران:</b>\nجهت مشاهده جزئیات یا شارژ سهمیه، روی نام فروشنده کلیک کنید:", call.from_user.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_res_view_"))
def handle_adm_res_view(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    res_id = int(call.data.replace("adm_res_view_", ""))
    r = db.get_reseller_by_id(res_id)
    if not r:
        bot.answer_callback_query(call.id, "فروشنده یافت نشد!")
        return

    stats = db.get_reseller_stats(res_id)
    month_names = ['', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
    shamsi_exp = "—"
    try:
        exp_dt = datetime.strptime(r["expire_date"], "%Y-%m-%d").date()
        jy, jm, jd = gregorian_to_jalali(exp_dt.year, exp_dt.month, exp_dt.day)
        shamsi_exp = f"{jd} {month_names[jm]} {jy}"
    except Exception:
        pass

    tg_status = f"متصل به آیدی <code>{r['tg_id']}</code>" if r["tg_id"] else "هنوز در بات لاگین نکرده"
    status_text = "🟢 فعال" if r["is_active"] else "🔴 مسدود"

    text = (
        f"👤 <b>اطلاعات نماینده: {r['name']}</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"🔑 <b>نام کاربری:</b> <code>{r['username']}</code>\n"
        f"🔒 <b>رمز عبور:</b> <code>{r['password']}</code>\n"
        f"📱 <b>وضعیت تلگرام:</b> {tg_status}\n"
        f"📌 <b>وضعیت حساب:</b> {status_text}\n"
        f"➖➖➖➖➖➖➖➖➖➖\n"
        f"📊 <b>کل سهمیه اختصاصی:</b> <code>{r['total_credit_gb']} گیگابایت</code>\n"
        f"📥 <b>حجم صادر شده:</b> <code>{stats['used_gb']} گیگابایت</code>\n"
        f"📤 <b>سهمیه باقی‌مانده:</b> <code>{stats['remaining_gb']} گیگابایت</code>\n"
        f"👥 <b>تعداد مشتریان صادر شده:</b> <b>{stats['users_count']} نفر</b>\n"
        f"⏳ <b>تاریخ انقضای قرارداد:</b> {shamsi_exp} ({r['expire_date']})"
    )
    markup = kb.admin_reseller_detail_keyboard(res_id, r["is_active"])
    bot.edit_message_text(text, call.from_user.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "adm_add_reseller")
def handle_adm_add_reseller(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    set_state(config.ADMIN_ID, "ADMIN_ADD_RES_NAME")
    text = (
        "➕ <b>افزودن فروشنده و همکار جدید (گام ۱ از ۴)</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "لطفاً <b>نام یا عنوان نمایشی همکار</b> را ارسال فرمایید:\n"
        "مثال: <code>رضا - کانال گیمینگ</code>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="adm_resellers"))
    bot.edit_message_text(text, call.from_user.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

def process_admin_res_name(message):
    name = message.text.strip()
    set_state(config.ADMIN_ID, "ADMIN_ADD_RES_CRED", temp_data={"name": name})
    text = (
        f"👤 نام: <b>{name}</b>\n\n"
        "🔑 <b>گام ۲ از ۴:</b>\n"
        "لطفاً <b>نام کاربری و رمز عبور</b> را با یک فاصله بفرستید (نام کاربری انگلیسی باشد):\n"
        "مثال:\n"
        "<code>reza_vpn pass1234</code>"
    )
    bot.reply_to(message, text)

def process_admin_res_cred(message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ فرمت نادرست است. مثال: <code>reza_vpn pass1234</code>")
        return

    state = get_state(config.ADMIN_ID)
    temp = state.get("temp_data", {})
    temp["username"] = parts[0].lower()
    temp["password"] = parts[1]
    set_state(config.ADMIN_ID, "ADMIN_ADD_RES_GB", temp_data=temp)

    text = (
        f"🔑 یوزرنیم: <code>{temp['username']}</code> | پسورد: <code>{temp['password']}</code>\n\n"
        "📊 <b>گام ۳ از ۴:</b>\n"
        "لطفاً <b>سقف ترافیک اختصاصی (به گیگابایت)</b> را به صورت یک عدد ارسال فرمایید:\n"
        "مثال: <code>500</code>"
    )
    bot.reply_to(message, text)

def process_admin_res_gb(message):
    raw = message.text.strip()
    try:
        gb = float(raw)
        if gb <= 0:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "❌ لطفاً مقدار حجم را به صورت یک عدد معتبر ارسال کنید (مثلاً: <code>500</code>).")
        return

    state = get_state(config.ADMIN_ID)
    temp = state.get("temp_data", {})
    temp["total_credit_gb"] = gb
    set_state(config.ADMIN_ID, "ADMIN_ADD_RES_DAYS", temp_data=temp)

    text = (
        f"📊 سهمیه حجم: <b>{gb} GB</b>\n\n"
        "⏳ <b>گام ۴ از ۴:</b>\n"
        "لطفاً <b>مدت زمان اعتبار قرارداد (به روز)</b> را ارسال فرمایید (مثلاً: <code>30</code> یا <code>60</code>):"
    )
    bot.reply_to(message, text)

def process_admin_res_days(message):
    raw = message.text.strip()
    try:
        days = int(raw)
        if days <= 0:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "❌ لطفاً تعداد روزها را به صورت عدد معتبر ارسال فرمایید (مثلاً: <code>30</code>).")
        return

    state = get_state(config.ADMIN_ID)
    temp = state.get("temp_data", {})
    clear_state(config.ADMIN_ID)

    name = temp["name"]
    username = temp["username"]
    password = temp["password"]
    gb = temp["total_credit_gb"]

    today = datetime.now().date()
    exp_dt = today + timedelta(days=days)
    expire_date = exp_dt.strftime("%Y-%m-%d")

    ok, res_id = db.create_reseller(name, username, password, gb, expire_date)
    if not ok:
        bot.reply_to(message, f"❌ خطا در ایجاد فروشنده: {res_id}")
        return

    month_names = ['', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
    jy, jm, jd = gregorian_to_jalali(exp_dt.year, exp_dt.month, exp_dt.day)
    shamsi_exp = f"{jd} {month_names[jm]} {jy}"

    send_sticker(config.ADMIN_ID, "BUSINESS")

    summary_text = (
        "🎉 <b>فروشنده و همکار جدید با موفقیت ایجاد شد!</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"👤 <b>نام همکار:</b> {name}\n"
        f"🔑 <b>نام کاربری:</b> <code>{username}</code>\n"
        f"🔒 <b>رمز عبور:</b> <code>{password}</code>\n"
        f"📊 <b>سقف سهمیه اولیه:</b> <code>{gb} گیگابایت</code>\n"
        f"⏳ <b>مدت اعتبار:</b> <code>{days} روز</code> (تا {shamsi_exp} - {expire_date})\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "💡 <b>راهنمای فروشنده:</b>\n"
        "فروشنده می‌تواند با زدن دکمه <b>«💼 پنل فروشندگان و همکاران»</b> در ربات و وارد کردن مشخصات بالا، به صورت مستقل برای مشتریان خود اکانت صادر کند."
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📋 مشاهده در لیست فروشندگان", callback_data=f"adm_res_view_{res_id}"))
    markup.add(types.InlineKeyboardButton("‹ بازگشت به مدیریت", callback_data="open_admin_panel"))
    bot.send_message(config.ADMIN_ID, summary_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_chg_res_"))
def handle_adm_chg_res(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    res_id = int(call.data.replace("adm_chg_res_", ""))
    r = db.get_reseller_by_id(res_id)
    if not r:
        bot.answer_callback_query(call.id, "فروشنده یافت نشد!")
        return

    set_state(config.ADMIN_ID, "ADMIN_CHG_RES_GB", temp_data={"reseller_id": res_id})
    text = (
        f"➕ <b>افزایش سهمیه حجم برای: {r['name']}</b>\n\n"
        f"سهمیه فعلی: <b>{r['total_credit_gb']} گیگابایت</b>\n\n"
        "لطفاً مقدار حجم افزایشی را به <b>گیگابایت (GB)</b> بفرستید:\n"
        "مثال: <code>200</code>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data=f"adm_res_view_{res_id}"))
    bot.edit_message_text(text, call.from_user.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

def process_admin_chg_res_gb(message):
    raw = message.text.strip()
    try:
        add_gb = float(raw)
        if add_gb <= 0:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "❌ لطفاً مقدار حجم را به صورت یک عدد مثبت بفرستید.")
        return

    state = get_state(config.ADMIN_ID)
    temp = state.get("temp_data", {})
    clear_state(config.ADMIN_ID)
    res_id = temp["reseller_id"]
    db.update_reseller_credit(res_id, add_gb)

    r = db.get_reseller_by_id(res_id)
    bot.reply_to(message, f"✅ مقدار <b>{add_gb} گیگابایت</b> به سهمیه {r['name']} افزوده شد.\nسهمیه کل جدید: <b>{r['total_credit_gb']} GB</b>")
    if r.get("tg_id"):
        try:
            bot.send_message(r["tg_id"], f"🎉 <b>همکار گرامی، سهمیه شما توسط مدیریت شارژ شد!</b>\nمقدار افزوده شده: <code>+{add_gb} گیگابایت</code>\nسهمیه کل جدید: <code>{r['total_credit_gb']} گیگابایت</code>")
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_ext_res_"))
def handle_adm_ext_res(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    res_id = int(call.data.replace("adm_ext_res_", ""))
    r = db.get_reseller_by_id(res_id)
    if not r:
        bot.answer_callback_query(call.id, "فروشنده یافت نشد!")
        return

    set_state(config.ADMIN_ID, "ADMIN_EXT_RES_DAYS", temp_data={"reseller_id": res_id})
    text = (
        f"⏳ <b>تمدید تاریخ انقضا برای: {r['name']}</b>\n\n"
        f"تاریخ انقضای فعلی: <b>{r['expire_date']}</b>\n\n"
        "لطفاً تعداد روزهایی که می‌خواهید به قرارداد همکاری اضافه شود را ارسال فرمایید:\n"
        "مثال: <code>30</code>"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data=f"adm_res_view_{res_id}"))
    bot.edit_message_text(text, call.from_user.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

def process_admin_ext_res_days(message):
    raw = message.text.strip()
    try:
        add_days = int(raw)
        if add_days <= 0:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "❌ لطفاً تعداد روزها را به صورت یک عدد مثبت بفرستید.")
        return

    state = get_state(config.ADMIN_ID)
    temp = state.get("temp_data", {})
    clear_state(config.ADMIN_ID)
    res_id = temp["reseller_id"]
    r = db.get_reseller_by_id(res_id)

    try:
        curr_dt = datetime.strptime(r["expire_date"], "%Y-%m-%d").date()
        today = datetime.now().date()
        base_dt = max(curr_dt, today)
        new_dt = base_dt + timedelta(days=add_days)
    except Exception:
        new_dt = datetime.now().date() + timedelta(days=add_days)

    new_expire_str = new_dt.strftime("%Y-%m-%d")
    db.update_reseller_expiry(res_id, new_expire_str)

    bot.reply_to(message, f"✅ تاریخ انقضای قرارداد {r['name']} تا <b>{new_expire_str}</b> تمدید گردید.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_tog_res_"))
def handle_adm_tog_res(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    res_id = int(call.data.replace("adm_tog_res_", ""))
    db.toggle_reseller_status(res_id)
    handle_adm_res_view(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_unl_res_"))
def handle_adm_unl_res(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    res_id = int(call.data.replace("adm_unl_res_", ""))
    db.unbind_reseller_tg(res_id)
    bot.answer_callback_query(call.id, "اتصال تلگرام نماینده لغو شد. در ورود بعدی باید رمز بزند.")
    handle_adm_res_view(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_del_res_"))
def handle_adm_del_res(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    res_id = int(call.data.replace("adm_del_res_", ""))
    db.delete_reseller(res_id)
    bot.answer_callback_query(call.id, "نماینده با موفقیت حذف شد.")
    handle_adm_list_resellers(call)

@bot.callback_query_handler(func=lambda call: call.data == "reseller_cancel")
def handle_reseller_cancel(call):
    user_id = call.from_user.id
    clear_state(user_id)
    try:
        bot.delete_message(user_id, call.message.message_id)
    except Exception:
        pass
    reseller = db.get_reseller_by_tg(user_id)
    if reseller:
        show_reseller_dashboard(user_id, reseller)
    else:
        bot.send_message(user_id, "منوی اصلی:", reply_markup=kb.main_menu(user_id))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("res_rnw_"))
def handle_res_rnw_select(call):
    user_id = call.from_user.id
    target_uuid = call.data.replace("res_rnw_", "")
    reseller = db.get_reseller_by_tg(user_id)
    if not reseller:
        bot.answer_callback_query(call.id, "حساب نمایندگی یافت نشد!")
        return

    set_state(user_id, "RESELLER_RENEW_GB", temp_data={"reseller_id": reseller["id"], "target_uuid": target_uuid})
    stats = db.get_reseller_stats(reseller["id"])
    text = (
        "🔄 <b>تمدید و شارژ اشتراک مشتری</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"شناسه کاربر مشتری: <code>{target_uuid}</code>\n"
        f"سهمیه باقی‌مانده شما: <b>{stats['remaining_gb']} GB</b>\n\n"
        "لطفاً <b>مقدار حجم (گیگ) و تعداد روز</b> افزایشی را با یک فاصله بفرستید:\n"
        "فرمت:\n"
        "<code>[حجم_گیگ] [تعداد_روز]</code>\n\n"
        "مثال (افزودن ۲۰ گیگ و ۳۰ روز):\n"
        "<code>20 30</code>"
    )
    markup = kb.reseller_cancel_keyboard()
    bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

def process_reseller_renew_gb(message):
    user_id = message.from_user.id
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ فرمت نادرست است. مثال: <code>20 30</code> (۲۰ گیگ ۳۰ روز)")
        return

    try:
        add_gb = float(parts[0])
        add_days = int(parts[1])
        if add_gb < 0 or add_days < 0 or (add_gb == 0 and add_days == 0):
            raise ValueError
    except ValueError:
        bot.reply_to(message, "❌ حجم و روزها باید اعداد مثبت و معتبر باشند.")
        return

    state = get_state(user_id)
    temp = state.get("temp_data", {})
    clear_state(user_id)

    res_id = temp["reseller_id"]
    target_uuid = temp["target_uuid"]
    stats = db.get_reseller_stats(res_id)

    if add_gb > stats["remaining_gb"]:
        bot.send_message(user_id, f"❌ حجم درخواستی ({add_gb} GB) از سهمیه باقی‌مانده شما ({stats['remaining_gb']} GB) بیشتر است!", reply_markup=kb.reseller_main_menu())
        return

    bot.send_message(user_id, "⏳ در حال تمدید اشتراک مشتری در سرور...")

    ok, res = hiddify.add_traffic_and_days(target_uuid, add_gb=add_gb, add_days=add_days)
    if not ok:
        bot.send_message(user_id, f"❌ خطا در تمدید سرور:\n{res}", reply_markup=kb.reseller_main_menu())
        return

    db.deduct_reseller_credit(res_id, add_gb)
    send_sticker(user_id, "ROCKET")

    sub_url = hiddify.get_sub_url(target_uuid)
    msg = (
        "✅ <b>اشتراک مشتری با موفقیت تمدید شد!</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"📊 حجم افزوده شده: <b>+{add_gb} گیگابایت</b>\n"
        f"⏳ روزهای افزوده شده: <b>+{add_days} روز</b>\n"
        f"🔗 لینک اتصال (بدون تغییر):\n<code>{sub_url}</code>\n\n"
        f"سهمیه کسر شده از شما: <b>{add_gb} GB</b>"
    )
    bot.send_message(user_id, msg, reply_markup=kb.reseller_main_menu())

# ----------------- Comprehensive Admin Panel -----------------

def show_admin_panel(user_id):
    text = (
        "👑 <b>پنل مدیریت ارشد دلتا فورس نت & هیدیفای</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "این پنل به صورت مستقیم به هسته هیدیفای و دیتابیس متصل است.\n"
        "عملیات مورد نظر را از منوی زیر انتخاب نمایید:"
    )
    markup = kb.admin_panel_keyboard(hiddify.admin_url)
    bot.send_message(user_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "open_admin_panel")
def handle_cb_open_admin(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    show_admin_panel(call.from_user.id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "adm_server_status")
def handle_adm_server_status(call):
    if call.from_user.id != config.ADMIN_ID:
        return

    bot.answer_callback_query(call.id, "در حال دریافت اطلاعات زنده سرورها...")
    ok, data = hiddify.get_server_status()
    ok_nodes, data_nodes = hiddify.get_nodes()

    if not ok:
        bot.send_message(config.ADMIN_ID, f"❌ خطا در استعلام وضعیت سرور: {data}")
        return

    sys_info = data.get("stats", {}).get("system", {})
    hist = data.get("usage_history", {})

    cpu = round(sys_info.get("cpu_percent", 0), 1)
    ram_used = round(sys_info.get("ram_used", 0), 2)
    ram_total = round(sys_info.get("ram_total", 0), 2)
    disk_used = round(sys_info.get("disk_used", 0), 1)
    disk_total = round(sys_info.get("disk_total", 0), 1)

    today_online = hist.get("today", {}).get("online", 0)
    now_online = hist.get("m5", {}).get("online", 0)
    total_users = hist.get("total", {}).get("users", 0)

    # Today usage in GB
    today_bytes = int(hist.get("today", {}).get("usage", 0))
    today_gb = round(today_bytes / (1024**3), 2)

    # Nodes info
    nodes_text = "🇨🇭 <b>سرور والد (سوییس):</b> 🟢 فعال (freedom.thedragon.top)\n"
    if ok_nodes and "nodes" in data_nodes:
        for n in data_nodes["nodes"]:
            status_emoji = "🟢 آنلاین" if n.get("status") == "online" else "🔴 قطع"
            nodes_text += f"🇹🇷 <b>نود کمکی ({n.get('name', 'Turkey')}):</b> {status_emoji} ({n.get('host')})\n"

    status_msg = (
        "📊 <b>وضعیت زنده سرورها و سخت‌افزار</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"⚡️ <b>مصرف پردازنده (CPU):</b> <code>{cpu}%</code>\n"
        f"🧠 <b>حافظه رم (RAM):</b> <code>{ram_used} GB</code> از <code>{ram_total} GB</code>\n"
        f"💾 <b>فضای دیسک (Disk):</b> <code>{disk_used} GB</code> از <code>{disk_total} GB</code>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"👥 <b>کاربران آنلاین هم‌اکنون:</b> <b>{now_online} نفر</b>\n"
        f"📈 <b>کاربران آنلاین امروز:</b> <b>{today_online} نفر</b>\n"
        f"🌐 <b>کل کاربران پنل:</b> <b>{total_users} نفر</b>\n"
        f"📦 <b>مصرف ترافیک امروز:</b> <b>{today_gb} GB</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "🌐 <b>وضعیت سرورها و لوکیشن‌ها:</b>\n"
        f"{nodes_text}"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🔄 بروزرسانی مجدد", callback_data="adm_server_status"),
        types.InlineKeyboardButton("‹ بازگشت به مدیریت", callback_data="open_admin_panel")
    )
    bot.send_message(config.ADMIN_ID, status_msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_users_list")
def handle_adm_users_list(call):
    if call.from_user.id != config.ADMIN_ID:
        return

    bot.answer_callback_query(call.id, "در حال استعلام لیست کاربران...")
    ok, users = hiddify.get_all_users()
    if not ok:
        bot.send_message(config.ADMIN_ID, f"خطا: {users}")
        return

    msg = f"👥 <b>لیست کاربران پنل هیدیفای (تعداد کل: {len(users)})</b>\n➖➖➖➖➖➖➖➖➖➖\n"
    for u in users[:15]:  # Show first 15
        u_name = u.get("name", "بی‌نام")
        usage = round(u.get("current_usage_GB", 0), 2)
        limit = u.get("usage_limit_GB", 0)
        days = u.get("package_days", 0)
        status = "🟢" if not u.get("deleted") else "🔴"
        msg += f"{status} <b>{u_name}</b> | مصرف: <code>{usage}/{limit} GB</code> | روز: <code>{days}</code>\n"

    if len(users) > 15:
        msg += f"\n<i>... و {len(users) - 15} کاربر دیگر (در پنل وب قابل مشاهده است).</i>"

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("➕ ایجاد کاربر دستی", callback_data="adm_new_user"),
        types.InlineKeyboardButton("‹ بازگشت", callback_data="open_admin_panel")
    )
    bot.send_message(config.ADMIN_ID, msg, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_new_user")
def handle_adm_new_user(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    set_state(config.ADMIN_ID, "ADMIN_NEW_USER")
    bot.send_message(
        config.ADMIN_ID,
        "➕ <b>ایجاد کاربر دستی آنی در هیدیفای</b>\n\n"
        "لطفاً نام، حجم (گیگ) و روز را با فاصله بفرستید:\n"
        "فرمت:\n<code>[نام] [حجم] [تعداد_روز]</code>\n\n"
        "مثال:\n<code>ali-vip 30 30</code>"
    )
    bot.answer_callback_query(call.id)

def process_admin_new_user(message):
    clear_state(config.ADMIN_ID)
    parts = message.text.strip().split()
    if len(parts) < 3:
        bot.reply_to(message, "فرمت نادرست است. مثال: <code>ali-vip 30 30</code>")
        return

    name = parts[0]
    try:
        gb = float(parts[1])
        days = int(parts[2])
    except ValueError:
        bot.reply_to(message, "حجم و روز باید عدد باشند.")
        return

    bot.reply_to(message, "در حال صدور کاربر در هیدیفای...")
    ok, res = hiddify.create_user(name=name, usage_limit_gb=gb, package_days=days)
    if not ok:
        bot.send_message(config.ADMIN_ID, f"❌ خطا: {res}")
        return

    sub_url = res.get("sub_url")
    user_uuid = res.get("uuid")

    msg = (
        f"✅ <b>کاربر {name} با موفقیت در هیدیفای ایجاد شد!</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"📊 <b>حجم:</b> {gb} GB\n"
        f"⏳ <b>اعتبار:</b> {days} روز\n"
        f"🔑 <b>UUID:</b> <code>{user_uuid}</code>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 <b>لینک سابسکریپشن:</b>\n<code>{sub_url}</code>"
    )
    bot.send_message(config.ADMIN_ID, msg)

@bot.callback_query_handler(func=lambda call: call.data == "adm_pending_receipts")
def handle_adm_pending(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    conn = db.get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE status = 'pending_approval' ORDER BY created_at DESC")
    orders = [dict(r) for r in c.fetchall()]
    conn.close()

    if not orders:
        bot.answer_callback_query(call.id, "هیچ فیشی در انتظار تایید وجود ندارد.")
        return

    bot.send_message(config.ADMIN_ID, f"📑 <b>تعداد {len(orders)} فیش در انتظار تایید است:</b>")
    for o in orders:
        txt = (
            f"🆔 سفارش: <code>{o['order_id']}</code>\n"
            f"👤 کاربر: <code>{o['tg_id']}</code> | پلن: {o['plan_name']}\n"
            f"💵 مبلغ: <b>{o['final_price']:,} تومان</b>"
        )
        markup = kb.admin_receipt_keyboard(o["order_id"])
        if o.get("receipt_photo_id"):
            bot.send_photo(config.ADMIN_ID, o["receipt_photo_id"], caption=txt, reply_markup=markup)
        else:
            bot.send_message(config.ADMIN_ID, txt, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "adm_set_card")
def handle_adm_set_card(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    curr_card = db.get_setting("card_number")
    curr_holder = db.get_setting("card_holder")
    set_state(call.from_user.id, "ADMIN_SET_CARD")
    bot.send_message(
        call.from_user.id,
        f"کارت فعلی:\n<code>{curr_card}</code>\nبه نام: {curr_holder}\n\n"
        "لطفاً شماره کارت جدید و نام صاحب حساب را با یک فاصله بفرستید:\n"
        "مثال:\n<code>6037997012345678 رضا بابایی</code>"
    )
    bot.answer_callback_query(call.id)

def process_admin_set_card(message):
    clear_state(message.from_user.id)
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "فرمت اشتباه است. باید شماره کارت و نام را با فاصله بنویسید.")
        return
    db.set_setting("card_number", parts[0])
    db.set_setting("card_holder", parts[1])
    bot.reply_to(message, f"✅ اطلاعات کارت جدید ذخیره شد:\nشماره کارت: <code>{parts[0]}</code>\nنام: {parts[1]}")

# ----------------- Admin Plan Management -----------------

@bot.callback_query_handler(func=lambda call: call.data == "adm_list_plans")
def handle_adm_list_plans(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    plans = db.get_all_plans()
    text = (
        "📦 <b>مدیریت پلن‌های فروشگاه دلتا فورس نت</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "▫️ برای ویرایش قیمت، وضعیت یا حذف، روی پلن مورد نظر کلیک کنید.\n"
        "▫️ همچنین می‌توانید پلن جدید بسازید یا نرخ‌های پلن دلخواه را تغییر دهید."
    )
    markup = kb.admin_plans_list_keyboard(plans)
    bot.edit_message_text(text, call.from_user.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_plan_view_"))
def handle_adm_plan_view(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    plan_id = int(call.data.replace("adm_plan_view_", ""))
    plan = db.get_plan(plan_id)
    if not plan:
        bot.answer_callback_query(call.id, "پلن یافت نشد!")
        return

    status_txt = "🟢 فعال (قابل خرید توسط کاربران)" if plan["is_active"] else "🔴 غیرفعال (پنهان شده)"
    text = (
        f"📦 <b>مشخصات پلن: {plan['name']}</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"📊 <b>حجم:</b> {plan['traffic_gb']} گیگابایت\n"
        f"⏳ <b>مدت اعتبار:</b> {plan['days']} روز\n"
        f"💵 <b>قیمت فعلی:</b> <b>{plan['price_toman']:,} تومان</b>\n"
        f"⚙️ <b>وضعیت:</b> {status_txt}\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "عملیات مورد نظر را انتخاب فرمایید:"
    )
    markup = kb.admin_plan_detail_keyboard(plan_id, bool(plan["is_active"]))
    bot.edit_message_text(text, call.from_user.id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_toggle_plan_"))
def handle_adm_toggle_plan(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    plan_id = int(call.data.replace("adm_toggle_plan_", ""))
    db.toggle_plan_status(plan_id)
    plan = db.get_plan(plan_id)
    status_txt = "فعال شد 🟢" if plan["is_active"] else "غیرفعال شد 🔴"
    bot.answer_callback_query(call.id, f"پلن {status_txt}")
    
    # refresh view
    call.data = f"adm_plan_view_{plan_id}"
    handle_adm_plan_view(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_edit_price_"))
def handle_adm_edit_price(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    plan_id = int(call.data.replace("adm_edit_price_", ""))
    plan = db.get_plan(plan_id)
    set_state(config.ADMIN_ID, "ADMIN_EDIT_PRICE", temp_data={"plan_id": plan_id})
    bot.send_message(
        config.ADMIN_ID,
        f"قیمت فعلی پلن <b>{plan['name']}</b> برابر <code>{plan['price_toman']:,}</code> تومان است.\n\n"
        "لطفاً قیمت جدید را به تومان (فقط عدد) ارسال فرمایید:\n"
        "مثال:\n<code>85000</code>"
    )
    bot.answer_callback_query(call.id)

def process_admin_edit_price(message):
    state = get_state(config.ADMIN_ID)
    plan_id = state.get("temp_data", {}).get("plan_id")
    clear_state(config.ADMIN_ID)
    try:
        new_price = int(message.text.strip())
        db.update_plan_price(plan_id, new_price)
        plan = db.get_plan(plan_id)
        bot.reply_to(message, f"✅ قیمت پلن <b>{plan['name']}</b> با موفقیت به <b>{new_price:,} تومان</b> تغییر یافت.")
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: لطفاً فقط عدد وارد فرمایید ({e}).")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_del_plan_"))
def handle_adm_del_plan(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    plan_id = int(call.data.replace("adm_del_plan_", ""))
    db.delete_plan(plan_id)
    bot.answer_callback_query(call.id, "پلن حذف شد.")
    plans = db.get_all_plans()
    markup = kb.admin_plans_list_keyboard(plans)
    bot.edit_message_text("📦 <b>مدیریت پلن‌های فروشگاه</b>", call.from_user.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "adm_add_plan")
def handle_adm_add_plan(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    set_state(config.ADMIN_ID, "ADMIN_ADD_PLAN")
    text = (
        "➕ <b>افزودن پلن جدید به فروشگاه</b>\n\n"
        "لطفاً مشخصات پلن را با فرمت زیر (جدا شده با خط عمودی | یا فاصله) ارسال فرمایید:\n"
        "<code>[نام پلن] | [حجم به گیگ] | [تعداد روز] | [قیمت به تومان]</code>\n\n"
        "مثال:\n"
        "<code>پلن توربو ۶۰ گیگ | 60 | 30 | 280000</code>"
    )
    bot.send_message(config.ADMIN_ID, text)
    bot.answer_callback_query(call.id)

def process_admin_add_plan(message):
    clear_state(config.ADMIN_ID)
    text = message.text.strip()
    delimiter = "|" if "|" in text else None
    parts = [p.strip() for p in text.split(delimiter)] if delimiter else text.split()
    if len(parts) < 4:
        bot.reply_to(message, "❌ فرمت نادرست است.\nمثال: <code>پلن ویژه | 50 | 30 | 250000</code>")
        return
    name = parts[0]
    try:
        gb = float(parts[1])
        days = int(parts[2])
        price = int(parts[3])
    except ValueError:
        bot.reply_to(message, "حجم، روز و قیمت باید عدد باشند.")
        return

    db.add_plan(name, gb, days, price)
    bot.reply_to(message, f"✅ پلن جدید <b>{name}</b> با حجم {gb} گیگ و قیمت {price:,} تومان با موفقیت اضافه شد!")

@bot.callback_query_handler(func=lambda call: call.data == "adm_rates_setting")
def handle_adm_rates_setting(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    curr_gb = db.get_setting("price_per_gb", "6000")
    curr_day = db.get_setting("price_per_day", "1000")
    set_state(config.ADMIN_ID, "ADMIN_SET_RATES")
    text = (
        "⚙️ <b>تنظیم نرخ پایه پلن دلخواه</b>\n\n"
        f"نرخ فعلی هر گیگابایت: <code>{int(curr_gb):,}</code> تومان\n"
        f"نرخ فعلی هر روز: <code>{int(curr_day):,}</code> تومان\n\n"
        "لطفاً نرخ جدید هر گیگ و هر روز را با یک فاصله بفرستید:\n"
        "مثال:\n"
        "<code>7000 1200</code>"
    )
    bot.send_message(config.ADMIN_ID, text)
    bot.answer_callback_query(call.id)

def process_admin_set_rates(message):
    clear_state(config.ADMIN_ID)
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "فرمت نادرست است. مثال: <code>6000 1000</code>")
        return
    try:
        gb_rate = int(parts[0])
        day_rate = int(parts[1])
        db.set_setting("price_per_gb", gb_rate)
        db.set_setting("price_per_day", day_rate)
        bot.reply_to(message, f"✅ نرخ‌های پایه پلن دلخواه بروزرسانی شد:\n▫️ هر گیگابایت: <b>{gb_rate:,} تومان</b>\n▫️ هر روز: <b>{day_rate:,} تومان</b>")
    except ValueError:
        bot.reply_to(message, "نرخ‌ها باید عدد صحیح باشند.")

@bot.callback_query_handler(func=lambda call: call.data == "adm_new_discount")
def handle_adm_new_discount(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    set_state(config.ADMIN_ID, "ADMIN_NEW_DISCOUNT")
    text = (
        "🎟 <b>ساخت کد تخفیف جدید</b>\n\n"
        "لطفاً کد، درصد تخفیف و سقف استفاده را با فاصله ارسال فرمایید:\n"
        "فرمت:\n"
        "<code>[کد_تخفیف] [درصد] [تعداد_سقف]</code>\n\n"
        "مثال (۲۰ درصد تخفیف برای ۵۰ نفر):\n"
        "<code>DELTA20 20 50</code>"
    )
    bot.send_message(config.ADMIN_ID, text)
    bot.answer_callback_query(call.id)

def process_admin_new_discount(message):
    clear_state(config.ADMIN_ID)
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "فرمت نادرست است. مثال: <code>DELTA20 20 50</code>")
        return
    code = parts[0].upper()
    try:
        percent = int(parts[1])
        limit = int(parts[2]) if len(parts) > 2 else 100
        db.create_discount_code(code, percent=percent, usage_limit=limit)
        bot.reply_to(message, f"✅ کد تخفیف <code>{code}</code> با <b>{percent}٪ تخفیف</b> برای <b>{limit} نفر</b> ایجاد شد!")
    except ValueError:
        bot.reply_to(message, "درصد و سقف باید عدد باشند.")

@bot.callback_query_handler(func=lambda call: call.data == "adm_broadcast")
def handle_adm_broadcast(call):
    if call.from_user.id != config.ADMIN_ID:
        return
    set_state(config.ADMIN_ID, "ADMIN_BROADCAST")
    bot.send_message(config.ADMIN_ID, "📢 لطفاً متن یا پیام همگانی مورد نظر خود را ارسال فرمایید تا برای تمامی کاربران ربات ارسال شود:")
    bot.answer_callback_query(call.id)

def process_admin_broadcast(message):
    clear_state(config.ADMIN_ID)
    bc_text = message.text.strip()
    uids = db.get_all_user_ids()
    bot.reply_to(message, f"📢 در حال ارسال پیام همگانی به {len(uids)} کاربر...")
    sent = 0
    for uid in uids:
        try:
            bot.send_message(uid, bc_text)
            sent += 1
            time.sleep(0.04)
        except Exception:
            pass
    bot.send_message(config.ADMIN_ID, f"✅ پیام همگانی با موفقیت به {sent} کاربر ارسال شد.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_sub_") or call.data == "copy_sub")
def handle_copy_sub(call):
    user_id = call.from_user.id
    u_uuid = call.data.replace("copy_sub_", "") if call.data.startswith("copy_sub_") else None
    if u_uuid:
        sub_url = hiddify.get_sub_url(u_uuid)
    else:
        sub_url = config.HIDDIFY_SUB_BASE

    text = (
        "📋 <b>لینک اتصال سابسکریپشن:</b>\n\n"
        f"<code>{sub_url}</code>\n\n"
        "👆 <i>برای کپی آسان، کافیست روی لینک بالا ضربه بزنید. سپس در نرم‌افزار خود Import from clipboard یا Add Subscription بزنید.</i>"
    )
    bot.send_message(user_id, text)
    bot.answer_callback_query(call.id, "لینک سابسکریپشن آماده کپی است!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("renew_sub_") or call.data == "renew_sub")
def handle_renew_sub(call):
    user_id = call.from_user.id
    u_uuid = call.data.replace("renew_sub_", "") if call.data.startswith("renew_sub_") else ""
    plans = db.get_active_plans()

    markup = types.InlineKeyboardMarkup(row_width=1)
    for p in plans:
        markup.add(types.InlineKeyboardButton(f"تمدید با {p['name']} — {p['price_toman']:,} ت", callback_data=f"rnw_p_{p['id']}_{u_uuid}"))
    markup.add(types.InlineKeyboardButton("‹ انصراف و بازگشت", callback_data="back_to_main"))

    text = (
        "🔄 <b>تمدید اشتراک هوشمند</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "با تمدید اشتراک، حجم و روزهای انتخابی به همین کانفیگ فعلی شما افزوده می‌شود و نیازی به تعویض لینک نخواهید داشت.\n\n"
        "لطفاً بسته تمدیدی مورد نظر را انتخاب فرمایید:"
    )
    bot.send_message(user_id, text, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rnw_p_"))
def handle_rnw_p(call):
    user_id = call.from_user.id
    parts = call.data.replace("rnw_p_", "").split("_")
    plan_id = int(parts[0])
    target_uuid = parts[1] if len(parts) > 1 and parts[1] else None

    plan = db.get_plan(plan_id)
    if not plan:
        bot.answer_callback_query(call.id, "پلن یافت نشد!")
        return

    order_id = f"RN-{int(time.time())}-{user_id % 10000}"
    db.create_order(
        order_id=order_id,
        tg_id=user_id,
        plan_name=f"تمدید: {plan['name']}",
        traffic_gb=plan["traffic_gb"],
        days=plan["days"],
        original_price=plan["price_toman"],
        final_price=plan["price_toman"],
        custom_name=f"renew:{target_uuid}" if target_uuid else "renew"
    )
    if target_uuid:
        db.update_order_status(order_id, "pending_payment", hiddify_uuid=target_uuid)

    send_order_invoice(user_id, order_id, call.message.message_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "query_sub_link")
def handle_cb_query_sub_link(call):
    user_id = call.from_user.id
    ask_subscription_link(user_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_sub_query")
def handle_cb_cancel_sub_query(call):
    user_id = call.from_user.id
    clear_state(user_id)
    try:
        bot.delete_message(user_id, call.message.message_id)
    except Exception:
        pass
    bot.send_message(user_id, "عملیات استعلام لغو شد.", reply_markup=kb.main_menu(user_id))
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "open_plans")
def handle_cb_open_plans(call):
    user_id = call.from_user.id
    show_plans(user_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "get_free_test")
def handle_cb_get_free_test(call):
    user_id = call.from_user.id
    handle_free_test_account(user_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "open_tutorials")
def handle_cb_open_tutorials(call):
    user_id = call.from_user.id
    show_tutorials(user_id)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def handle_cb_back_main(call):
    user_id = call.from_user.id
    clear_state(user_id)
    bot.delete_message(user_id, call.message.message_id)
    bot.send_message(user_id, "منوی اصلی:", reply_markup=kb.main_menu(user_id))
    bot.answer_callback_query(call.id)

# ----------------- Main Entrypoint -----------------

if __name__ == "__main__":
    logger.info("Delta Force Shop Bot starting...")
    try:
        bot.remove_webhook()
    except Exception:
        pass

    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=15)
        except Exception as e:
            logger.error(f"Polling crashed: {e}. Retrying in 5 seconds...")
            time.sleep(5)
