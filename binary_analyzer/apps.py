from django.apps import AppConfig


class BinaryAnalyzerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'binary_analyzer'
    verbose_name = 'Analisador Binário'

    def ready(self):
        import binary_analyzer.signals  # noqa: F401
