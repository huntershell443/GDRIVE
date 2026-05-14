# file_manager/upload_handlers.py
import os
from django.core.files.uploadhandler import TemporaryFileUploadHandler
from django.conf import settings

class CustomTempFileUploadHandler(TemporaryFileUploadHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Usa diretório personalizado em vez de /tmp
        self.upload_dir = getattr(settings, 'FILE_UPLOAD_TEMP_DIR', '/home/tmp/django_uploads')
        os.makedirs(self.upload_dir, exist_ok=True)