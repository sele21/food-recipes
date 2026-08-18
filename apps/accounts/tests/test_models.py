from django.test import TestCase
from django.contrib.auth import get_user_model
from accounts.models import Follow
from recipes.models import Recipe, Like

User = get_user_model()


class UserModelTest(TestCase):
    """Test custom user model"""

    # comment this out what it does
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="testpassword",
            first_name="Test",
            last_name="User",
            bio="Test bio",
            website="https://example.com",
        )

    def test_user_creation(self):
        """Test user is created with all fields"""

        self.assertEqual(self.user.username, "testuser")
        self.assertEqual(self.user.email, "testuser@example.com")
        self.assertTrue(self.user.check_password("testpassword"))
        self.assertEqual(self.user.first_name, "Test")
        self.assertEqual(self.user.last_name, "User")
        self.assertEqual(self.user.bio, "Test bio")
        self.assertEqual(self.user.website, "https://example.com")

    def test_user_str_method(self):
        """test string representation"""
        self.assertEqual(str(self.user), "testuser")

    def test_user_email_unique(self):
        """test that email must be unique"""

        with self.assertRaises(Exception):
            User.objects.create_user(
                username="another",
                email="testuser@example.com",  # same email
                password="testpassword",
            )

    def test_user_recipe_count_method(self):
        """test recipe count property return correct number"""

        Recipe.objects.create(
            title="Recipe1",
            description="test",
            creator=self.user,
            prep_time=10,
            cook_time=5,
            servings=4,
        )
        Recipe.objects.create(
            title="recipe2",
            description="test",
            creator=self.user,
            prep_time=10,
            cook_time=5,
            servings=4,
        )

        self.assertEqual(self.user.recipe_count(), 2)

    def test_user_str_method_without_username(self):
        """test string fallback if no username"""

        user = User.objects.create(
            username="",
            email="nouser@example.com",
        )

        self.assertEqual(str(user), "nouser@example.com")


class FollowModelTests(TestCase):
    """test follow model"""

    def setUp(self):
        self.user1 = User.objects.create_user(
            username="user1", email="user1@example.com", password="testpassword"
        )
        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="testpassword",
        )

    def test_follow_creation(self):
        """test creating a follow relationship"""

        follow = Follow.objects.create(
            follower=self.user1,
            followed=self.user2,
        )
        self.assertEqual(follow.follower, self.user1)
        self.assertEqual(follow.followed, self.user2)
        self.assertIsNotNone(follow.created_at)

    def test_unique_follow(self):
        """test can't follow same user twice"""

        Follow.objects.create(follower=self.user1, followed=self.user2)

        with self.assertRaises(Exception):
            Follow.objects.create(follower=self.user1, followed=self.user2)

    def test_follow_str_method(self):
        """test string representation"""

        follow = Follow.objects.create(follower=self.user1, followed=self.user2)
        self.assertEqual(str(follow), "user1 follows user2")

    def test_follower_count(self):
        """test follower count works"""

        Follow.objects.create(follower=self.user2, followed=self.user1)
        # Follow.objects.create(follower=self.user1, followed=self.user2)

        user3 = User.objects.create_user(
            username="user3", email="user3@example.com", password="test"
        )
        Follow.objects.create(follower=user3, followed=self.user1)

        self.assertEqual(self.user1.followers.count(), 2)

    def test_following_count(self):
        """test following count works"""

        Follow.objects.create(follower=self.user1, followed=self.user2)
        user3 = User.objects.create(
            username="user3", email="user3@example.com", password="test"
        )
        Follow.objects.create(follower=self.user1, followed=user3)

        self.assertEqual(self.user1.following.count(), 2)

    def test_cannot_follow_self(self):
        """test user cannot follow themselves"""

        with self.assertRaises(Exception):
            Follow.objects.create(follower=self.user1, followed=self.user1)
