from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.views import custom_404_view, custom_500_view



urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),  # For django-allauth
    path("accounts/", include("accounts.urls")),
    path("__debug__/", include("debug_toolbar.urls")),
    path("", include("core.urls")),  # We'll add core and recipes URLs later
    path("recipes/", include("recipes.urls")),
    path("notifications/", include("notifications.urls")),
    path("payments/", include("payments.urls")),  # Add this line for payments app
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# custom error handlers
handler404 = "core.views.custom_404_view"
handler500 = "core.views.custom_500_view"
handler403 = "core.views.ratelimit_exceeded"  # Custom handler for rate limit exceeded
