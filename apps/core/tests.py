from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from recipes.models import Recipe, Category, Like

User = get_user_model()


class HomeViewTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="u1", email="u1@example.com", password="pass123")
        self.user2 = User.objects.create_user(username="u2", email="u2@example.com", password="pass123")

        self.category = Category.objects.create(name="Dinner", slug="dinner")

        self.recipe1 = Recipe.objects.create(
            title="Pasta",
            description="Tasty pasta",
            creator=self.user1,
            category=self.category,
            prep_time=10,
            cook_time=15,
            servings=2,
            is_published=True,
        )

        self.recipe2 = Recipe.objects.create(
            title="Pizza",
            description="Cheesy pizza",
            creator=self.user2,
            category=self.category,
            prep_time=20,
            cook_time=20,
            servings=4,
            is_published=True,
        )

        # Create likes
        Like.objects.create(user=self.user1, recipe=self.recipe1)
        Like.objects.create(user=self.user2, recipe=self.recipe1)
        Like.objects.create(user=self.user1, recipe=self.recipe2)

        self.client = Client()

    def test_home_view_statistics(self):
        """Verify that HomeView correctly aggregates user, recipe, category, and likes counts."""
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context["recipe_count"], 2)
        self.assertEqual(response.context["category_count"], 1)
        self.assertEqual(response.context["user_count"], 2)
        self.assertEqual(response.context["total_likes"], 3)
        self.assertEqual(response.context["like_count"], 3)

        # Verify likes rendered in template
        self.assertContains(response, "3")
