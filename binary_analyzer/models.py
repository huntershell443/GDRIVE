from django.db import models


class BinaryAnalysis(models.Model):
    STATUS_PENDING   = 'pending'
    STATUS_ANALYZING = 'analyzing'
    STATUS_DONE      = 'done'
    STATUS_ERROR     = 'error'
    STATUS_CHOICES = [
        (STATUS_PENDING,   'Pendente'),
        (STATUS_ANALYZING, 'Analisando'),
        (STATUS_DONE,      'Concluído'),
        (STATUS_ERROR,     'Erro'),
    ]

    FILETYPE_APK = 'apk'
    FILETYPE_EXE = 'exe'
    FILETYPE_CHOICES = [
        (FILETYPE_APK, 'APK Android'),
        (FILETYPE_EXE, 'EXE/PE Windows'),
    ]

    file = models.OneToOneField(
        'file_manager.File',
        on_delete=models.CASCADE,
        related_name='binary_analysis',
    )
    status    = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    file_type = models.CharField(max_length=10, choices=FILETYPE_CHOICES)
    report    = models.JSONField(null=True, blank=True)
    risk_score = models.IntegerField(null=True, blank=True)  # 0–100
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Análise Binária'
        verbose_name_plural = 'Análises Binárias'
        ordering = ['-created_at']

    def __str__(self):
        return f"Análise de {self.file.name} ({self.status})"

    @property
    def risk_label(self):
        if self.risk_score is None:
            return 'Desconhecido'
        if self.risk_score >= 75:
            return 'Alto'
        if self.risk_score >= 40:
            return 'Médio'
        return 'Baixo'

    @property
    def risk_color(self):
        if self.risk_score is None:
            return 'secondary'
        if self.risk_score >= 75:
            return 'danger'
        if self.risk_score >= 40:
            return 'warning'
        return 'success'
