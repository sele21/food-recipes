import json
from unittest.mock import patch
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from recipes.models import Recipe, Category
from payments.models import Purchase
from payments.services import initialize_payment

User = get_user_model()


class PaymentSystemTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="buyer", email="buyer@example.com", password="password123"
        )
        self.creator = User.objects.create_user(
            username="chef", email="chef@example.com", password="password123"
        )
        self.category = Category.objects.create(name="Dessert", slug="dessert")

        self.premium_recipe = Recipe.objects.create(
            title="Truffle Cake",
            description="Luxury chocolate cake",
            creator=self.creator,
            category=self.category,
            prep_time=20,
            cook_time=30,
            servings=8,
            is_premium=True,
            price=Decimal("150.00"),
            is_published=True,
        )

        self.free_recipe = Recipe.objects.create(
            title="Simple Salad",
            description="Quick salad recipe",
            creator=self.creator,
            category=self.category,
            prep_time=5,
            cook_time=0,
            servings=2,
            is_premium=False,
            is_published=True,
        )

        self.client = Client()

    def test_purchase_model_properties(self):
        """Test Purchase model properties and status helpers."""
        purchase = Purchase.objects.create(
            user=self.user,
            recipe=self.premium_recipe,
            transaction_id="tx-12345",
            amount=Decimal("150.00"),
            status=Purchase.STATUS_PENDING,
        )
        self.assertFalse(purchase.is_completed)
        self.assertIn("buyer@example.com", str(purchase))

        purchase.status = Purchase.STATUS_COMPLETED
        purchase.save()
        self.assertTrue(purchase.is_completed)

    def test_checkout_requires_login(self):
        """Checkout page should redirect unauthenticated users to login."""
        url = reverse("payments:checkout", kwargs={"recipe_id": self.premium_recipe.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    @patch("payments.views.initialize_payment")
    def test_checkout_initiation_and_retry(self, mock_init):
        """Test checkout flow creating pending purchase and updating on retry."""
        mock_init.return_value = {
            "status": "success",
            "data": {"checkout_url": "https://checkout.chapa.co/pay/123"},
        }

        self.client.login(username="buyer", password="password123")
        url = reverse("payments:checkout", kwargs={"recipe_id": self.premium_recipe.id})

        # Initial POST request
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://checkout.chapa.co/pay/123")

        # Verify pending purchase created
        purchase = Purchase.objects.get(user=self.user, recipe=self.premium_recipe)
        self.assertEqual(purchase.status, Purchase.STATUS_PENDING)
        self.assertEqual(purchase.amount, Decimal("150.00"))

        # Retry POST request should update existing purchase without IntegrityError crash
        mock_init.return_value = {
            "status": "success",
            "data": {"checkout_url": "https://checkout.chapa.co/pay/456"},
        }
        retry_response = self.client.post(url)
        self.assertEqual(retry_response.status_code, 302)
        self.assertEqual(retry_response.url, "https://checkout.chapa.co/pay/456")

        updated_purchase = Purchase.objects.get(user=self.user, recipe=self.premium_recipe)
        self.assertEqual(updated_purchase.status, Purchase.STATUS_PENDING)

    def test_already_purchased_redirects_to_recipe(self):
        """Already purchased premium recipe should redirect user back to recipe detail."""
        Purchase.objects.create(
            user=self.user,
            recipe=self.premium_recipe,
            transaction_id="tx-completed",
            amount=Decimal("150.00"),
            status=Purchase.STATUS_COMPLETED,
        )

        self.client.login(username="buyer", password="password123")
        url = reverse("payments:checkout", kwargs={"recipe_id": self.premium_recipe.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("recipes:recipe_detail", kwargs={"slug": self.premium_recipe.slug}))

    @patch("payments.views.verify_payment")
    def test_webhook_successful_payment(self, mock_verify):
        """Webhook should mark purchase completed on successful payment status."""
        purchase = Purchase.objects.create(
            user=self.user,
            recipe=self.premium_recipe,
            transaction_id="tx-webhook-test",
            amount=Decimal("150.00"),
            status=Purchase.STATUS_PENDING,
        )

        payload = {
            "status": "success",
            "data": {"tx_ref": "tx-webhook-test"}
        }

        url = reverse("payments:webhook")
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, Purchase.STATUS_COMPLETED)

    def test_webhook_missing_tx_ref(self):
        """Webhook should return 400 if tx_ref is missing."""
        url = reverse("payments:webhook")
        response = self.client.post(url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_premium_paywall_access_control(self):
        """Test RecipeDetailView paywall access control."""
        detail_url = reverse("recipes:recipe_detail", kwargs={"slug": self.premium_recipe.slug})

        # 1. Anonymous user -> has_access is False
        anon_resp = self.client.get(detail_url)
        self.assertEqual(anon_resp.status_code, 200)
        self.assertFalse(anon_resp.context["has_access"])
        self.assertContains(anon_resp, "Premium Recipe Content Locked")

        # 2. Logged in buyer without purchase -> has_access is False
        self.client.login(username="buyer", password="password123")
        buyer_resp = self.client.get(detail_url)
        self.assertEqual(buyer_resp.status_code, 200)
        self.assertFalse(buyer_resp.context["has_access"])

        # 3. Logged in creator -> has_access is True
        self.client.login(username="chef", password="password123")
        creator_resp = self.client.get(detail_url)
        self.assertEqual(creator_resp.status_code, 200)
        self.assertTrue(creator_resp.context["has_access"])

        # 4. Logged in buyer after purchase -> has_access is True
        Purchase.objects.create(
            user=self.user,
            recipe=self.premium_recipe,
            transaction_id="tx-access-test",
            amount=Decimal("150.00"),
            status=Purchase.STATUS_COMPLETED,
        )
        self.client.login(username="buyer", password="password123")
        purchased_resp = self.client.get(detail_url)
        self.assertEqual(purchased_resp.status_code, 200)
        self.assertTrue(purchased_resp.context["has_access"])

    @patch("payments.services.chapa.Chapa")
    def test_initialize_payment_service(self, mock_chapa_cls):
        """Test initialize_payment service instantiates chapa.Chapa correctly."""
        mock_instance = mock_chapa_cls.return_value
        mock_instance.initialize.return_value = {
            "status": "success",
            "data": {"checkout_url": "https://checkout.chapa.co/pay/test"}
        }
        res = initialize_payment("test@example.com", Decimal("100.00"), "tx-ref-1", "http://callback", "http://return")
        self.assertEqual(res["status"], "success")

    def test_payment_success_renders_receipt_and_recipe_details(self):
        """Test payment_success view displays receipt, recipe details, and auto-redirect countdown."""
        purchase = Purchase.objects.create(
            user=self.user,
            recipe=self.premium_recipe,
            transaction_id="tx-success-receipt",
            amount=Decimal("150.00"),
            status=Purchase.STATUS_COMPLETED,
        )

        self.client.login(username="buyer", password="password123")
        url = reverse("payments:success") + "?tx_ref=tx-success-receipt"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/success.html")
        self.assertEqual(response.context["purchase"], purchase)
        self.assertEqual(response.context["recipe"], self.premium_recipe)
        self.assertContains(response, "Truffle Cake")
        self.assertContains(response, "150.00")
        self.assertContains(response, "COMPLETED")
        self.assertContains(response, "countdown")

    @patch("payments.views.verify_payment")
    def test_payment_success_verifies_pending_purchase(self, mock_verify):
        """Test payment_success verifies pending purchase with gateway and displays receipt."""
        mock_verify.return_value = {"status": "success", "data": {"status": "success"}}
        purchase = Purchase.objects.create(
            user=self.user,
            recipe=self.premium_recipe,
            transaction_id="tx-pending-verify",
            amount=Decimal("150.00"),
            status=Purchase.STATUS_PENDING,
        )

        self.client.login(username="buyer", password="password123")
        url = reverse("payments:success") + "?tx_ref=tx-pending-verify"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, Purchase.STATUS_COMPLETED)
        self.assertEqual(response.context["recipe"], self.premium_recipe)
        self.assertContains(response, "Truffle Cake")

    def test_payment_success_immediate_redirect_option(self):
        """Test redirect=now param on payment_success redirects directly to recipe page."""
        Purchase.objects.create(
            user=self.user,
            recipe=self.premium_recipe,
            transaction_id="tx-direct-redirect",
            amount=Decimal("150.00"),
            status=Purchase.STATUS_COMPLETED,
        )

        self.client.login(username="buyer", password="password123")
        url = reverse("payments:success") + "?tx_ref=tx-direct-redirect&redirect=now"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("recipes:recipe_detail", kwargs={"slug": self.premium_recipe.slug}))

