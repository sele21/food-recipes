import logging
import requests
import chapa
from django.conf import settings

logger = logging.getLogger(__name__)


def get_chapa_client():
    secret_key = getattr(settings, 'CHAPA_SECRET_KEY', None)
    if not secret_key:
        logger.error("CHAPA_SECRET_KEY is not configured in settings.")
        raise ValueError("Chapa API secret key is missing.")
    return chapa.Chapa(secret_key)


def initialize_payment(email, amount, tx_ref, callback_url, return_url, first_name="Customer", last_name="User", currency="ETB"):
    """Initialize transaction with Chapa payment gateway."""
    try:
        client = get_chapa_client()
        formatted_amount = float(amount)

        # Ensure first_name and last_name are non-empty strings
        first_name = str(first_name).strip() if first_name else "Customer"
        last_name = str(last_name).strip() if last_name else "User"

        response = client.initialize(
            email=email,
            amount=formatted_amount,
            first_name=first_name,
            last_name=last_name,
            tx_ref=tx_ref,
            currency=currency,
            callback_url=callback_url,
            return_url=return_url,
        )

        # Normalize response if Response object returned
        if not isinstance(response, dict):
            status_val = getattr(response, 'status', 'success')
            msg_val = getattr(response, 'message', '')
            data_val = getattr(response, 'data', {})
            
            checkout_url = None
            if isinstance(data_val, dict):
                checkout_url = data_val.get('checkout_url')
            elif hasattr(data_val, 'checkout_url'):
                checkout_url = getattr(data_val, 'checkout_url')

            return {
                'status': status_val,
                'message': msg_val,
                'data': {'checkout_url': checkout_url} if checkout_url else data_val
            }

        return response
    except Exception as e:
        logger.error(f"Failed to initialize Chapa payment for {tx_ref}: {e}", exc_info=True)
        return {'status': 'failed', 'message': str(e)}


def verify_payment(tx_ref):
    """
    Verify transaction status with Chapa API.
    Falls back to direct REST API GET request if SDK verify() encounters an httpx bug.
    """
    secret_key = getattr(settings, 'CHAPA_SECRET_KEY', None)

    # 1. Attempt SDK verification
    try:
        client = get_chapa_client()
        response = client.verify(tx_ref)
        if not isinstance(response, dict):
            return {
                'status': getattr(response, 'status', 'failed'),
                'message': getattr(response, 'message', ''),
                'data': getattr(response, 'data', {})
            }
        return response
    except Exception as e:
        logger.warning(f"Chapa SDK verify failed ({e}) for {tx_ref}, falling back to direct HTTP verification.")

    # 2. Direct HTTP verification fallback (bypasses SDK httpx.Client.get bug)
    if not secret_key:
        return {'status': 'failed', 'message': 'Chapa secret key missing'}

    try:
        url = f"https://api.chapa.co/v1/transaction/verify/{tx_ref}"
        headers = {'Authorization': f'Bearer {secret_key}'}
        res = requests.get(url, headers=headers, timeout=10)
        return res.json()
    except Exception as ex:
        logger.error(f"Direct Chapa REST API verification failed for {tx_ref}: {ex}", exc_info=True)
        return {'status': 'failed', 'message': str(ex)}
