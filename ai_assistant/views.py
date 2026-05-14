import json
import requests

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import sync_to_async

from .rag_qa import compose_prompt

from .models import Conversation, Message
from django.utils.timezone import now
from django.shortcuts import render
from django.shortcuts import get_object_or_404

from django.views.decorators.http import require_POST

from datetime import timedelta


OLLAMA_URL = getattr(settings, 'OLLAMA_API_URL', 'http://localhost:11434/api/generate')


def _ollama_base_url():
    """Deriva http://host:port a partir do OLLAMA_URL (tira /api/generate)."""
    url = OLLAMA_URL.rstrip('/')
    for suffix in ('/api/generate', '/api/chat'):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


@login_required
def ollama_tags(request):
    """Proxy GET para /api/tags do Ollama — lista de modelos instalados."""
    api_key = getattr(settings, 'OLLAMA_API_KEY', '') or ''
    headers = {}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    try:
        r = requests.get(f'{_ollama_base_url()}/api/tags', headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json() or {}
        models = []
        for m in (data.get('models') or []):
            name = m.get('name') or m.get('model') or ''
            if name:
                models.append(name)
        return JsonResponse({'models': models})
    except requests.HTTPError as e:
        return JsonResponse({'error': f'HTTP {e.response.status_code}', 'models': []}, status=502)
    except Exception as e:
        return JsonResponse({'error': str(e), 'models': []}, status=502)


async def _maybe_update_title(conversation, question: str, model: str):
    """Set title from 1st message; AI-generate title after 5th message."""
    try:
        user_count = await sync_to_async(
            Message.objects.filter(conversation=conversation, sender='user').count
        )()

        if user_count == 1:
            title = question[:70].strip()
            if len(question) > 70:
                title += '…'
            conversation.title = title
            await sync_to_async(conversation.save)()

        elif user_count == 5:
            msgs = await sync_to_async(list)(
                Message.objects.filter(
                    conversation=conversation, sender='user'
                ).order_by('created_at').values_list('content', flat=True)[:5]
            )
            questions_text = "\n".join(f"- {q[:150]}" for q in msgs)
            title_prompt = (
                "Crie um título curto (máximo 55 caracteres) que resume o tema desta conversa "
                "baseado nas perguntas abaixo. Responda APENAS com o título, sem aspas nem explicação.\n\n"
                f"Perguntas:\n{questions_text}"
            )

            api_key = getattr(settings, 'OLLAMA_API_KEY', '') or ''
            headers = {'Content-Type': 'application/json'}
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'

            def call_ollama_title():
                r = requests.post(
                    OLLAMA_URL,
                    json={'model': model, 'prompt': title_prompt, 'stream': False,
                          'options': {'num_predict': 25}},
                    headers=headers,
                    timeout=30,
                )
                r.raise_for_status()
                return r.json().get('response', '').strip()

            title = await sync_to_async(call_ollama_title)()
            if title:
                conversation.title = title[:80]
                await sync_to_async(conversation.save)()
    except Exception:
        pass


def iter_ollama_stream(payload: dict, timeout: int = 300):
    """Yield text chunks from Ollama API streaming response."""
    api_key = getattr(settings, 'OLLAMA_API_KEY', '') or ''
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    model_name = (payload or {}).get('model') or '?'
    try:
        with requests.post(OLLAMA_URL, json=payload, headers=headers, stream=True, timeout=timeout) as r:
            if r.status_code == 404:
                try:
                    body = r.json()
                    msg = body.get('error') or str(body)
                except Exception:
                    msg = r.text[:200] if r.text else 'model not found'
                yield (
                    f"[error] Modelo '{model_name}' não encontrado no Ollama ({msg}). "
                    f"Rode no terminal: `ollama pull {model_name}` — "
                    f"ou use /models no terminal p/ ver os instalados e /model <nome> para trocar."
                )
                return
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    yield line
                    continue
                if isinstance(data, dict) and 'response' in data:
                    yield data['response']
                else:
                    yield json.dumps(data)
    except requests.ConnectionError:
        yield (
            f"[error] não foi possível conectar ao Ollama em {OLLAMA_URL}. "
            f"Verifique se o serviço está em execução (`ollama serve`)."
        )
    except Exception as e:
        yield f"[error] {str(e)}"


def _resolve_conversation_sync(user, conversation_id, force_new, mode):
    """Resolve qual Conversation usar — chamada sync, agrupa todas as queries do ORM."""
    title_prefix = 'Terminal' if mode == Conversation.MODE_TERMINAL else 'Conversa'
    new_title = f"{title_prefix} iniciada em {now().strftime('%d/%m/%Y %H:%M')}"

    if force_new:
        return Conversation.objects.create(user=user, mode=mode, title=new_title)

    conversation = None
    if conversation_id:
        try:
            conversation = Conversation.objects.get(
                pk=int(conversation_id), user=user, is_deleted=False
            )
        except Conversation.DoesNotExist:
            conversation = None
        except Exception:
            conversation = None

    if not conversation:
        conversation = Conversation.objects.filter(
            user=user,
            mode=mode,
            created_at__gte=now() - timedelta(hours=24),
            is_deleted=False,
        ).order_by('-created_at').first()

    if not conversation:
        conversation = Conversation.objects.create(user=user, mode=mode, title=new_title)
    return conversation


async def _resolve_conversation(user, conversation_id, force_new, mode):
    return await sync_to_async(_resolve_conversation_sync)(user, conversation_id, force_new, mode)


@sync_to_async
def _resolve_user(request):
    """Avalia o SimpleLazyObject do AuthMiddleware fora do contexto async."""
    u = request.user
    # acesso a um atributo força o resolve
    _ = u.pk
    return u


@csrf_exempt
@login_required
async def chat_stream(request):
    """POST endpoint to accept a 'prompt' and stream response back to the browser."""
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'error': 'invalid json'}, status=400)

    question        = payload.get('prompt') or payload.get('question') or ''
    attachment_text = payload.get('attachment_text') or ''
    conversation_id = payload.get('conversation_id')
    force_new       = payload.get('force_new', False)
    default_model   = getattr(settings, 'OLLAMA_DEFAULT_MODEL', 'llama3.2')
    model           = payload.get('model', default_model)

    user = await _resolve_user(request)

    try:
        prompt_text = await sync_to_async(compose_prompt)(user, question, attachment_text=attachment_text)
    except Exception:
        prompt_text = question

    ollama_payload = {
        'model': model,
        'prompt': prompt_text,
        'stream': True,
        'options': {
            'num_ctx':     int(getattr(settings, 'OLLAMA_NUM_CTX', 4096)),
            'num_predict': int(getattr(settings, 'OLLAMA_NUM_PREDICT', 2048)),
            'num_thread':  int(getattr(settings, 'OLLAMA_NUM_THREAD', 0)),
        }
    }
    system_prompt = getattr(settings, 'OLLAMA_SYSTEM_PROMPT', '').strip()
    if system_prompt:
        ollama_payload['system'] = system_prompt

    conversation = await _resolve_conversation(
        user, conversation_id, force_new, Conversation.MODE_CHAT
    )

    await sync_to_async(Message.objects.create)(
        conversation=conversation, sender='user', content=question
    )

    assistant_response_parts = []

    def generator():
        # Tag de abertura visível p/ o frontend; o prompt já termina em <pensando>.
        yield '<pensando>'
        for chunk in iter_ollama_stream(ollama_payload):
            assistant_response_parts.append(chunk)
            yield chunk

    async def async_wrapped_generator():
        for chunk in generator():
            yield chunk
        full_response = ''.join(assistant_response_parts)
        if not full_response.startswith('<pensando>'):
            full_response = '<pensando>' + full_response
        await sync_to_async(Message.objects.create)(
            conversation=conversation,
            sender='assistant',
            content=full_response,
        )
        await _maybe_update_title(conversation, question, model)

    return StreamingHttpResponse(async_wrapped_generator(), content_type='text/plain')


