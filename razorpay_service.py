"""
razorpay_service.py
-------------------
Dedicated service for Razorpay test-mode order creation and signature verification.
All secrets come from environment variables; no client-supplied secrets are trusted.
"""

import os
import hmac
import hashlib
import logging

try:
    import razorpay  # type: ignore
except Exception:
    razorpay = None  # Allow patching in tests

logger = logging.getLogger(__name__)


class RazorpayServiceError(Exception):
    pass


def _get_keys():
    key_id = os.environ.get('RAZORPAY_KEY_ID') or ''
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET') or ''
    return key_id.strip(), key_secret.strip()


def is_configured():
    key_id, key_secret = _get_keys()
    return bool(key_id and key_secret)


def create_order(amount, receipt=None, notes=None, currency=None):
    """
    Create a Razorpay order. Amount should be passed in the smallest currency unit
    as expected by Razorpay (e.g., paise for INR). Caller is responsible for
    computing amount from server-side trek data.
    """
    if not is_configured():
        raise RazorpayServiceError('Razorpay is not configured (missing RAZORPAY_KEY_ID/SECRET)')

    try:
        import razorpay as _razorpay
    except ImportError as exc:
        raise RazorpayServiceError('razorpay package not installed') from exc

    key_id, key_secret = _get_keys()
    client = _razorpay.Client(auth=(key_id, key_secret))

    if currency is None:
        currency = os.environ.get('PAYMENT_CURRENCY', 'INR')

    order_data = {
        'amount': int(amount),
        'currency': currency,
        'receipt': receipt or '',
        'payment_capture': 1,
    }
    if notes:
        order_data['notes'] = notes

    try:
        order = client.order.create(data=order_data)
        return order
    except Exception as exc:
        logger.error('Razorpay order creation failed: %s', exc)
        raise RazorpayServiceError(f'Order creation failed: {exc}') from exc


def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verify Razorpay payment signature using server-side secret.
    Returns True if valid, False otherwise. Never trusts client messages.
    """
    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return False
    if not is_configured():
        return False

    key_id, key_secret = _get_keys()
    try:
        msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode('utf-8')
        expected = hmac.new(key_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()
        # Use constant-time comparison
        return hmac.compare_digest(expected, razorpay_signature.strip())
    except Exception as exc:
        logger.error('Razorpay signature verification error: %s', exc)
        return False


def get_order_amount_from_order(order):
    """Extract amount (in smallest unit) from Razorpay order dict if present."""
    try:
        return int(order.get('amount'))
    except Exception:
        return None
