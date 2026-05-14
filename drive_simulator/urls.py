from django.contrib import admin
from django.urls import path, include
from file_manager.views import handler404, handler500, login_view, logout_view  # Apenas estas importações
from django.conf.urls.static import static
from django.conf import settings
from django.views.static import serve
from django.urls import re_path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('GDriver/', include('file_manager.urls')),
    path('', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('api/', include('file_manager.api_urls')),
    path('ai_assistant/', include('ai_assistant.urls')),
    path('binary_analyzer/', include('binary_analyzer.urls', namespace='binary_analyzer')),
    path('test-404/', handler404),
    path('test-500/', handler500),
]

# REMOVA completamente estas linhas ↓
# urlpatterns += [
#     path('<path:undefined_path>/', handler_404, name='handler_404'),
# ]

# CORRIJA os handlers - use os nomes corretos (sem underline)
handler404 = 'file_manager.views.handler404'  # SEM underline
handler500 = 'file_manager.views.handler500'  # SEM underline

# Serve media files always (mesmo com DEBUG=False, pois é servidor interno)
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]