@csrf_exempt
@login_required
async def terminal_stream(request):
    """POST endpoint do MODO TERMINAL — Ollama direto, sem RAG, com histórico persistido."""
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'error': 'invalid json'}, status=400)

    question        = (payload.get('prompt') or '').strip()
    attachment_text = payload.get('attachment_text') or ''
    attachment_name = (payload.get('attachment_name') or '').strip()
    conversation_id = payload.get('conversation_id')
    force_new       = bool(payload.get('force_new', False))
    default_model   = getattr(settings, 'OLLAMA_DEFAULT_MODEL', 'llama3.2')
    model           = payload.get('model', default_model)

    if not question and not attachment_text:
        return JsonResponse({'error': 'empty prompt'}, status=400)

    MAX_ATTACH = 20000
    trimmed_note = ''
    if attachment_text and len(attachment_text) > MAX_ATTACH:
        attachment_text = attachment_text[:MAX_ATTACH]
        trimmed_note = '\n[AVISO] Arquivo truncado para caber no contexto.'

    sys_line = (
        "Você é um assistente em MODO TERMINAL. "
        "Responda de forma direta, objetiva e concisa, em texto plano. "
        "Evite introduções longas, emojis e markdown pesado. "
        "Seja técnico e factual."
    )

    if attachment_text:
        header = f"=== {attachment_name or 'arquivo_anexado'} ===\n" if attachment_name else ""
        prompt_text = (
            f"{sys_line}\n\n"
            f"Contexto do arquivo anexado:\n"
            f"{header}{attachment_text}{trimmed_note}\n\n"
            f"Pergunta do usuário: {question or '(descreva o arquivo acima)'}"
        )
    else:
        prompt_text = f"{sys_line}\n\nPergunta: {question}"

    ollama_payload = {
        'model': model,
        'prompt': prompt_text,
        'stream': True,
        'options': {
            'num_ctx':     int(getattr(settings, 'OLLAMA_NUM_CTX', 4096)),
            'num_predict': int(getattr(settings, 'OLLAMA_TERM_NUM_PREDICT', 1024)),
            'num_thread':  int(getattr(settings, 'OLLAMA_NUM_THREAD', 0)),
        }
    }

    user = await _resolve_user(request)
    conversation = await _resolve_conversation(
        user, conversation_id, force_new, Conversation.MODE_TERMINAL
    )

    user_content = question or f"[anexo: {attachment_name}]"
    await sync_to_async(Message.objects.create)(
        conversation=conversation, sender='user', content=user_content
    )

    assistant_parts = []

    def sync_generator():
        for chunk in iter_ollama_stream(ollama_payload):
            assistant_parts.append(chunk)
            yield chunk

    async def async_gen():
        for c in sync_generator():
            yield c
        full = ''.join(assistant_parts)
        await sync_to_async(Message.objects.create)(
            conversation=conversation, sender='assistant', content=full,
        )
        await _maybe_update_title(conversation, question or attachment_name, model)

    response = StreamingHttpResponse(async_gen(), content_type='text/plain')
    response['X-Conversation-Id'] = str(conversation.id)
    return response


