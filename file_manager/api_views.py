from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Tool, Note, Project
from .serializers import ToolSerializer, NoteSerializer, ProjectSerializer


class _OwnedByUserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.model.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ToolViewSet(_OwnedByUserViewSet):
    queryset = Tool.objects.all()
    serializer_class = ToolSerializer


class NoteViewSet(_OwnedByUserViewSet):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer


class ProjectViewSet(_OwnedByUserViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
