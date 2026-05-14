from typing import List, Optional
from django.utils.text import Truncator
from django.utils import timezone
import os
from file_manager.models import (
    Note, CVE, Dork, DorkNote,
    File, Folder, ResourceLink, Tool,
    ToolNote, Project, ProjectItem,
    YouTubeChannel, UserStorage
)

try:
    from binary_analyzer.models import BinaryAnalysis
    _BINARY_ANALYZER = True
except ImportError:
    _BINARY_ANALYZER = False

MAX_CONTEXT_CHARS = 18000  # Aumentado para modelos modernos (8k+ context)

PROMPT_TEMPLATE = """Você é o **Assistente de Segurança Pessoal** do usuário **{username}** no sistema **GDriver** — plataforma privada focada em pentest, segurança ofensiva e armazenamento de informações técnicas (CVEs, dorks, ferramentas, arquivos, notas, projetos e links).

Data/hora: {datetime}

═══ IDENTIDADE E COMPORTAMENTO ═══
- Você é especialista em segurança ofensiva/defensiva, pentest e hacking ético.
- "GDriver"/"GDrive"/"meu sistema"/"sistema" = GDriver, plataforma do usuário. NUNCA Google Drive.
- **OBRIGATÓRIO**: Sua resposta DEVE ser baseada nos DADOS DO SISTEMA fornecidos abaixo. Se os dados estão lá, USE-OS diretamente na resposta.
- PROIBIDO responder "não tenho acesso" ou "não posso ver" quando os dados já estão incluídos no contexto abaixo.
- Nunca exponha dados de outros usuários.
- Responda sempre em **Markdown** (listas, negrito, tabelas, blocos de código quando relevante).
- Para CVEs: inclua severidade, descrição e referências quando disponíveis.
- Para dorks: mostre a query completa e plataforma.
- Para ferramentas: inclua categoria e descrição.
- Para scripts/exploits: forneça o código e explique uso/riscos em seguida.

═══ RACIOCÍNIO VISÍVEL (OBRIGATÓRIO) ═══
Você DEVE seguir este formato exato:

1. Primeiro, escreva seu raciocínio dentro de <pensando> </pensando>
2. Depois, fora das tags, escreva sua resposta final em Markdown

Exemplo CORRETO:
<pensando>
O usuário perguntou sobre CVEs. Nos dados encontro: CVE-2024-12345 (crítica), CVE-2024-67890 (alta). Vou listar ambas com severidade e descrição.
</pensando>
Aqui estão as CVEs encontradas no seu sistema:
- **CVE-2024-12345** (Crítica): Buffer overflow no nginx...
- **CVE-2024-67890** (Alta): XSS no painel admin...

═══ CRIAÇÃO DE NOTA ═══
- Se o usuário pedir para criar/adicionar/salvar uma nota ou anotação:
  1. Faça perguntas para coletar: título, conteúdo principal, pasta (opcional).
  2. Quando tiver TODOS os dados necessários, inclua EXATAMENTE ao final da resposta FORA das tags:
     [CRIAR_NOTA:{{"title":"TITULO","content":"CONTEUDO","folder_name":"PASTA_OU_VAZIO"}}]
  3. Não invente dados — pergunte o que precisar.

═══ BUSCA DE ARQUIVOS ═══
- Cada arquivo nos dados abaixo inclui [link:URL].
- Ao localizar arquivos, exiba como: [nome do arquivo](URL)
- Liste TODOS os resultados relevantes com links clicáveis.

═══ DADOS DO SISTEMA (USE ESTES DADOS PARA RESPONDER) ═══
{contexts}
════════════════════════════════════════════════════════
{attachment_section}
Pergunta do usuário: {question}"""


