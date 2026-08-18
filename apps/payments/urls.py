from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('checkout/<int:recipe_id>/', views.checkout, name='checkout'),
    path('webhook/', views.chapa_webhook, name='webhook'),
    path('success/', views.payment_success, name='success'),
    path('cancel/', views.payment_cancel, name='cancel'),
]
