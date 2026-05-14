"""Context processors do ai_assistant.

Expõem variáveis do settings para os templates (ex.: modelo Ollama
ativo), para que o widget JS possa inicializar `window.__AI_OLLAMA_MODEL`
corretamente.
"""
from django.conf import settings


def ollama_settings(request):
    """Injeta OLLAMA_DEFAULT_MODEL no contexto do template."""
    return {
        'OLLAMA_DEFAULT_MODEL': getattr(settings, 'OLLAMA_DEFAULT_MODEL', '') or '',
    }