def build_context_for_user(user, focus: Optional[str] = None) -> str:
    parts: List[str] = []
    focus = (focus or '').lower()

    def add(label: str, text: str):
        parts.append(f"[{label}] {text}")

    # Always prepend system description so the AI knows what GDriver is
    parts.append(get_system_description())

    # ── Focos específicos ─────────────────────────────────────────────────────

    if focus == 'dorks_shodan':
        for d in Dork.objects.filter(user=user, platform__iexact='Shodan').order_by('-created_at')[:60]:
            add("DORK/Shodan", f"{d.query}" + (f" — {d.description}" if d.description else ""))
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'dorks_google':
        for d in Dork.objects.filter(user=user, platform__iexact='Google').order_by('-created_at')[:60]:
            add("DORK/Google", f"{d.query}" + (f" — {d.description}" if d.description else ""))
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'dorks':
        for d in Dork.objects.filter(user=user).order_by('-created_at')[:60]:
            add(f"DORK/{d.platform}", f"{d.query}" + (f" — {d.description}" if d.description else ""))
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'cves':
        cves = list(CVE.objects.filter(user=user).order_by('-published_date')[:50])
        parts.append(f"## CVEs registradas no sistema ({len(cves)} total)")
        for c in cves:
            add("CVE", f"{c.cve_id} | severidade:{c.severity} | {c.description or ''} | refs:{c.references or 'N/A'}")
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'tools':
        tools = list(Tool.objects.filter(user=user).order_by('-created_at')[:80])
        parts.append(f"## Ferramentas de pentest/segurança cadastradas ({len(tools)} total)")
        for t in tools:
            add("TOOL", f"{t.name} [categoria:{t.category}]" + (f" — {t.description}" if t.description else ""))
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'notes':
        for n in Note.objects.filter(user=user).order_by('-created_at')[:50]:
            folder_name = n.folder.name if n.folder else "raiz"
            add("NOTE", f"{n.title} [pasta:{folder_name}]\n{(n.content or '')[:400]}")
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'files':
        for f in File.objects.filter(user=user).order_by('-uploaded_at')[:60]:
            folder_name = f.folder.name if f.folder else "raiz"
            folder_id   = f.folder.id if f.folder else ''
            size = f.file.size if f.file else 0
            url  = f"/GDriver/files/?folder={folder_id}" if folder_id else "/GDriver/files/"
            add("FILE", f"{f.name} [pasta:{folder_name}] [{round(size/1024,1)}KB] [link:{url}]")
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'folders':
        for folder in Folder.objects.filter(user=user).order_by('name'):
            parent = folder.parent.name if folder.parent else "raiz"
            add("FOLDER", f"{folder.name} [em:{parent}]")
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'links':
        for lk in ResourceLink.objects.filter(user=user).order_by('-created_at')[:60]:
            add("LINK", f"{lk.title} — {lk.url}" + (f"\n{lk.description}" if lk.description else ""))
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'projects':
        for p in Project.objects.filter(user=user).order_by('-id')[:20]:
            add("PROJECT", p.name)
            for item in ProjectItem.objects.filter(project=p)[:15]:
                add("  ITEM", f"{item.title}" + (f" | {item.notes}" if item.notes else "") + (f" | {item.link}" if item.link else ""))
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'youtube':
        for ch in YouTubeChannel.objects.filter(user=user).order_by('-id')[:30]:
            add("YOUTUBE", f"{ch.name} — {ch.url}" + (f"\n{ch.description}" if ch.description else ""))
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    if focus == 'storage':
        try:
            storage = UserStorage.objects.get(user=user)
            limit = storage.get_storage_limit_bytes()
            used = sum(
                f.file.size for f in File.objects.filter(user=user) if f.file
            )
            add("ARMAZENAMENTO", (
                f"Plano: {storage.plan} | "
                f"Limite: {round(limit/(1024**3),2)} GB | "
                f"Usado: {round(used/(1024**3),3)} GB | "
                f"Livre: {round((limit-used)/(1024**3),3)} GB"
            ))
        except Exception:
            pass
        return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)

    # ── Contexto completo (sem foco específico) ───────────────────────────────

    # Storage summary
    try:
        storage = UserStorage.objects.filter(user=user).first()
        if storage:
            limit = storage.get_storage_limit_bytes()
            used = sum(f.file.size for f in File.objects.filter(user=user) if f.file)
            add("ARMAZENAMENTO", f"Plano:{storage.plan} Limite:{round(limit/(1024**3),2)}GB Usado:{round(used/(1024**3),3)}GB")
    except Exception:
        pass

    # Files (recent 40)
    files = list(File.objects.filter(user=user).order_by('-uploaded_at')[:40])
    if files:
        parts.append(f"## ARQUIVOS ({len(files)} recentes)")
    for f in files:
        folder_name = f.folder.name if f.folder else "raiz"
        folder_id   = f.folder.id if f.folder else ''
        size = f.file.size if f.file else 0
        url  = f"/GDriver/files/?folder={folder_id}" if folder_id else "/GDriver/files/"
        add("FILE", f"{f.name} [pasta:{folder_name}] [{round(size/1024,1)}KB] [link:{url}]")

    # Notes (recent 40, partial content)
    notes = list(Note.objects.filter(user=user).order_by('-created_at')[:40])
    if notes:
        parts.append(f"## NOTAS ({len(notes)} recentes)")
    for n in notes:
        folder_name = n.folder.name if n.folder else "raiz"
        add("NOTE", f"{n.title} [pasta:{folder_name}] — {(n.content or '')[:300]}")

    # CVEs (recent 30)
    cves = list(CVE.objects.filter(user=user).order_by('-published_date')[:30])
    if cves:
        parts.append(f"## CVEs ({len(cves)} registradas)")
    for c in cves:
        add("CVE", f"{c.cve_id} | severidade:{c.severity} | {(c.description or '')[:200]} | refs:{c.references or 'N/A'}")

    # Dorks (recent 60)
    dorks = list(Dork.objects.filter(user=user).order_by('-created_at')[:60])
    if dorks:
        parts.append(f"## DORKS ({len(dorks)} registradas)")
    for d in dorks:
        add(f"DORK/{d.platform}", f"{d.query}" + (f" — {d.description}" if d.description else ""))

    # Links (recent 30)
    links = list(ResourceLink.objects.filter(user=user).order_by('-created_at')[:30])
    if links:
        parts.append(f"## LINKS ({len(links)} salvos)")
    for lk in links:
        add("LINK", f"{lk.title} — {lk.url}" + (f" | {lk.description[:100]}" if lk.description else ""))

    # Tools (recent 50)
    tools = list(Tool.objects.filter(user=user).order_by('-created_at')[:50])
    if tools:
        parts.append(f"## FERRAMENTAS ({len(tools)} cadastradas)")
    for t in tools:
        add("TOOL", f"{t.name} [categoria:{t.category}]" + (f" — {t.description[:120]}" if t.description else ""))

    # Projects
    projects = list(Project.objects.filter(user=user).order_by('-id')[:15])
    if projects:
        parts.append(f"## PROJETOS ({len(projects)})")
    for p in projects:
        add("PROJECT", p.name)
        for item in ProjectItem.objects.filter(project=p)[:10]:
            add("  ITEM", f"{item.title}" + (f" | {item.notes[:100]}" if item.notes else "") + (f" | {item.link}" if item.link else ""))

    # YouTube channels
    channels = list(YouTubeChannel.objects.filter(user=user).order_by('-id')[:20])
    if channels:
        parts.append(f"## CANAIS YOUTUBE ({len(channels)})")
    for ch in channels:
        add("YOUTUBE", f"{ch.name} — {ch.url}" + (f" | {ch.description[:100]}" if ch.description else ""))

    # Folders
    for folder in Folder.objects.filter(user=user).order_by('name')[:20]:
        parent = folder.parent.name if folder.parent else "raiz"
        add("FOLDER", f"{folder.name} [em:{parent}]")

    # Binary analyses (APK/EXE)
    if _BINARY_ANALYZER:
        analyses = list(
            BinaryAnalysis.objects.filter(
                file__user=user, status='done'
            ).select_related('file').order_by('-updated_at')[:20]
        )
        if analyses:
            parts.append(f"## ANÁLISES BINÁRIAS ({len(analyses)} concluídas)")
        for a in analyses:
            r = a.report or {}
            dangerous = r.get('dangerous_permissions', [])
            findings  = r.get('suspicious_findings', [])
            yara_hits = r.get('yara_matches', []) or []
            secrets   = r.get('secrets', []) or []
            vt        = r.get('virustotal', {}) or {}
            vt_summary = ''
            if vt.get('known'):
                vt_summary = f"VT:{vt.get('malicious',0)}/{vt.get('total',0)}"
                if vt.get('suggested_label'):
                    vt_summary += f" ({vt.get('suggested_label')})"
            elif vt.get('known') is False:
                vt_summary = 'VT:desconhecido'
            yara_summary = ''
            if yara_hits:
                yara_summary = 'yara:' + ','.join(y.get('rule', '?') for y in yara_hits[:5])
            secrets_summary = ''
            if secrets:
                secrets_summary = f"segredos:{len(secrets)}(HIGH:{sum(1 for s in secrets if s.get('severity')=='HIGH')})"
            add("BINARY_ANALYSIS", (
                f"{a.file.name} [{a.file_type.upper()}] "
                f"risco:{a.risk_score}/100 ({a.risk_label}) "
                f"pacote:{r.get('package','N/A')} "
                f"permissoes_perigosas:{len(dangerous)} "
                f"achados_suspeitos:{len(findings)} "
                f"{yara_summary} {secrets_summary} {vt_summary} "
                f"url:/binary_analyzer/file/{a.file.id}/"
            ))

    # Copilot/system doc
    try:
        doc = get_copilot_instructions()
        if doc:
            parts.insert(0, f"[SYSTEM DOC]\n{doc[:800]}")
    except Exception:
        pass

    return Truncator("\n".join(parts)).chars(MAX_CONTEXT_CHARS)


