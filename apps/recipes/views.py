from django.shortcuts import render, get_object_or_404
from django.conf import settings

from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)
from .models import (
    Recipe,
    Ingredient,
    Step,
    RecipeImage,
    Category,
    Like,
    Comment,
    Bookmark,
    Rating,
    Collection,
    CollectionItem,
)

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from .forms import RecipeForm, IngredientForm, StepForm
from django.forms import inlineformset_factory


from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from .models import Like, Comment
from django.contrib import messages

from django.db.models import Q, Count
from datetime import timedelta
from django.utils import timezone


from django.contrib.contenttypes.models import ContentType
from notifications.models import Activity


from django.views.generic.edit import UpdateView, DeleteView



class RecipeListView(ListView):
    model = Recipe
    template_name = "recipes/recipe_list.html"
    context_object_name = "recipes"
    ordering = "-created_at"
    paginate_by = 9

    def get_queryset(self):
        queryset = Recipe.objects.filter(is_published=True)

        # filter by category if selected
        # search by title
        search_query = self.request.GET.get("search", "")
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query)
                | Q(description__icontains=search_query)
            )
        # filter by category if selected
        category_slug = self.request.GET.get("category")
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        # filter by prep time(max minutes)
        max_time = self.request.GET.get("max_time")
        if max_time:
            queryset = queryset.filter(prep_time__lte=max_time)

        # filter by ingredient
        ingredient = self.request.GET.get("ingredient")
        if ingredient:
            queryset = queryset.filter(
                ingredients__name__icontains=ingredient
            ).distinct()

        return queryset.select_related('creator', 'category')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.all()

        # pass search parameters to template for pagination links
        context["search_query"] = self.request.GET.get("search", "")
        context["selected_category"] = self.request.GET.get("category", "")
        context["max_time"] = self.request.GET.get("max_time", "")
        context["ingredient"] = self.request.GET.get("ingredient", "")

        context["cloud_name"] = settings.CLOUDINARY_STORAGE["CLOUD_NAME"]

        return context


from payments.models import Purchase


class RecipeDetailView(DetailView):
    model = Recipe
    template_name = "recipes/recipe_detail.html"
    context_object_name = "recipe"

    def get_queryset(self):
        return Recipe.objects.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipe = self.get_object()

        # user interactions status

        if self.request.user.is_authenticated:
            context["user_liked"] = recipe.likes.filter(user=self.request.user).exists()
            context["user_bookmarked"] = recipe.bookmarks.filter(
                user=self.request.user
            ).exists()
            context["user_rating"] = recipe.ratings.filter(
                user=self.request.user
            ).first()
        else:
            context["user_liked"] = False
            context["user_bookmarked"] = False
            context["user_rating"] = None

        # Premium Paywall Access Control
        has_access = True
        if recipe.is_premium:
            if self.request.user.is_authenticated:
                if self.request.user == recipe.creator or self.request.user.id == recipe.creator_id:
                    has_access = True
                else:
                    has_access = Purchase.objects.filter(
                        user=self.request.user, recipe=recipe, status=Purchase.STATUS_COMPLETED
                    ).exists()
            else:
                has_access = False

        context["has_access"] = has_access

        context["cloud_name"] = settings.CLOUDINARY_STORAGE["CLOUD_NAME"]

        # Add this similar recipes
        context["similar_recipes"] = recipe.get_similar_recipes()

        return context


