import json
from django.core.management.base import BaseCommand
from cves.models import CVE  # Ajuste o import para seu app
from django.contrib.auth.models import User
from django.utils.dateparse import parse_datetime

class Command(BaseCommand):
    help = 'Importa CVEs de um arquivo JSON no formato NVD'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Caminho do arquivo JSON para importar')
        parser.add_argument(
            '--username',
            type=str,
            help='Usuário dono dos registros (padrão: admin)',
            default='admin'
        )

    def handle(self, *args, **options):
        file_path = options['file_path']
        username = options['username']

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Usuário '{username}' não encontrado."))
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            vulnerabilities = data.get("vulnerabilities", [])
            if not vulnerabilities:
                self.stdout.write(self.style.ERROR("JSON não contém chave 'vulnerabilities'."))
                return

            count_imported = 0
            for item in vulnerabilities:
                cve_data = item.get("cve", {})
                cve_id = cve_data.get("id")
                if not cve_id:
                    continue

                descriptions = cve_data.get("descriptions", [])
                description = next((d.get("value") for d in descriptions if d.get("lang") == "en"), "")

                metrics = cve_data.get("metrics", {})
                severity = "N/A"
                if "cvssMetricV31" in metrics:
                    severity = metrics["cvssMetricV31"][0].get("cvssData", {}).get("baseSeverity", "N/A")
                elif "cvssMetricV30" in metrics:
                    severity = metrics["cvssMetricV30"][0].get("cvssData", {}).get("baseSeverity", "N/A")
                elif "cvssMetricV2" in metrics:
                    severity = metrics["cvssMetricV2"][0].get("baseSeverity", "N/A")

                references = cve_data.get("references", [])
                link = references[0]["url"] if references else ""

                published_str = cve_data.get("published")
                published_date = parse_datetime(published_str) if published_str else None

                obj, created = CVE.objects.get_or_create(
                    cve_id=cve_id,
                    defaults={
                        "description": description,
                        "severity": severity,
                        "references": link,
                        "published_date": published_date,
                        "user": user
                    }
                )
                if created:
                    count_imported += 1

            self.stdout.write(self.style.SUCCESS(f"{count_imported} CVEs importadas com sucesso."))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Arquivo não encontrado: {file_path}"))

        except json.JSONDecodeError:
            self.stdout.write(self.style.ERROR("Erro ao decodificar JSON. Verifique o formato do arquivo."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erro inesperado: {e}"))
