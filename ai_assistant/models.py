from django.db import models
from django.conf import settings


class Conversation(models.Model):
    MODE_CHAT     = 'chat'
    MODE_TERMINAL = 'terminal'
    MODE_CHOICES = (
        (MODE_CHAT,     'Chat'),
        (MODE_TERMINAL, 'Terminal'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=255, blank=True)
    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default=MODE_CHAT, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return f"Conversation #{self.id} ({self.user}) [{self.mode}] - {self.title}"


class Message(models.Model):
    SENDER_CHOICES = (
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    )
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=20, choices=SENDER_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender}: {self.content[:50]}"
