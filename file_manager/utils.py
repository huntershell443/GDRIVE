import subprocess
from tempfile import NamedTemporaryFile
import shutil
import os

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:
    HEIF_SUPPORT = False

from PIL import Image


def generate_video_thumbnail(video_file_path):
    temp_thumb = NamedTemporaryFile(suffix=".jpg", delete=False)
    temp_thumb.close()

    command = [
        'ffmpeg',
        '-i', video_file_path,
        '-ss', '00:00:01.000',
        '-vframes', '1',
        temp_thumb.name,
    ]
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return temp_thumb.name


def generate_heif_thumbnail(heif_file_path):
    """Converte HEIF/HEIC para JPEG. Requer pillow-heif instalado."""
    if not HEIF_SUPPORT:
        return None
    temp_thumb = NamedTemporaryFile(suffix=".jpg", delete=False)
    temp_thumb.close()
    try:
        with Image.open(heif_file_path) as img:
            img = img.convert('RGB')
            img.thumbnail((800, 800))
            img.save(temp_thumb.name, 'JPEG', quality=85)
        return temp_thumb.name
    except Exception:
        if os.path.exists(temp_thumb.name):
            os.unlink(temp_thumb.name)
        return None


def get_folder_storage_usage(path):
    """Retorna o uso total de espaço da pasta (em bytes)."""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)
    return total_size


def get_server_storage_info(path='/'):
    """Retorna informações sobre o disco no qual o caminho está localizado."""
    total, used, free = shutil.disk_usage(path)
    return {
        'total': total,
        'used': used,
        'free': free
    }
