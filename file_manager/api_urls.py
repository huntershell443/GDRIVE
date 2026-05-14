from rest_framework import routers
from django.urls import path, include
from .api_views import ToolViewSet, NoteViewSet, ProjectViewSet

router = routers.DefaultRouter()
router.register(r'tools', ToolViewSet)
router.register(r'notes', NoteViewSet)
router.register(r'projects', ProjectViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
