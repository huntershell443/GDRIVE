import logging
import threading

from django.db.models.signals import post_save
from django.dispatch import receiver

from file_manager.models import File

logger = logging.getLogger(__name__)


_APK_EXT_HINT = ('.apk',)
_EXE_EXT_HINT = ('.exe', '.dll', '.sys', '.scr')


def detect_binary_type(path: str, name_hint: str = '') -> str:
    """Determina apk/exe pelo conteúdo (magic bytes), com extensão como dica.

    Retorna 'apk', 'exe' ou ''.
    """
    name = (name_hint or '').lower()
    try:
        with open(path, 'rb') as f:
            head = f.read(4096)
    except Exception:
        head = b''

    # PE (EXE/DLL/SYS/SCR): assinatura MZ + header PE
    if head[:2] == b'MZ' and len(head) > 0x40:
        try:
            import struct
            pe_off = struct.unpack_from('<I', head, 0x3c)[0]
            if pe_off + 4 <= len(head) and head[pe_off:pe_off + 4] == b'PE\x00\x00':
                return 'exe'
            # Mesmo sem o PE header dentro dos 4096 bytes lidos, MZ + extensão Windows = exe.
            if name.endswith(_EXE_EXT_HINT):
                return 'exe'
        except Exception:
            pass

    # APK: zip (PK\x03\x04) com AndroidManifest.xml dentro.
    if head[:4] == b'PK\x03\x04':
        # extensão é o sinal mais barato; se for .apk, aceita direto
        if name.endswith(_APK_EXT_HINT):
            return 'apk'
        # senão olha se tem AndroidManifest.xml na lista do zip
        try:
            import zipfile
            with zipfile.ZipFile(path, 'r') as z:
                names = z.namelist()
                if 'AndroidManifest.xml' in names and any(
                    n.startswith('classes') and n.endswith('.dex') for n in names
                ):
                    return 'apk'
        except Exception:
            pass

    # Última linha de defesa: extensão pura, mesmo sem confirmação por bytes.
    if name.endswith(_APK_EXT_HINT):
        return 'apk'
    if name.endswith(_EXE_EXT_HINT):
        return 'exe'
    return ''


@receiver(post_save, sender=File)
def auto_trigger_binary_analysis(sender, instance, created, **kwargs):
    if not created:
        return

    try:
        path = instance.file.path if instance.file else None
    except Exception:
        path = None

    if not path:
        return

    file_type = detect_binary_type(path, instance.name or '')
    if not file_type:
        return

    try:
        from binary_analyzer.models import BinaryAnalysis
        from binary_analyzer.tasks import run_analysis

        analysis, new = BinaryAnalysis.objects.get_or_create(
            file=instance,
            defaults={'file_type': file_type, 'status': BinaryAnalysis.STATUS_PENDING},
        )
        if new or analysis.status == BinaryAnalysis.STATUS_PENDING:
            t = threading.Thread(target=run_analysis, args=(instance.id,), daemon=True)
            t.start()
    except Exception as exc:
        logger.exception("auto_trigger_binary_analysis failed for File id=%s: %s", instance.id, exc)
