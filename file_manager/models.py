from django.db import models
from django.contrib.auth.models import User
import os
import shutil
from django.conf import settings
import secrets
from django.utils import timezone
from datetime import timedelta

class EmailVerification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    code = models.CharField(max_length=6, default='000000')  # Adicione default
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    
    def is_expired(self):
        expiration_time = self.created_at + timedelta(days=1)
        return timezone.now() > expiration_time
    
    def generate_code(self):
        self.code = ''.join(secrets.choice('0123456789') for _ in range(6))
        self.save()
        return self.code
    
    class Meta:
        db_table = 'email_verification'

def user_directory_path(instance, filename):
    if instance.folder:
        return f'{instance.user.username}/{instance.folder}/{filename}'
    return f'{instance.user.username}/{filename}'

class File(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to=user_directory_path)
    folder = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255)
    thumbnail = models.ImageField(upload_to='thumbnails/%Y/%m/%d/', blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # CAMPOS ADICIONADOS PARA SUPORTAR COMPARTILHAMENTO GLOBAL
    is_global = models.BooleanField(default=False)
    global_created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='global_files')

    def delete(self, *args, **kwargs):
        if self.file and os.path.isfile(self.file.path):
            os.remove(self.file.path)
        if self.thumbnail and os.path.isfile(self.thumbnail.path):
            os.remove(self.thumbnail.path)
        super().delete(*args, **kwargs)

    def __str__(self):
        return self.name

class StoragePlan(models.TextChoices):
    PLAN_15GB = '15', '15 GB'
    PLAN_50GB = '50', '50 GB'
    PLAN_100GB = '100', '100 GB'
    PLAN_200GB = '200', '200 GB'
    PLAN_400GB = '400', '400 GB'
    CUSTOM = 'custom', 'Personalizado'

class UserStorage(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    plan = models.CharField(max_length=10, choices=StoragePlan.choices, default=StoragePlan.PLAN_15GB)
    custom_limit_gb = models.FloatField(null=True, blank=True)

    def get_storage_limit_bytes(self):
        if self.plan == StoragePlan.CUSTOM:
            return (self.custom_limit_gb or 0) * 1024**3
        return int(self.plan) * 1024**3

    def __str__(self):
        return f"Armazenamento de {self.user.username}"

class Folder(models.Model):
    name = models.CharField(max_length=255)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subfolders')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    def get_full_path(self):
        from django.conf import settings
        if self.parent:
            return os.path.join(self.parent.get_full_path(), self.name)
        return os.path.join(settings.MEDIA_ROOT, 'user_uploads', str(self.user.id), self.name)
    
    def create_physical_folder(self):
        path = self.get_full_path()
        os.makedirs(path, exist_ok=True)
        return path
    
    def delete_physical_folder(self):
        path = self.get_full_path()
        if os.path.exists(path):
            shutil.rmtree(path)
    
    def move_physical_folder(self, new_parent):
        old_path = self.get_full_path()
        self.parent = new_parent
        self.save()
        new_path = self.get_full_path()
        
        if os.path.exists(old_path):
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            shutil.move(old_path, new_path)

class Note(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    tags = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    folder = models.ForeignKey(Folder, on_delete=models.SET_NULL, null=True, blank=True)
    # CAMPOS ADICIONADOS PARA SUPORTAR COMPARTILHAMENTO GLOBAL
    is_global = models.BooleanField(default=False)
    global_created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='global_notes')

    def __str__(self):
        return self.title

class DorkPlatform(models.TextChoices):
    GOOGLE = 'Google'
    SHODAN = 'Shodan'
    CENSYS = 'Censys'
    FIREFOX = 'Firefox'
    TOR = 'Tor'

class Dork(models.Model):
    query = models.TextField()
    description = models.TextField()
    platform = models.CharField(max_length=50, choices=DorkPlatform.choices, default=DorkPlatform.GOOGLE)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_global = models.BooleanField(default=False)
    global_created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='global_dorks')

    def __str__(self):
        return f"[{self.platform}] {self.query[:50]}"

class DorkNote(models.Model):
    dork = models.ForeignKey(Dork, on_delete=models.CASCADE)
    note = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


class CVE(models.Model):
    cve_id = models.CharField(max_length=20, unique=True)
    description = models.TextField()
    severity = models.CharField(max_length=20)
    published_date = models.DateField()
    references = models.URLField()
    is_global = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    
    # Adicione índices para melhor performance
    class Meta:
        indexes = [
            models.Index(fields=['cve_id']),
            models.Index(fields=['published_date']),
            models.Index(fields=['severity']),
            models.Index(fields=['user', 'is_global']),
        ]
    
    def __str__(self):
        return self.cve_id

class ResourceLink(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    url = models.URLField()
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_global = models.BooleanField(default=False)
    global_created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='global_links')

    def __str__(self):
        return self.title

class Tool(models.Model):
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255)
    description = models.TextField()
    homepage = models.URLField(blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_global = models.BooleanField(default=False)
    global_created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='global_tools')

    def __str__(self):
        return self.name

class ToolNote(models.Model):
    tool = models.ForeignKey(Tool, on_delete=models.CASCADE)
    note = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

class Project(models.Model):
    name = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='subfolders')

    def __str__(self):
        return self.name

class ProjectItem(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='projects/items/', blank=True, null=True)
    link = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.title

class YouTubeChannel(models.Model):
    name = models.CharField(max_length=255)
    url = models.URLField()
    description = models.TextField(blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_global = models.BooleanField(default=False)
    global_created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='global_channels')

    def __str__(self):
        return self.name

class GlobalFile(models.Model):
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='global_files/')
    description = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    category = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.name

class SystemConfig(models.Model):
    """Configuração global do sistema — apenas um registro permitido."""
    media_root = models.CharField(
        max_length=500,
        verbose_name='Diretório de armazenamento (MEDIA_ROOT)',
        help_text='Caminho absoluto onde os arquivos dos usuários serão salvos. Ex: D:/GDrive_users/  ou  /var/data/gdrive_users/',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração do Sistema'
        verbose_name_plural = 'Configuração do Sistema'

    def __str__(self):
        return f'Configuração do Sistema — {self.media_root}'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        # Aplica imediatamente em runtime
        settings.MEDIA_ROOT = self.media_root
        settings.STATICFILES_DIRS  # keep reference

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={
            'media_root': settings.MEDIA_ROOT,
        })
        return obj

    def delete(self, *args, **kwargs):
        pass  # singleton — não pode ser deletado


class SharedResource(models.Model):
    PERMISSION_CHOICES = [
        ('view', 'Visualizar'),
        ('edit', 'Editar'),
    ]
    
    resource_type = models.CharField(max_length=50)  # 'file', 'note', 'tool', etc.
    resource_id = models.IntegerField()  # ID do recurso original
    shared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shared_resources')
    shared_with = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='accessible_resources')
    shared_with_all = models.BooleanField(default=False)  # Compartilhado com todos os usuários
    created_at = models.DateTimeField(auto_now_add=True)
    permission = models.CharField(max_length=20, choices=PERMISSION_CHOICES, default='view')

    class Meta:
        indexes = [
            models.Index(fields=['resource_type', 'resource_id']),
        ]
    
    def __str__(self):
        return f"{self.resource_type} {self.resource_id} shared by {self.shared_by}"