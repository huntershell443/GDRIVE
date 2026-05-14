import threading
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from file_manager.models import File
from binary_analyzer.models import BinaryAnalysis
from binary_analyzer.tasks import run_analysis


# Se uma análise está marcada como `analyzing` há mais que isso, considera-se travada
# (provável reboot do servidor no meio da execução) e permite re-disparar.
STALE_ANALYZING_AFTER = timedelta(minutes=10)


def _wants_json(request) -> bool:
    accept = (request.META.get('HTTP_ACCEPT') or '').lower()
    if 'application/json' in accept:
        return True
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return True
    return False


def _detect_file_type(name: str) -> str:
    name = (name or '').lower()
    if name.endswith('.apk'):
        return 'apk'
    if name.endswith(('.exe', '.dll', '.sys', '.scr')):
        return 'exe'
    return ''


@login_required
def analysis_report(request, file_id):
    file_obj = get_object_or_404(File, pk=file_id, user=request.user)
    try:
        analysis = file_obj.binary_analysis
    except BinaryAnalysis.DoesNotExist:
        analysis = None

    # Detecta análise "travada" (reboot do servidor durante execução)
    stale = False
    if analysis and analysis.status == BinaryAnalysis.STATUS_ANALYZING:
        if analysis.updated_at < timezone.now() - STALE_ANALYZING_AFTER:
            stale = True

    return render(request, 'binary_report.html', {
        'file': file_obj,
        'analysis': analysis,
        'stale': stale,
    })


@login_required
def analysis_status(request, file_id):
    """JSON polling endpoint — frontend queries while analysis runs."""
    file_obj = get_object_or_404(File, pk=file_id, user=request.user)
    try:
        a = file_obj.binary_analysis
        return JsonResponse({
            'status': a.status,
            'risk_score': a.risk_score,
            'risk_label': a.risk_label,
            'risk_color': a.risk_color,
            'error': a.error_message,
        })
    except BinaryAnalysis.DoesNotExist:
        return JsonResponse({'status': 'not_found'})


@require_POST
@login_required
def trigger_analysis(request, file_id):
    """Manually trigger (or re-trigger) analysis for a file."""
    file_obj = get_object_or_404(File, pk=file_id, user=request.user)
    file_type = _detect_file_type(file_obj.name)

    if not file_type:
        if _wants_json(request):
            return JsonResponse({'error': 'Tipo de arquivo não suportado para análise.'}, status=400)
        return redirect(reverse('binary_analyzer:report', args=[file_id]))

    analysis, _ = BinaryAnalysis.objects.get_or_create(
        file=file_obj,
        defaults={'file_type': file_type},
    )

    # Dedup: se outro File com o mesmo SHA-256 já tem análise concluída,
    # copia o relatório em vez de re-rodar.
    copied = _try_copy_done_report(file_obj, analysis)
    if not copied:
        analysis.status = BinaryAnalysis.STATUS_PENDING
        analysis.file_type = file_type
        analysis.report = None
        analysis.error_message = ''
        analysis.save()
        t = threading.Thread(target=run_analysis, args=(file_obj.id,), daemon=True)
        t.start()

    if _wants_json(request):
        return JsonResponse({
            'status': 'reused' if copied else 'started',
            'file_id': file_id,
        })
    return redirect(reverse('binary_analyzer:report', args=[file_id]))


def _try_copy_done_report(file_obj, analysis) -> bool:
    """Se já existe BinaryAnalysis 'done' para outro File com o mesmo SHA-256
    do binário atual, reaproveita o report. Retorna True se copiou.
    """
    try:
        import hashlib
        h = hashlib.sha256()
        with open(file_obj.file.path, 'rb') as fh:
            for chunk in iter(lambda: fh.read(65536), b''):
                h.update(chunk)
        sha = h.hexdigest()
    except Exception:
        return False

    existing = (BinaryAnalysis.objects
                .filter(status=BinaryAnalysis.STATUS_DONE,
                        report__sha256=sha)
                .exclude(pk=analysis.pk)
                .order_by('-updated_at')
                .first())
    if not existing or not existing.report:
        return False

    analysis.status = BinaryAnalysis.STATUS_DONE
    analysis.report = existing.report
    analysis.risk_score = existing.risk_score
    analysis.error_message = ''
    analysis.save()
    return True


