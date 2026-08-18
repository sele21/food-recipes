from django.db import models
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.db.models import Avg

from django.utils import timezone
from datetime import timedelta
from django.conf import settings

User = get_user_model()


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        app_label = "recipes"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            # Auto-generate from name
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            while Category.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug
        else:
            # If slug is provided manually, ensure it's unique
            original_slug = self.slug
            counter = 1
            while Category.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1

        super().save(*args, **kwargs)


class Recipe(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recipes"
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True
    )

    prep_time = models.IntegerField(help_text="Preparation time in minutes")
    cook_time = models.IntegerField(help_text="Cooking time in minutes")
    servings = models.IntegerField(default=1)

    featured_image = models.ImageField(
        upload_to="recipes/featured/", blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True)
    is_premium = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, blank=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.title)

            # Ensure uniqueness
            original_slug = self.slug
            counter = 1
            while Recipe.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1

        super().save(*args, **kwargs)

    @property
    def average_rating(self):
        """Return average rating using a single DB aggregation query."""
        result = self.ratings.aggregate(avg=Avg('value'))
        return round(result['avg'], 1) if result['avg'] else 0

    @property
    def total_time(self):
        """return total preparation time (prep + cook)"""
        return self.prep_time + (self.cook_time or 0)

    @property
    def rating_count(self):
        return self.ratings.count()

    def total_interactions(self):
        """'total likes + bookmarks + ratings + comments"""
        return (
            self.likes.count()
            + self.bookmarks.count()
            + self.ratings.count()
            + self.comments.count()
        )

    def trending_score(self, days=7):
        """Calculate trending score based on recent activity.

        Args:
            days: Number of past days to consider (default 7).
        """
        since = timezone.now() - timedelta(days=days)
        recent_likes = self.likes.filter(created_at__gte=since).count()
        recent_bookmarks = self.bookmarks.filter(created_at__gte=since).count()
        recent_ratings = self.ratings.filter(created_at__gte=since).count()
        recent_comments = self.comments.filter(created_at__gte=since).count()

        score = (
            (recent_likes * 5)
            + (recent_bookmarks * 2)
            + (recent_ratings * 4)
            + (recent_comments * 1)
        )

        return score

    class Meta:
        ordering = ["-created_at"]

    def get_similar_recipes(self, limit=5):
        """Find similar recipes based on category and shared ingredients"""

        similar = Recipe.objects.filter(is_published=True).exclude(id=self.id)

        if self.category:
            same_category = similar.filter(category=self.category)
            if same_category.exists():
                return same_category[:limit]

        my_ingredients = set(self.ingredients.values_list("name", flat=True))

        scored_recipes = []
        for recipe in similar:
            their_ingredients = set(recipe.ingredients.values_list("name", flat=True))
            overlap = len(my_ingredients.intersection(their_ingredients))
            if overlap > 0:
                scored_recipes.append((recipe, overlap))

        scored_recipes.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in scored_recipes[:limit]]


class RecipeImage(models.Model):
    """Multiple images for a recipe"""

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="recipes/images/")
    is_featured = models.BooleanField(default=False)
    caption = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]
        app_label = "recipes"

    def __str__(self):
        return f"Image for {self.recipe.title}"


class Ingredient(models.Model):
    """Dynamic ingredients for a recipe"""

    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="ingredients"
    )
    name = models.CharField(max_length=200)
    quantity = models.CharField(max_length=100, blank=True)
    unit = models.CharField(max_length=50, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]
        app_label = "recipes"

    def __str__(self):
        return f"{self.quantity} {self.unit} {self.name}".strip()


class Step(models.Model):
    """Dynamic cooking steps for a recipe"""

    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="steps")
    step_number = models.IntegerField()
    description = models.TextField()
    image = models.ImageField(upload_to="steps/", blank=True, null=True)

    class Meta:
        ordering = ["step_number"]
        app_label = "recipes"

    def __str__(self):
        return f"Step {self.step_number}"


class Comment(models.Model):
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="comments"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # auto_now updates on every save

    class Meta:
        ordering = ["-created_at"]
        app_label = "recipes"

    def __str__(self):
        return f"Comment by {self.user.username} on {self.recipe.title}"


# Like model to track user likes on recipes
class Like(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["recipe", "user"]  # one like per user per recipe
        app_label = "recipes"

    def __str__(self):
        return f"{self.user.username} likes {self.recipe.title}"  # Add user field to Like model


class Bookmark(models.Model):
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="bookmarks"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["recipe", "user"]  # one bookmark per user per recipe
        app_label = "recipes"

    def __str__(self):
        return f"{self.user.username} bookmarked {self.recipe.title}"


class Rating(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name="ratings")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    value = models.IntegerField(
        choices=[(i, i) for i in range(1, 6)]
    )  # rating value (e.g., 1-5)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        from django.core.exceptions import ValidationError

        if int(self.value) < 1 or int(self.value) > 5:
            raise ValidationError("Rating must be between 1 and 5")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ["recipe", "user"]  # one rating per user per recipe
        app_label = "recipes"

    def __str__(self):
        return f"{self.user.username} rated {self.recipe.title}: {self.value}*"


class Collection(models.Model):
    """a collection of recipes created by a user"""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="collections"
    )
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["name", "creator"]
        ordering = ["-created_at"]
        app_label = "recipes"

    def __str__(self):
        return f"{self.name} by {self.creator.username}"

    @property
    def recipe_count(self):
        return self.items.count()


class CollectionItem(models.Model):
    """collection of recipes"""

    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name="items"
    )
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name="collection_items"
    )
    added_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ["collection", "recipe"]
        ordering = ["-added_at"]
        app_label = "recipes"

    def __str__(self):
        return f"{self.recipe.title} in {self.collection.name}"
