from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.conf import settings
from .models import Comment

@receiver(post_save, sender=Comment)
def send_admin_notification_on_comment(sender, instance, created, **kwargs):
    if created:
        subject = "New Comment Posted"
        message = f"User {instance.user.email} commented on {instance.recipe.title}: {instance.content}"
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [settings.ADMIN_EMAIL],
            fail_silently=True,
        )
