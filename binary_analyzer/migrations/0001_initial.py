from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('file_manager', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='BinaryAnalysis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    choices=[('pending', 'Pendente'), ('analyzing', 'Analisando'), ('done', 'Concluído'), ('error', 'Erro')],
                    default='pending', max_length=20,
                )),
                ('file_type', models.CharField(
                    choices=[('apk', 'APK Android'), ('exe', 'EXE/PE Windows')],
                    max_length=10,
                )),
                ('report', models.JSONField(blank=True, null=True)),
                ('risk_score', models.IntegerField(blank=True, null=True)),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('file', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='binary_analysis',
                    to='file_manager.file',
                )),
            ],
            options={
                'verbose_name': 'Análise Binária',
                'verbose_name_plural': 'Análises Binárias',
                'ordering': ['-created_at'],
            },
        ),
    ]
