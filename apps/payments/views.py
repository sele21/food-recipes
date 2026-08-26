from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.urls import reverse
from django.contrib import messages

import json
import uuid
import logging
import chapa

from recipes.models import Recipe
from .models import Purchase
from .services import initialize_payment, verify_payment

logger = logging.getLogger(__name__)


@csrf_exempt
def chapa_webhook(request):
    """
    Webhook handler for Chapa payment events.
    Verifies payload signature and transaction status before updating database.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'failed', 'message': 'Method not allowed'}, status=405)

    try:
        payload_data = json.loads(request.body)
        event_data = payload_data.get('data', {}) if isinstance(payload_data.get('data'), dict) else {}
        tx_ref = event_data.get('tx_ref') or payload_data.get('tx_ref')

        if not tx_ref:
            logger.warning("Chapa webhook received without tx_ref")
            return JsonResponse({'status': 'failed', 'message': 'Missing tx_ref'}, status=400)

        # Verify signature if secret key is present
        secret_key = getattr(settings, 'CHAPA_SECRET_KEY', None)
        signature = request.headers.get('Chapa-Signature') or request.headers.get('x-chapa-signature')
        
        if secret_key and signature:
            try:
                if not chapa.verify_webhook(secret_key, payload_data, signature):
                    logger.warning(f"Invalid webhook signature for tx_ref={tx_ref}")
                    return JsonResponse({'status': 'failed', 'message': 'Invalid signature'}, status=400)
            except Exception as e:
                logger.error(f"Webhook signature verification error: {e}")

        # Find corresponding purchase record
        purchase = Purchase.objects.filter(transaction_id=tx_ref).first()
        if not purchase:
            logger.warning(f"Purchase not found for webhook tx_ref={tx_ref}")
            return JsonResponse({'status': 'failed', 'message': 'Purchase not found'}, status=404)

        # Check payload status or verify via Chapa API
        status_value = payload_data.get('status') or event_data.get('status')
        
        # If payload doesn't explicitly state success, perform API verification
        if status_value != 'success':
            verification_resp = verify_payment(tx_ref)
            if verification_resp.get('status') == 'success':
                status_value = 'success'

        if status_value == 'success':
            purchase.status = Purchase.STATUS_COMPLETED
            purchase.save()
            logger.info(f"Purchase #{purchase.id} marked as COMPLETED for tx_ref={tx_ref}")
            return JsonResponse({'status': 'success'})
        else:
            purchase.status = Purchase.STATUS_FAILED
            purchase.save()
            logger.info(f"Purchase #{purchase.id} marked as FAILED for tx_ref={tx_ref}")
            return JsonResponse({'status': 'failed', 'message': 'Transaction not successful'})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'failed', 'message': 'Invalid JSON body'}, status=400)
    except Exception as e:
        logger.error(f"Chapa webhook processing error: {e}", exc_info=True)
        return JsonResponse({'status': 'failed', 'message': 'Internal server error'}, status=500)


@login_required
def checkout(request, recipe_id):
    """
    Checkout page for purchasing premium recipes via Chapa.
    Handles retries by updating existing pending/failed purchase records.
    """
    recipe = get_object_or_404(Recipe, id=recipe_id, is_premium=True)

    # Check if user already purchased this recipe
    if Purchase.objects.filter(user=request.user, recipe=recipe, status=Purchase.STATUS_COMPLETED).exists():
        messages.info(request, "You have already purchased this premium recipe.")
        return redirect('recipes:recipe_detail', slug=recipe.slug)

    if request.method == 'POST':
        tx_ref = f"recipe-{recipe.id}-{uuid.uuid4().hex[:8]}"

        # Extract user details with safe fallbacks
        user = request.user
        email = user.email.strip() if user.email and user.email.strip() else f"{user.username}@example.com"
        first_name = user.first_name.strip() if user.first_name and user.first_name.strip() else user.username
        last_name = user.last_name.strip() if user.last_name and user.last_name.strip() else "Customer"

        # Create or update pending purchase record for retries
        purchase, created = Purchase.objects.update_or_create(
            user=request.user,
            recipe=recipe,
            defaults={
                'transaction_id': tx_ref,
                'amount': recipe.price,
                'status': Purchase.STATUS_PENDING,
            }
        )

        callback_url = request.build_absolute_uri(reverse('payments:webhook'))
        return_url = request.build_absolute_uri(reverse('payments:success') + f"?tx_ref={tx_ref}")

        response = initialize_payment(
            email=email,
            amount=recipe.price,
            tx_ref=tx_ref,
            callback_url=callback_url,
            return_url=return_url,
            first_name=first_name,
            last_name=last_name,
        )

        checkout_url = None
        if isinstance(response, dict):
            status_val = response.get('status')
            data_val = response.get('data') or {}
            if isinstance(data_val, dict):
                checkout_url = data_val.get('checkout_url')
            elif hasattr(data_val, 'checkout_url'):
                checkout_url = getattr(data_val, 'checkout_url')

        if checkout_url:
            return redirect(checkout_url)

        logger.error(f"Payment initialization failed for recipe {recipe.id}: {response}")
        messages.error(request, f"Payment initiation failed: {response.get('message', 'Please try again.')}")
        return render(request, 'payments/checkout.html', {'recipe': recipe, 'error': response.get('message')})

    return render(request, 'payments/checkout.html', {'recipe': recipe})


def payment_success(request):
    """
    Success landing page after payment.
    Verifies payment status with gateway if pending, adds success message,
    and passes purchase & recipe receipt details to the template with auto-redirect logic.
    """
    tx_ref = (
        request.GET.get('tx_ref')
        or request.GET.get('trx_ref')
        or request.GET.get('reference')
        or request.GET.get('transaction_id')
    )

    purchase = None
    recipe = None

    if tx_ref:
        purchase = Purchase.objects.filter(transaction_id=tx_ref).select_related('recipe', 'user').first()
    elif request.user.is_authenticated:
        # Fallback to user's most recent completed or pending purchase if tx_ref query param omitted
        purchase = (
            Purchase.objects.filter(user=request.user)
            .select_related('recipe', 'user')
            .order_by('-purchased_at')
            .first()
        )

    if purchase:
        recipe = purchase.recipe
        # If webhook hasn't updated status yet, verify directly with gateway
        if purchase.status != Purchase.STATUS_COMPLETED and tx_ref:
            verification = verify_payment(tx_ref)
            v_status = verification.get('status') if isinstance(verification, dict) else getattr(verification, 'status', None)
            v_data = verification.get('data') if isinstance(verification, dict) else getattr(verification, 'data', {})
            data_status = v_data.get('status') if isinstance(v_data, dict) else getattr(v_data, 'status', None)

            if v_status == 'success' or data_status == 'success':
                purchase.status = Purchase.STATUS_COMPLETED
                purchase.save()

        if purchase.status == Purchase.STATUS_COMPLETED:
            messages.success(request, f"🎉 Payment successful! You now have full access to '{recipe.title}'.")
            if request.GET.get('redirect') == 'now':
                return redirect('recipes:recipe_detail', slug=recipe.slug)

    context = {
        'purchase': purchase,
        'recipe': recipe,
        'message': 'Payment completed!',
    }
    return render(request, 'payments/success.html', context)


def payment_cancel(request):
    """Cancel landing page if user cancels payment on Chapa interface."""
    tx_ref = request.GET.get('tx_ref')
    recipe = None
    if tx_ref:
        purchase = Purchase.objects.filter(transaction_id=tx_ref).first()
        if purchase:
            if purchase.status == Purchase.STATUS_PENDING:
                purchase.status = Purchase.STATUS_CANCELLED
                purchase.save()
            recipe = purchase.recipe

    return render(request, 'payments/cancel.html', {'recipe': recipe})
