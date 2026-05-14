from django.urls import re_path
from . import terminal_consumer

websocket_urlpatterns = [
    re_path(r'ws/terminal/(?P<project_id>\d+)/$', terminal_consumer.TerminalConsumer.as_asgi()),
]
