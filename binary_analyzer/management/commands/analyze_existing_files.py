"""Backfill: percorre File sem BinaryAnalysis e dispara análise.

Uso:
    python manage.py analyze_existing_files            # roda em background (threads)
    python manage.py analyze_existing_files --sync     # roda inline (1 a 1, mesmo processo)
    python manage.py analyze_existing_files --user joao
    python manage.py analyze_existing_files --reset-stale  # reabre análises 'analyzing' antigas
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from binary_analyzer.models import BinaryAnalysis
from binary_analyzer.signals import detect_binary_type
from binary_analyzer.tasks import run_analysis
from file_manager.models import File


class Command(BaseCommand):
    help = 'Backfill — analisa arquivos enviados antes do binary_analyzer existir.'

    def add_arguments(self, parser):
        parser.add_argument('--user', help='Limita ao username dado.')
        parser.add_argument('--sync', action='store_true', help='Roda inline em vez de threads.')
        parser.add_argument('--reset-stale', action='store_true',
                            help='Reseta análises travadas em "analyzing" há mais de 10min.')
        parser.add_argument('--force', action='store_true',
                            help='Re-analisa mesmo arquivos com análise concluída.')

    def handle(self, *args, **opts):
        if opts['reset_stale']:
            cutoff = timezone.now() - timedelta(minutes=10)
            stale = BinaryAnalysis.objects.filter(
                status=BinaryAnalysis.STATUS_ANALYZING,
                updated_at__lt=cutoff,
            )
            n = stale.update(status=BinaryAnalysis.STATUS_PENDING, error_message='reset by command')
            self.stdout.write(self.style.WARNING(f'{n} análise(s) travadas resetadas para pending.'))

        files = File.objects.all().select_related('user')
        if opts['user']:
            files = files.filter(user__username=opts['user'])

        triggered = 0
        skipped = 0
        for f in files:
            try:
                path = f.file.path if f.file else None
            except Exception:
                path = None
            if not path:
                skipped += 1
                continue

            ftype = detect_binary_type(path, f.name or '')
            if not ftype:
                skipped += 1
                continue

            existing = BinaryAnalysis.objects.filter(file=f).first()
            if existing and existing.status == BinaryAnalysis.STATUS_DONE and not opts['force']:
                skipped += 1
                continue

            if existing:
                existing.status = BinaryAnalysis.STATUS_PENDING
                existing.file_type = ftype
                existing.report = None
                existing.error_message = ''
                existing.save()
            else:
                BinaryAnalysis.objects.create(
                    file=f, file_type=ftype, status=BinaryAnalysis.STATUS_PENDING,
                )

            self.stdout.write(f'  → File #{f.id}  {f.name}  [{ftype}]  user={f.user.username}')
            if opts['sync']:
                run_analysis(f.id)
            else:
                import threading
                threading.Thread(target=run_analysis, args=(f.id,), daemon=True).start()
            triggered += 1

        self.stdout.write(self.style.SUCCESS(
            f'Concluído. disparadas={triggered}  ignoradas={skipped}'
        ))
        if not opts['sync'] and triggered:
            self.stdout.write('As análises rodam em background; acompanhe pelo /binary_analyzer/.')