@login_required
def conversation_list(request):
    mode = request.GET.get('mode')
    qs = Conversation.objects.filter(user=request.user, is_deleted=False)
    if mode in (Conversation.MODE_CHAT, Conversation.MODE_TERMINAL):
        qs = qs.filter(mode=mode)
    return render(request, 'conversation_list.html', {'conversations': qs.order_by('-updated_at')})


@login_required
def conversation_detail(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, user=request.user)
    messages = conv.messages.order_by('created_at')
    return render(request, 'conversation_detail.html', {'conversation': conv, 'messages': messages})


@require_POST
@login_required
def delete_conversation(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, user=request.user)
    conv.is_deleted = True
    conv.save()
    return JsonResponse({'success': True})


@require_POST
@login_required
def end_current_conversation(request):
    mode = request.POST.get('mode') or request.GET.get('mode') or Conversation.MODE_CHAT
    if mode not in (Conversation.MODE_CHAT, Conversation.MODE_TERMINAL):
        mode = Conversation.MODE_CHAT
    recent_convs = Conversation.objects.filter(
        user=request.user,
        mode=mode,
        created_at__gte=now() - timedelta(hours=24),
        is_deleted=False
    ).order_by('-created_at')

    if recent_convs.exists():
        conv = recent_convs.first()
        conv.is_deleted = True
        conv.save()

    return JsonResponse({'success': True})


