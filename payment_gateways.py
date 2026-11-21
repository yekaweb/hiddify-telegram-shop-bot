"""
Payment Gateway Drivers for ZarinPal and Zibal.
Standardized according to official REST API specifications.
"""
import requests
import logging

logger = logging.getLogger("PaymentGateways")

class ZarinPalClient:
    """Official ZarinPal REST API v4 Client."""
    def __init__(self, merchant_id: str, is_sandbox: bool = False):
        self.merchant_id = str(merchant_id).strip()
        self.is_sandbox = bool(is_sandbox)
        
        if self.is_sandbox:
            self.base_url = "https://sandbox.zarinpal.com/pg/v4/payment"
            self.start_pay_base = "https://sandbox.zarinpal.com/pg/StartPay"
        else:
            self.base_url = "https://api.zarinpal.com/pg/v4/payment"
            self.start_pay_base = "https://www.zarinpal.com/pg/StartPay"

    def is_configured(self) -> bool:
        return bool(self.merchant_id and len(self.merchant_id) >= 10)

    def request_payment(self, amount_tomans: int, description: str, callback_url: str, mobile: str = None, email: str = None):
        """Request payment link from ZarinPal. Returns (success, payment_url, authority_or_err)."""
        if not self.is_configured():
            return False, None, "مرچنت کد زرین‌پال تنظیم نشده است."

        amount_rials = int(amount_tomans) * 10
        url = f"{self.base_url}/request.json"
        
        metadata = {}
        if mobile:
            metadata["mobile"] = str(mobile)
        if email:
            metadata["email"] = str(email)

        payload = {
            "merchant_id": self.merchant_id,
            "amount": amount_rials,
            "description": description or "خرید اشتراک دلتا فورس",
            "callback_url": callback_url,
            "metadata": metadata
        }

        try:
            resp = requests.post(url, json=payload, timeout=12)
            data = resp.json().get("data", {})
            errors = resp.json().get("errors", [])
            
            code = data.get("code")
            if code == 100:
                authority = data.get("authority")
                payment_url = f"{self.start_pay_base}/{authority}"
                return True, payment_url, authority
            else:
                err_msg = f"خطای زرین‌پال ({code}): {errors or data.get('message')}"
                logger.error(err_msg)
                return False, None, err_msg
        except Exception as e:
            logger.error(f"ZarinPal request exception: {e}")
            return False, None, str(e)

    def verify_payment(self, authority: str, amount_tomans: int):
        """Verify payment with ZarinPal. Returns (success, ref_id, card_or_err)."""
        if not self.is_configured():
            return False, None, "مرچنت کد زرین‌پال تنظیم نشده است."

        amount_rials = int(amount_tomans) * 10
        url = f"{self.base_url}/verify.json"
        payload = {
            "merchant_id": self.merchant_id,
            "amount": amount_rials,
            "authority": str(authority)
        }

        try:
            resp = requests.post(url, json=payload, timeout=12)
            res_json = resp.json()
            data = res_json.get("data", {})
            errors = res_json.get("errors", [])
            code = data.get("code")

            if code in (100, 101):
                ref_id = str(data.get("ref_id"))
                card_pan = data.get("card_pan", "")
                return True, ref_id, card_pan
            else:
                err_msg = f"کد خطا {code}: {errors or data.get('message', 'تراکنش ناموفق')}"
                return False, None, err_msg
        except Exception as e:
            logger.error(f"ZarinPal verify exception: {e}")
            return False, None, str(e)


class ZibalClient:
    """Official Zibal Payment Gateway Client."""
    def __init__(self, merchant: str = "zibal"):
        self.merchant = str(merchant).strip() or "zibal"
        self.base_url = "https://gateway.zibal.ir/v1"
        self.start_url_base = "https://gateway.zibal.ir/start"

    def is_configured(self) -> bool:
        return bool(self.merchant and len(self.merchant) >= 5)

    def request_payment(self, amount_tomans: int, description: str, callback_url: str, order_id: str = None, mobile: str = None):
        """Request payment link from Zibal. Returns (success, payment_url, track_id_or_err)."""
        if not self.is_configured():
            return False, None, "مرچنت کد زیبال تنظیم نشده است."

        amount_rials = int(amount_tomans) * 10
        url = f"{self.base_url}/request"
        payload = {
            "merchant": self.merchant,
            "amount": amount_rials,
            "callbackUrl": callback_url,
            "description": description or "خرید اشتراک دلتا فورس",
        }
        if order_id:
            payload["orderId"] = str(order_id)
        if mobile:
            payload["mobile"] = str(mobile)

        try:
            resp = requests.post(url, json=payload, timeout=12)
            data = resp.json()
            result = data.get("result")

            if result == 100:
                track_id = str(data.get("trackId"))
                payment_url = f"{self.start_url_base}/{track_id}"
                return True, payment_url, track_id
            else:
                err_msg = f"خطای زیبال ({result}): {data.get('message', 'خطای نامشخص')}"
                logger.error(err_msg)
                return False, None, err_msg
        except Exception as e:
            logger.error(f"Zibal request exception: {e}")
            return False, None, str(e)

    def verify_payment(self, track_id: str):
        """Verify payment with Zibal. Returns (success, ref_number, card_or_err)."""
        if not self.is_configured():
            return False, None, "مرچنت کد زیبال تنظیم نشده است."

        url = f"{self.base_url}/verify"
        payload = {
            "merchant": self.merchant,
            "trackId": int(track_id)
        }

        try:
            resp = requests.post(url, json=payload, timeout=12)
            data = resp.json()
            result = data.get("result")

            if result in (100, 201):
                ref_number = str(data.get("refNumber", ""))
                card_number = data.get("cardNumber", "")
                return True, ref_number, card_number
            else:
                err_msg = f"کد نتیجه {result}: {data.get('message', 'تراکنش ناموفق یا پرداخت نشده')}"
                return False, None, err_msg
        except Exception as e:
            logger.error(f"Zibal verify exception: {e}")
            return False, None, str(e)
