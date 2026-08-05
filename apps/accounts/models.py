from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.conf import settings
from django.apps import AppConfig

# User = get_user_model()


class CustomUser(AbstractUser):
    """
    Custom user model that extends Django's built-in User.
    Email is required and unique.
    """

    email = models.EmailField(
        _("email address"),
        unique=True,
        blank=False,
        null=False,
        error_messages={
            "unique": _("A user with that email already exists."),
        },
    )

    # Additional fields can be added here as needed, for example:
    # New profile fields
    bio = models.TextField(
        _("bio"), max_length=500, blank=True
    )  # short biography or description of the user

    # profile picture field to allow users to upload a profile image
    profile_picture = models.ImageField(upload_to="profiles/", blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(
        auto_now_add=True
    )  # timestamp for when the user account was created
    updated_at = models.DateTimeField(
        auto_now=True
    )  # timestamp for when the user account

    def __str__(self):
        return self.username

    # helper method to count user's recipes
    def recipe_count(self):
        return self.recipes.count()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")


class Follow(models.Model):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="following"
    )
    followed = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="followers"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["follower", "followed"]
        ordering = ["-created_at"]

    def clean(self):
        if self.follower == self.followed:
            from django.core.exceptions import ValidationError

            raise ValidationError("You cannot follow yourself")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.follower.username} follows {self.followed.username}"

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'

    def ready(self):
        import apps.accounts.signals  