def compose_prompt(user, question: str, attachment_text: Optional[str] = None) -> str:
    question_lower = (question or "").lower()
    focus = None

    kw = question_lower
    if "shodan" in kw:
        focus = "dorks_shodan"
    elif "google dork" in kw or ("google" in kw and "dork" in kw):
        focus = "dorks_google"
    elif "dork" in kw:
        focus = "dorks"
    elif any(x in kw for x in ("cve", "vulnerab", "exploit", "cve-")):
        focus = "cves"
    elif any(x in kw for x in ("ferramenta", "tool", "pentest", "hacking tool")):
        focus = "tools"
    elif any(x in kw for x in ("nota", "notas", "anotação")):
        focus = "notes"
    elif any(x in kw for x in ("arquivo", "pasta", "upload", "ficheiro", "folder")):
        focus = "files"
    elif any(x in kw for x in ("link", "recurso", "url", "site")):
        focus = "links"
    elif any(x in kw for x in ("projeto", "project")):
        focus = "projects"
    elif any(x in kw for x in ("youtube", "canal", "channel")):
        focus = "youtube"
    elif any(x in kw for x in ("armazenamento", "storage", "plano", "espaço", "disco")):
        focus = "storage"
    # Perguntas sobre o próprio sistema não precisam de foco específico — o contexto
    # completo + a descrição do sistema no topo já cobrem.
    # binary_analyzer: sem foco específico, cobre via contexto completo

    context = build_context_for_user(user, focus=focus)
    username = getattr(user, 'username', 'usuário')
    dt = timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')

    attachment_section = ""
    if attachment_text and attachment_text.strip():
        truncated = attachment_text[:8000]
        attachment_section = (
            "═══ ARQUIVO ANEXADO PELO USUÁRIO ═══\n"
            "ATENÇÃO: o texto abaixo É o conteúdo completo do arquivo. "
            "Você JÁ TEM acesso a ele — leia, analise e responda com base nesse conteúdo.\n\n"
            f"{truncated}\n"
            "═════════════════════════════════════\n\n"
        )

    return PROMPT_TEMPLATE.format(
        username=username,
        datetime=dt,
        contexts=context,
        attachment_section=attachment_section,
        question=question,
    )


