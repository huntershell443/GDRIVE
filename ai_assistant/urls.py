from django.urls import path
from . import views

app_name = 'ai_assistant'

urlpatterns = [
    path('chat/', views.chat_stream, name='chat_stream'),
    path('terminal/', views.terminal_stream, name='terminal_stream'),
    path('api/ollama_tags/', views.ollama_tags, name='ollama_tags'),
    path('conversas/', views.conversation_list, name='conversation_list'),
    path('conversas/<int:pk>/', views.conversation_detail, name='conversation_detail'),
    path('conversas/<int:pk>/excluir/', views.delete_conversation, name='conversation_delete'),
    path('end_current/', views.end_current_conversation, name='end_current_conversation'),
    path('conversa/<int:pk>/ajax/', views.conversation_detail_ajax, name='conversation_detail_ajax'),
    # JSON APIs used by the chat widget
    path('api/conversations/', views.conversations_api, name='conversations_api'),
    path('api/current_messages/', views.current_messages_api, name='current_messages_api'),
    path('api/create_note/', views.create_note_from_ai, name='create_note_from_ai'),
    path('api/conversation/<int:pk>/messages/', views.conversation_messages_api, name='conversation_messages_api'),
]
