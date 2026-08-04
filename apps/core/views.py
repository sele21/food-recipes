from django.views.generic import TemplateView
from recipes.models import Recipe, Category
from django.contrib.auth import get_user_model, models
from django.shortcuts import render

User = get_user_model()

class HomeView(TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Statistics
        try:
            context['recipe_count'] = Recipe.objects.filter(is_published=True).count()
        except Exception:
            context['recipe_count'] = 0

        try:
            context['category_count'] = Category.objects.count()
        except Exception:
            context['category_count'] = 0

        try:
            context['featured_recipes'] = Recipe.objects.filter(is_published=True).order_by('-created_at')[:6]
        except Exception:
            context['featured_recipes'] = []

        try:

            context['categories'] = Category.objects.all()
        except Exception:
            context['categories'] = []
        try:
            context['user_count'] = User.objects.count()
        except Exception:
            context['user_count'] = 0

        try:
            context['like_count'] = Recipe.objects.filter(is_published=True).aggregate(total_likes=models.Sum('likes'))['total_likes'] or 0
        except Exception:
            context['like_count'] = 0


        return context


def custom_404_view(request, exception):
    """Custom 404 error handler that renders a user-friendly 404 page."""
    return render(request, '404.html', status=404)


def custom_500_view(request):
    """Custom 500 error handler that renders a user-friendly 500 page."""
    return render(request, '500.html', status=500)

def ratelimit_exceeded(request, exception):
    """Custom view for handling rate limit exceeded errors."""
    return render(request, 'rate_limit.html', status=429)

