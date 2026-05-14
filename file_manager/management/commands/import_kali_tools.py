from django.core.management.base import BaseCommand
from file_manager.models import Tool
from django.contrib.auth.models import User

KALI_TOOLS = [
    {'name': 'Nmap', 'category': 'Reconhecimento', 'usage': 'Scanner de redes e auditoria de segurança.'},
    {'name': 'Masscan', 'category': 'Reconhecimento', 'usage': 'Scanner de portas extremamente rápido.'},
    {'name': 'Metasploit Framework', 'category': 'Exploitação', 'usage': 'Framework para desenvolvimento e execução de exploits.'},
    {'name': 'BeEF', 'category': 'Exploitação', 'usage': 'Framework para exploração de navegadores.'},
    {'name': 'Autopsy', 'category': 'Análise Forense', 'usage': 'Plataforma de análise forense digital.'},
    {'name': 'Volatility', 'category': 'Análise Forense', 'usage': 'Framework para análise de memória volátil.'},
]

class Command(BaseCommand):
    help = 'Importa ferramentas Kali padrão para o usuário especificado'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Nome do usuário para associar as ferramentas')

    def handle(self, *args, **kwargs):
        username = kwargs['username']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Usuário "{username}" não encontrado.'))
            return
        
        created_count = 0
        for tool_data in KALI_TOOLS:
            tool, created = Tool.objects.get_or_create(
                user=user,
                name=tool_data['name'],
                defaults={
                    'category': tool_data['category'],
                    'usage': tool_data['usage'],
                }
            )
            if created:
                created_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'{created_count} ferramentas Kali importadas para o usuário {username}.'))
