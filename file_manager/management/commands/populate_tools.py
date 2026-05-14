from django.core.management.base import BaseCommand
from file_manager.models import Tool
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Adiciona ferramentas do Kali Linux no banco'

    def handle(self, *args, **kwargs):
        user = User.objects.first()  # Só para associar um usuário, pode mudar isso

        tools = [
            {"name": "Nmap", "category": "Rede", "usage": "Escaneia redes para descobrir hosts e serviços."},
            {"name": "Metasploit", "category": "Exploits", "usage": "Ferramenta para explorar vulnerabilidades."},
            {"name": "Wireshark", "category": "Análise", "usage": "Captura e analisa tráfego de rede."},
        ]

        for t in tools:
            tool, created = Tool.objects.get_or_create(
                name=t["name"],
                user=user,
                defaults={"category": t["category"], "usage": t["usage"]}
            )
            if created:
                print(f"Ferramenta criada: {tool.name}")
            else:
                print(f"Ferramenta já existe: {tool.name}")
