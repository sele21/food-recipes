from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.views import custom_404_view, custom_500_view
from django_ratelimit.decorators import ratelimit
from allauth.account.views import LoginView, SignupView


ratelimited_login = ratelimit(key='ip', rate='5/m', block=True)(LoginView.as_view())
ratelimited_signup = ratelimit(key='ip', rate='5/m',block=True)(SignupView.as_view())

urlpatterns = [
    path('accounts/login/', ratelimited_login, name='account_login'),
    path('accounts/signup/', ratelimited_signup, name='account_signup'),


    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),  # For django-allauth
    path("accounts/", include("accounts.urls")),
    path("__debug__/", include("debug_toolbar.urls")),
    path("", include("core.urls")),  # We'll add core and recipes URLs later
    path("recipes/", include("recipes.urls")),
    path("notifications/", include("notifications.urls")),


]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# custom error handlers
handler404 = "core.views.custom_404_view"
handler500 = "core.views.custom_500_view"