@login_required
def badges_for_files(request):
    """Retorna metadados de análise para os file ids dados.

    Query: ?ids=1,2,3
    Usado pelo file_list.html para mostrar emblema de risco e VT direto nos cards.
    """
    raw = request.GET.get('ids', '')
    try:
        ids = [int(x) for x in raw.split(',') if x.strip().isdigit()]
    except Exception:
        ids = []
    if not ids:
        return JsonResponse({'badges': {}})

    qs = BinaryAnalysis.objects.filter(
        file__user=request.user, file_id__in=ids
    ).select_related('file')
    out = {}
    for a in qs:
        vt = (a.report or {}).get('virustotal') or {}
        vt_summary = None
        if vt.get('known'):
            vt_summary = {
                'malicious': vt.get('malicious', 0),
                'total':     vt.get('total', 0),
                'permalink': vt.get('permalink', ''),
                'label':     vt.get('suggested_label', ''),
            }
        elif vt.get('known') is False:
            vt_summary = {'unknown': True}
        out[str(a.file_id)] = {
            'status': a.status,
            'risk_score': a.risk_score,
            'risk_label': a.risk_label,
            'risk_color': a.risk_color,
            'file_type': a.file_type,
            'vt': vt_summary,
        }
    return JsonResponse({'badges': out})


@require_POST
@login_required
def recheck_virustotal(request, file_id):
    """Re-consulta o VirusTotal pelo SHA-256 e atualiza a chave 'virustotal' do report.

    Útil quando: (a) você analisou um sample antes de configurar a VT_API_KEY;
    (b) o hash veio como 'desconhecido' e horas/dias depois já foi catalogado por
    outros pesquisadores. Não re-roda toda a análise — só atualiza o subcampo VT.
    """
    file_obj = get_object_or_404(File, pk=file_id, user=request.user)
    try:
        analysis = file_obj.binary_analysis
    except BinaryAnalysis.DoesNotExist:
        if _wants_json(request):
            return JsonResponse({'error': 'sem análise'}, status=404)
        return redirect(reverse('binary_analyzer:report', args=[file_id]))

    sha = (analysis.report or {}).get('sha256') or ''
    if not sha:
        # Calcula na hora se o report não tem hash gravado
        try:
            import hashlib
            h = hashlib.sha256()
            with open(file_obj.file.path, 'rb') as fh:
                for chunk in iter(lambda: fh.read(65536), b''):
                    h.update(chunk)
            sha = h.hexdigest()
        except Exception:
            sha = ''

    from binary_analyzer.enrichment import virustotal_lookup
    vt_data = virustotal_lookup(sha) if sha else {}

    if not vt_data:
        msg = 'VT_API_KEY não configurada ou hash vazio'
        if _wants_json(request):
            return JsonResponse({'error': msg}, status=400)
        return redirect(reverse('binary_analyzer:report', args=[file_id]))

    report = analysis.report or {}
    report['virustotal'] = vt_data
    analysis.report = report
    analysis.save(update_fields=['report', 'updated_at'])

    if _wants_json(request):
        return JsonResponse({'success': True, 'virustotal': vt_data})
    return redirect(reverse('binary_analyzer:report', args=[file_id]))


@login_required
def analyses_list(request):
    """List all analyses for the current user."""
    analyses = BinaryAnalysis.objects.filter(
        file__user=request.user
    ).select_related('file').order_by('-created_at')[:50]
    return render(request, 'binary_analyses_list.html', {'analyses': analyses})
