"""
Background analysis task. Runs in a daemon thread — no Celery required.
"""
import logging

logger = logging.getLogger(__name__)


def run_analysis(file_id: int) -> None:
    """Analyze the binary file associated with a file_manager.File id."""
    import django
    django.setup() if not django.conf.settings.configured else None  # noqa

    from file_manager.models import File
    from binary_analyzer.models import BinaryAnalysis

    try:
        analysis = BinaryAnalysis.objects.get(file_id=file_id)
    except BinaryAnalysis.DoesNotExist:
        logger.error("BinaryAnalysis not found for file_id=%s", file_id)
        return

    analysis.status = BinaryAnalysis.STATUS_ANALYZING
    analysis.save(update_fields=['status', 'updated_at'])

    try:
        file_obj = analysis.file
        path = file_obj.file.path

        if analysis.file_type == BinaryAnalysis.FILETYPE_APK:
            from binary_analyzer.analyzers.apk_analyzer import analyze_apk
            report = analyze_apk(path)
        else:
            from binary_analyzer.analyzers.exe_analyzer import analyze_exe
            report = analyze_exe(path)

        analysis.report     = report
        analysis.risk_score = report.get('risk_score', 0)
        analysis.status     = BinaryAnalysis.STATUS_DONE
        analysis.error_message = ''

    except Exception as exc:
        logger.exception("Analysis failed for file_id=%s", file_id)
        analysis.status = BinaryAnalysis.STATUS_ERROR
        analysis.error_message = str(exc)

    analysis.save(update_fields=['status', 'report', 'risk_score', 'error_message', 'updated_at'])