def get_system_description() -> str:
    """Returns a concise, always-present description of the GDriver system."""
    return """## O QUE É O GDRIVE / GDRIVER
GDriver (também chamado de GDrive ou "o sistema") é uma plataforma web **pessoal e auto-hospedável** construída em Django. Funciona como um substituto do Google Drive com módulos voltados a segurança ofensiva e organização de conhecimento técnico.

### Módulos disponíveis
- **Gerenciador de Arquivos** (`/GDriver/files/`): upload em chunks, thumbnails de vídeo via FFmpeg, preview inline (imagens, vídeos, PDFs, código), organização em pastas, compartilhamento, limite de armazenamento configurável por usuário (padrão 15 GB).
- **Notas** (`/GDriver/notes/`): editor markdown com tags e busca.
- **Google Dorks** (`/GDriver/dorks/`): coleção de dorks para Google, Shodan, Censys, Tor e Firefox.
- **CVEs** (`/GDriver/cves/`): base de vulnerabilidades importável via JSON (formato NVD), busca por CVE-ID, descrição e severidade.
- **Ferramentas de Segurança** (`/GDriver/tools/`): catálogo de ferramentas de pentest com documentação.
- **Projetos** (`/GDriver/projects/`): gerenciamento de projetos com itens e terminal interativo via WebSocket.
- **Links / Recursos** (`/GDriver/links/`): bookmarks organizados com descrição.
- **Canais YouTube** (`/GDriver/youtube/`): canais salvos para referência.
- **Assistente de IA** (`/ai_assistant/`): chat com Ollama (modelo local), com acesso a todos os dados do usuário via RAG.
- **Terminal Interativo** (`/GDriver/projects/<id>/terminal/`): shell real (cmd.exe no Windows, bash no Linux) via WebSocket.
- **Painel Principal** (`/GDriver/dashboard/`): visão geral do sistema.
- **API REST** (`/api/`): acesso programático aos dados.

### Stack técnica
Django 5.x, Django Channels (WebSocket), Uvicorn/Daphne (ASGI), ChromaDB (RAG vetorial), Ollama (LLM local), FFmpeg (thumbnails de vídeo), Pillow (imagens), Django REST Framework.

### Importante
- "GDriver", "GDrive", "meu sistema", "o sistema", "o programa", "a plataforma" = **este sistema**, NUNCA Google Drive.
- Roda na porta **8787** por padrão (`python server.py`).
- Auto-hospedado: todos os dados ficam locais, sem nuvem externa."""


def get_copilot_instructions() -> str:
    path = os.path.join(os.path.dirname(__file__), '../.github/copilot-instructions.md')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ''