class RecipeCreateView(LoginRequiredMixin, CreateView):
    model = Recipe
    fields = [
        "title",
        "description",
        "category",
        "prep_time",
        "cook_time",
        "servings",
        "is_premium",
        "price",
        "featured_image",
    ]
    template_name = "recipes/recipe_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Create formsets
        IngredientFormSet = inlineformset_factory(
            Recipe,
            Ingredient,
            fields=["name", "quantity", "unit"],
            extra=3,
            can_delete=True,
        )

        StepFormSet = inlineformset_factory(
            Recipe,
            Step,
            fields=["step_number", "description"],
            extra=3,
            can_delete=True,
        )

        if self.request.POST:
            context["ingredient_formset"] = IngredientFormSet(
                self.request.POST, instance=self.object, prefix="ingredients"
            )
            context["step_formset"] = StepFormSet(
                self.request.POST, instance=self.object, prefix="steps"
            )
        else:
            context["ingredient_formset"] = IngredientFormSet(
                instance=self.object, prefix="ingredients"
            )
            context["step_formset"] = StepFormSet(
                instance=self.object, prefix="steps"
            )

        return context

    def form_valid(self, form):
        form.instance.creator = self.request.user
        context = self.get_context_data()
        ingredient_formset = context["ingredient_formset"]
        step_formset = context["step_formset"]

        if ingredient_formset.is_valid() and step_formset.is_valid():
            self.object = form.save()
            ingredient_formset.instance = self.object
            step_formset.instance = self.object
            ingredient_formset.save()
            step_formset.save()
            Activity.objects.create(
                actor=self.request.user,
                verb="create",
                target=self.object,
                recipient=None,  # Public creation, no specific recipient
            )
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("recipes:recipe_list")



@login_required
def add_comment(request, recipe_id):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    content = request.POST.get("content", "").strip()

    if not content:
        messages.error(request, "Comment cannot be empty.")
    elif len(content) > 2000:
        messages.error(request, "Comment is too long (max 2000 characters).")
    else:
        comment = Comment.objects.create(
            recipe=recipe, user=request.user, content=content
        )
        # CREATE ACTIVITY
        Activity.objects.create(
            actor=request.user,
            verb="comment",
            target=comment,  # Point to the comment itself
            recipient=recipe.creator,  # Notify recipe owner
        )

    return redirect("recipes:recipe_detail", slug=recipe.slug)


@login_required
def toggle_bookmark(request, recipe_id):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    bookmark = Bookmark.objects.filter(recipe=recipe, user=request.user)

    if bookmark.exists():
        bookmark.delete()
    else:
        Bookmark.objects.create(recipe=recipe, user=request.user)

    return redirect("recipes:recipe_detail", slug=recipe.slug)


# Rating view to handle user ratings on recipes
@login_required
def rate_recipe(request, recipe_id):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    value = request.POST.get("value")

    if value:
        try:
            # Convert to integer
            value = int(value)

            # Validate range
            if 1 <= value <= 5:
                rating, created = Rating.objects.update_or_create(
                    recipe=recipe, user=request.user, defaults={"value": value}
                )

                # Optional: Add success message
                messages.success(request, f"Rating updated to {value}★")
            else:
                messages.error(request, "Rating must be between 1 and 5")

        except (ValueError, TypeError):
            messages.error(request, "Invalid rating value")
    else:
        messages.error(request, "No rating value provided")

    return redirect("recipes:recipe_detail", slug=recipe.slug)


class BookmarkListView(LoginRequiredMixin, ListView):
    model = Bookmark
    template_name = "recipes/bookmarks.html"
    context_object_name = "bookmarks"

    def get_queryset(self):
        return Bookmark.objects.filter(user=self.request.user).select_related("recipe")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recipes"] = [bookmark.recipe for bookmark in context["bookmarks"]]
        return context


@login_required
def toggle_like(request, recipe_id):
    recipe = get_object_or_404(Recipe, id=recipe_id)
    like = Like.objects.filter(recipe=recipe, user=request.user)
    if like.exists():
        like.delete()

        Activity.objects.filter(
            target_content_type=ContentType.objects.get_for_model(recipe),
            target_object_id=recipe.id,
            actor=request.user,
            verb="like",
        ).delete()
    else:
        Like.objects.create(recipe=recipe, user=request.user)

        Activity.objects.create(
            actor=request.user, verb="like", target=recipe, recipient=recipe.creator
        )

    return redirect("recipes:recipe_detail", slug=recipe.slug)


class RecipeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """View to handle updating a recipe. Only the creator can update."""

    model = Recipe
    fields = [
        "title",
        "description",
        "category",
        "prep_time",
        "cook_time",
        "servings",
        "is_premium",
        "price",
        "featured_image",
    ]
    template_name = "recipes/recipe_form.html"

    def test_func(self):
        """check if the logged in user is the creator of the recipe"""
        recipe = self.get_object()
        return self.request.user == recipe.creator

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipe = self.get_object()

        IngredientFormSet = inlineformset_factory(
            Recipe,
            Ingredient,
            fields=["name", "quantity", "unit"],
            extra=1,
            can_delete=True,
        )
        StepFormSet = inlineformset_factory(
            Recipe,
            Step,
            fields=["step_number", "description"],
            extra=1,
            can_delete=True,
        )

        if self.request.POST:
            context["ingredient_formset"] = IngredientFormSet(
                self.request.POST, instance=recipe, prefix="ingredients"
            )
            context["step_formset"] = StepFormSet(
                self.request.POST, instance=recipe, prefix="steps"
            )
        else:
            context["ingredient_formset"] = IngredientFormSet(
                instance=recipe, prefix="ingredients"
            )
            context["step_formset"] = StepFormSet(
                instance=recipe, prefix="steps"
            )

        return context

    def form_valid(self, form):
        context = self.get_context_data()
        ingredient_formset = context["ingredient_formset"]
        step_formset = context["step_formset"]

        if ingredient_formset.is_valid() and step_formset.is_valid():
            self.object = form.save()
            ingredient_formset.instance = self.object
            step_formset.instance = self.object
            ingredient_formset.save()
            step_formset.save()
            return super().form_valid(form)
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse_lazy("recipes:recipe_detail", kwargs={"slug": self.object.slug})


class RecipeDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """View to handle deleting a recipe. Only the creator can delete."""

    model = Recipe
    template_name = "recipes/recipe_confirm_delete.html"
    success_url = reverse_lazy("recipes:recipe_list")

    def test_func(self):
        """check if the logged in user is the creator of the recipe"""
        recipe = self.get_object()
        return self.request.user == recipe.creator

    def delete(self, request, *args, **kwargs):
        """Override delete to also remove related activities"""
        self.object = self.get_object()
        recipe_id = self.object.id

        # Delete related activities
        Activity.objects.filter(
            target_content_type=ContentType.objects.get_for_model(self.object),
            target_object_id=recipe_id,
        ).delete()

        messages.success(
            request, "Recipe and all related activities have been deleted successfully."
        )
        return super().delete(request, *args, **kwargs)


class FollowingFeedView(LoginRequiredMixin, ListView):
    """Show recipes from users that the logged-in user is following"""

    model = Recipe
    template_name = "recipes/following_feed.html"
    context_object_name = "recipes"
    paginate_by = 9

    def get_queryset(self):
        following_users = self.request.user.following.all().values_list(
            "followed", flat=True
        )

        return Recipe.objects.filter(
            creator_id__in=following_users, is_published=True
        ).order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["feed_type"] = "following"
        return context


class CollectionListView(ListView):
    """View to list all collections, with option to filter by user"""

    model = Collection
    template_name = "recipes/collection_list.html"
    context_object_name = "collections"
    paginate_by = 12

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.GET.get("mine"):
            return Collection.objects.filter(creator=self.request.user)
        return Collection.objects.filter(is_public=True)


class CollectionDetailView(DetailView):
    """View to show details of a collection, including its recipes"""

    model = Collection
    template_name = "recipes/collection_detail.html"
    context_object_name = "collection"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        collection = self.get_object()

        if self.request.user.is_authenticated:
            user_collection = Collection.objects.filter(
                creator=self.request.user
            ).exclude(id=collection.id)
            context["user_collections"] = user_collection

        return context


class CollectionCreateView(LoginRequiredMixin, CreateView):
    """create a new collection"""

    model = Collection
    fields = ["name", "description", "is_public"]
    template_name = "recipes/collection_form.html"

    def form_valid(self, form):
        form.instance.creator = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("recipes:collection_detail", kwargs={"pk": self.object.pk})



class CollectionUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """edit a collection"""

    model = Collection
    fields = ["name", "description", "is_public"]
    template_name = "recipes/collection_form.html"

    def test_func(self):
        collection = self.get_object()
        return self.request.user == collection.creator

    def get_success_url(self):
        return reverse_lazy("recipes:collection_detail", kwargs={"pk": self.object.pk})


class CollectionDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """delete a collection"""

    model = Collection
    template_name = "recipes/collection_confirm_delete.html"
    success_url = reverse_lazy("recipes:collection_list")

    def test_func(self):
        collection = self.get_object()
        return self.request.user == collection.creator


@login_required
def add_to_collection(request, recipe_id):
    """Add a recipe to a collection"""

    recipe = get_object_or_404(Recipe, id=recipe_id)
    collection_id = request.POST.get("collection_id")

    if collection_id:
        collection = get_object_or_404(
            Collection, id=collection_id, creator=request.user
        )
        item, created = CollectionItem.objects.get_or_create(
            collection=collection, recipe=recipe
        )

        if created:
            messages.success(request, f'Added to collection "{collection.name}".')
        else:
            messages.info(request, f'"{collection.name}" already contains this recipe.')
    else:
        messages.error(request, "No collection selected.")

    return redirect("recipes:recipe_detail", slug=recipe.slug)


@login_required
def remove_from_collection(request, item_id):
    """Remove a recipe from a collection"""

    item = get_object_or_404(
        CollectionItem, id=item_id, collection__creator=request.user
    )
    collection = item.collection
    item.delete()
    messages.success(request, f'Removed from collection "{collection.name}".')

    return redirect("recipes:collection_detail", pk=collection.pk)


class RecommendedRecipesView(LoginRequiredMixin, ListView):
    "Personalized recipe recommendations based on user's collections and interactions"

    model = Recipe
    template_name = "recipes/recommended.html"
    context_object_name = "recipes"
    paginate_by = 12

    def get_queryset(self):
        user = self.request.user

        # Get user's interests
        interacted_recipes = Recipe.objects.filter(
            Q(likes__user=user) | Q(bookmarks__user=user) | Q(ratings__user=user)
        )

        favorite_categories = interacted_recipes.values_list(
            "category", flat=True
        ).distinct()

        # Store recommendations with reasons
        recommendations = []

        # Base recipes (exclude user's own)
        base_recipes = Recipe.objects.filter(is_published=True).exclude(creator=user)

        # Category-based recommendations
        if favorite_categories:
            valid_categories = [c for c in favorite_categories if c]
            if valid_categories:
                category_recipes = base_recipes.filter(category__in=valid_categories)
                for recipe in category_recipes:
                    category_name = (
                        recipe.category.name if recipe.category else "Unknown"
                    )
                    recommendations.append(
                        {
                            "recipe": recipe,
                            "reason": f"Because you like {category_name} recipes",
                            "priority": 1,
                        }
                    )

        # Popular recipes (fallback/add more)
        popular = base_recipes.annotate(
            interaction_count=Count("likes")
            + Count("bookmarks")
            + Count("ratings")
            + Count("comments")
        ).order_by("-interaction_count")[:20]

        for recipe in popular:
            # Check if already added
            if not any(r["recipe"].id == recipe.id for r in recommendations):
                recommendations.append(
                    {"recipe": recipe, "reason": "Popular this week", "priority": 2}
                )

        # Sort by priority, then by creation date
        recommendations.sort(
            key=lambda x: (x["priority"], -x["recipe"].created_at.timestamp())
        )

        # Store in session or cache for template
        self.recommendation_reasons = {
            r["recipe"].id: r["reason"] for r in recommendations
        }

        return [r["recipe"] for r in recommendations][:50]


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add reasons to context
        if hasattr(self, "recommendation_reasons"):
            context["recommendation_reasons"] = self.recommendation_reasons

        # Trending
        week_ago = timezone.now() - timedelta(days=7)
        trending = (
            Recipe.objects.filter(is_published=True, created_at__gte=week_ago)
            .annotate(
                recent_likes=Count("likes", filter=Q(likes__created_at__gte=week_ago))
            )
            .order_by("-recent_likes")[:5]
        )
        context["trending"] = trending
        return context
