import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drive_simulator.settings')

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
import file_manager.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drive_simulator.settings')

application = ProtocolTypeRouter({
	"http": get_asgi_application(),
	"websocket": AuthMiddlewareStack(
		URLRouter(
			file_manager.routing.websocket_urlpatterns
		)
	),
})
