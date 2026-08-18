from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import get_user_model
from django.views.generic import DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from .models import CustomUser
from notifications.models import Activity
from django.contrib import messages
from .models import Follow


from django.db.models import Count

User = get_user_model()


class ProfileView(DetailView):
    """public profile page for any user
    shows their recipes and basic info"""

    model = User
    template_name = "accounts/profile.html"
    context_object_name = "profile_user"  # the user whose profile is being viewed
    slug_field = "username"  # use username in url
    slug_url_kwarg = "username"  # url: /profile/<username>/

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        # get user's published recipes
        context["recipes"] = user.recipes.filter(is_published=True)
        # get user stat
        context["total_recipes"] = user.recipes.count()
        context["total_likes_received"] = (
            user.recipes.aggregate(total=Count("likes"))["total"] or 0
        )

        context["followers_count"] = Follow.objects.filter(followed=user).count()
        context["following_count"] = Follow.objects.filter(follower=user).count()

        if self.request.user.is_authenticated:
            context["is_following"] = Follow.objects.filter(
                follower=self.request.user, followed=user
            ).exists()

        # Get user's recent activity (public)
        context["activities"] = (
            Activity.objects.filter(actor=user)
            .exclude(verb="follow")  # Keep follows private
            .select_related("target_content_type")[:20]
        )
        return context


class DashboardView(LoginRequiredMixin, UpdateView):
    """private dashboard for logged in user to edit their profile"""

    model = User
    template_name = "accounts/dashboard.html"
    fields = [
        "username",
        "email",
        "first_name",
        "last_name",
        "bio",
        "profile_picture",
        "website",
    ]
    success_url = reverse_lazy("accounts:dashboard")

    def get_object(self):
        return self.request.user  # only allow editing own profile

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.get_object()
        # get user's published recipes
        context["my_recipes"] = (
            user.recipes.all()
        )  # show all recipes, not just published
        # get user's bookmarked recipes
        context["bookmarks"] = user.bookmark_set.all().select_related(
            "recipe"
        )  # optimize query to get recipe data

        # user recent activity - last 5 recipes created or updated
        context["recent_comments"] = user.comment_set.all()[:5]

        return context


@login_required
def toggle_follow(request, username):
    """
    follow or unfollow a user
    """
    followed_user = get_object_or_404(User, username=username)

    if request.user == followed_user:
        messages.error(request, "You cannot follow yourself.")
        return redirect("accounts:profile", username=username)

    follow = Follow.objects.filter(follower=request.user, followed=followed_user)

    if follow.exists():
        follow.delete()
        messages.success(request, f"You have unfollowed {followed_user.username}.")
    else:
        Follow.objects.create(follower=request.user, followed=followed_user)

        Activity.objects.create(
            actor=request.user,
            verb="follow",
            target=followed_user,
            recipient=followed_user,
        )

        messages.success(request, f"You are now following {followed_user.username}.")
    return redirect("accounts:profile", username=username)