@login_required
def conversation_detail_ajax(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, user=request.user)
    messages = conv.messages.order_by('created_at')
    return render(request, 'ai_assistant/partials/conversation_detail_body.html', {
        'conversation': conv,
        'messages': messages
    })


@login_required
def conversation_messages_api(request, pk):
    """Returns all messages of a specific conversation so the widget can load it."""
    conv = get_object_or_404(Conversation, pk=pk, user=request.user, is_deleted=False)
    messages = [
        {'sender': m.sender, 'content': m.content}
        for m in conv.messages.order_by('created_at')
    ]
    return JsonResponse({
        'messages': messages,
        'title': conv.title or '',
        'id': conv.id,
        'mode': conv.mode,
    })


@login_required
def conversations_api(request):
    """JSON list of conversations for the history panel.

    Aceita ?mode=chat|terminal para filtrar por tipo de conversa.
    """
    mode = request.GET.get('mode')
    qs = Conversation.objects.filter(user=request.user, is_deleted=False)
    if mode in (Conversation.MODE_CHAT, Conversation.MODE_TERMINAL):
        qs = qs.filter(mode=mode)
    convs = qs.order_by('-updated_at')[:30]

    result = []
    for c in convs:
        msg_count = c.messages.count()
        last = c.messages.order_by('-created_at').first()
        result.append({
            'id': c.id,
            'title': c.title or 'Conversa sem título',
            'updated_at': c.updated_at.strftime('%d/%m %H:%M'),
            'message_count': msg_count,
            'preview': (last.content[:90] if last else ''),
            'mode': c.mode,
            'url': f'/ai_assistant/conversa/{c.id}/ajax/',
        })
    return JsonResponse({'conversations': result})


@login_required
def current_messages_api(request):
    """Returns messages of the active conversation (last 24 h) for widget restore.

    Aceita ?mode=chat|terminal para escolher qual conversa restaurar.
    """
    mode = request.GET.get('mode')
    if mode not in (Conversation.MODE_CHAT, Conversation.MODE_TERMINAL):
        mode = Conversation.MODE_CHAT

    conv = Conversation.objects.filter(
        user=request.user,
        mode=mode,
        created_at__gte=now() - timedelta(hours=24),
        is_deleted=False,
    ).order_by('-created_at').first()
    if not conv:
        return JsonResponse({'messages': [], 'title': '', 'mode': mode})
    messages = [
        {'sender': m.sender, 'content': m.content}
        for m in conv.messages.order_by('created_at')
    ]
    return JsonResponse({
        'messages': messages,
        'title': conv.title or '',
        'id': conv.id,
        'mode': conv.mode,
    })


@require_POST
@login_required
def create_note_from_ai(request):
    """Create a Note from data collected by the AI assistant."""
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'invalid json'}, status=400)

    title   = (data.get('title') or 'Nota sem título').strip()[:255]
    content = (data.get('content') or '').strip()
    folder_name = (data.get('folder_name') or '').strip()

    from file_manager.models import Note, Folder as FolderModel
    folder = None
    if folder_name:
        folder = FolderModel.objects.filter(user=request.user, name__iexact=folder_name).first()

    note = Note.objects.create(user=request.user, title=title, content=content, folder=folder)
    return JsonResponse({
        'success': True,
        'note_id': note.id,
        'url': f'/GDriver/notes/edit/{note.id}/',
        'title': note.title,
    })
