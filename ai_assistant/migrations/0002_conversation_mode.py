from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_assistant', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='mode',
            field=models.CharField(
                choices=[('chat', 'Chat'), ('terminal', 'Terminal')],
                db_index=True,
                default='chat',
                max_length=16,
            ),
        ),
    ]
