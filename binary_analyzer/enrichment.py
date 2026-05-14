"""Enriquecimentos opcionais para a análise binária.

Cada função degrada graciosamente se a dependência ou config não existir:
- YARA           → requer pacote `yara-python` e regras em binary_analyzer/yara_rules/
- capa           → requer pacote `flare-capa` (lib `capa`)
- VirusTotal     → requer settings.VT_API_KEY (consulta apenas por hash, nunca upload)
- Credenciais    → puro Python, sempre disponível
"""
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Carregamento de YARA (uma vez por processo) ──────────────────────────────
try:
    import yara as _yara
    YARA_AVAILABLE = True
except ImportError:
    _yara = None
    YARA_AVAILABLE = False

_YARA_COMPILED = None
_YARA_RULES_DIR = Path(__file__).parent / 'yara_rules'


def _load_yara_rules():
    """Compila todas as .yar/.yara em yara_rules/. Cache em memória."""
    global _YARA_COMPILED
    if _YARA_COMPILED is not None or not YARA_AVAILABLE:
        return _YARA_COMPILED

    if not _YARA_RULES_DIR.exists():
        return None

    files = {}
    for p in _YARA_RULES_DIR.rglob('*'):
        if p.is_file() and p.suffix.lower() in ('.yar', '.yara'):
            files[p.stem] = str(p)

    if not files:
        return None

    try:
        _YARA_COMPILED = _yara.compile(filepaths=files)
        logger.info("YARA: %d regras carregadas de %s", len(files), _YARA_RULES_DIR)
    except Exception as exc:
        logger.exception("YARA: falha ao compilar regras: %s", exc)
        _YARA_COMPILED = None
    return _YARA_COMPILED


def yara_scan(path: str) -> list:
    """Roda YARA contra o arquivo. Retorna lista de matches (vazia se indisponível)."""
    if not YARA_AVAILABLE:
        return []
    rules = _load_yara_rules()
    if not rules:
        return []
    try:
        matches = rules.match(path, timeout=60)
    except Exception as exc:
        logger.warning("YARA scan falhou em %s: %s", path, exc)
        return []

    out = []
    for m in matches:
        meta = m.meta or {}
        out.append({
            'rule': m.rule,
            'tags': list(m.tags or []),
            'description': meta.get('description', '') or meta.get('desc', ''),
            'author':      meta.get('author', ''),
            'reference':   meta.get('reference', '') or meta.get('url', ''),
            'severity':    meta.get('severity', '') or meta.get('score', ''),
            'strings_hit': len(getattr(m, 'strings', []) or []),
        })
    return out


# ── capa (capabilities) ──────────────────────────────────────────────────────
def capa_analyze(path: str) -> dict:
    """Roda capa e retorna capabilities agrupadas por namespace.

    capa é pesado e tem dependências chatas (vivisect/flirt). Se não estiver instalado,
    retorna {}. Os erros são silenciosos por design — é enriquecimento opcional.
    """
    try:
        import capa.main
        import capa.rules
        import capa.engine
        import capa.features.extractors.viv
        import capa.render.result_document as rd
    except ImportError:
        return {}

    try:
        # capa lê regras de um diretório padrão (instalado junto da lib em alguns wheels);
        # se não rolar, abortamos sem barulho.
        rules_path = os.environ.get('CAPA_RULES_PATH')
        if not rules_path:
            return {'note': 'capa instalado mas CAPA_RULES_PATH não configurado'}

        rules = capa.rules.RuleSet(capa.rules.get_rules([rules_path]))
        extractor = capa.features.extractors.viv.VivisectFeatureExtractor(
            capa.main.get_workspace(path, format_='auto'), path
        )
        capabilities, _ = capa.main.find_capabilities(rules, extractor)

        # Agrupa por namespace (ex: "host-interaction/process/inject")
        grouped = {}
        for rule_name, results in capabilities.items():
            rule = rules[rule_name]
            ns = rule.meta.get('namespace', 'misc')
            grouped.setdefault(ns, []).append({
                'name': rule_name,
                'description': rule.meta.get('description', ''),
                'attack': rule.meta.get('att&ck', []) or rule.meta.get('attack', []),
                'mbc':    rule.meta.get('mbc', []),
            })
        return {'capabilities': grouped, 'total': sum(len(v) for v in grouped.values())}
    except Exception as exc:
        logger.warning("capa falhou em %s: %s", path, exc)
        return {}


# ── VirusTotal (lookup por SHA-256, nunca upload) ────────────────────────────
def virustotal_lookup(sha256: str) -> dict:
    """Consulta /api/v3/files/{sha256} no VirusTotal.

    Nunca envia o arquivo — apenas o hash, que já é metadado público.
    Retorna dict vazio se VT_API_KEY não estiver no settings.
    """
    from django.conf import settings
    api_key = getattr(settings, 'VT_API_KEY', '') or os.environ.get('VT_API_KEY', '')
    if not api_key or not sha256:
        return {}

    try:
        import requests
        r = requests.get(
            f'https://www.virustotal.com/api/v3/files/{sha256}',
            headers={'x-apikey': api_key},
            timeout=15,
        )
    except Exception as exc:
        return {'error': f'erro de rede: {exc}'}

    if r.status_code == 404:
        return {'known': False, 'sha256': sha256}
    if r.status_code == 401:
        return {'error': 'VT_API_KEY inválida'}
    if r.status_code == 429:
        return {'error': 'VirusTotal rate limit'}
    if r.status_code != 200:
        return {'error': f'VT HTTP {r.status_code}'}

    try:
        data = r.json().get('data', {})
        attrs = data.get('attributes', {})
        stats = attrs.get('last_analysis_stats', {}) or {}
        names = attrs.get('names', []) or []
        threat = (attrs.get('popular_threat_classification') or {})
        suggested = threat.get('suggested_threat_label', '')
        return {
            'known': True,
            'sha256': sha256,
            'malicious':  int(stats.get('malicious', 0)),
            'suspicious': int(stats.get('suspicious', 0)),
            'undetected': int(stats.get('undetected', 0)),
            'harmless':   int(stats.get('harmless', 0)),
            'total':      sum(int(v) for v in stats.values() if isinstance(v, (int, float))),
            'reputation': attrs.get('reputation', 0),
            'first_submission': attrs.get('first_submission_date', 0),
            'last_analysis':    attrs.get('last_analysis_date', 0),
            'suggested_label':  suggested,
            'family':           threat.get('popular_threat_name', []) or [],
            'common_names':     names[:5],
            'tags':             attrs.get('tags', [])[:10],
            'permalink':        f'https://www.virustotal.com/gui/file/{sha256}',
        }
    except Exception as exc:
        return {'error': f'parse: {exc}'}


# ── Regex de credenciais / segredos hardcoded ────────────────────────────────
# Inspirado em truffleHog/gitleaks. Pesos: HIGH = certeza alta, MEDIUM = padrão genérico.
_SECRET_PATTERNS = [
    # Chaves de cloud
    (r'AKIA[0-9A-Z]{16}',                                  'AWS Access Key ID',     'HIGH'),
    (r'(?i)aws(.{0,20})?(secret|sk)[\'"\s:=]+[A-Za-z0-9/+=]{40}', 'AWS Secret Key (heur.)', 'MEDIUM'),
    (r'AIza[0-9A-Za-z\-_]{35}',                            'Google API Key',        'HIGH'),
    (r'ya29\.[0-9A-Za-z\-_]{20,}',                         'Google OAuth Token',    'HIGH'),
    (r'AAAA[A-Za-z0-9_-]{7}:[A-Za-z0-9_-]{140,}',          'Firebase FCM Server Key','HIGH'),
    (r'(?i)heroku[a-z0-9_ \-]*[\'"\s:=]+[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', 'Heroku API Key', 'MEDIUM'),

    # GitHub / GitLab
    (r'ghp_[A-Za-z0-9]{36}',                               'GitHub PAT',            'HIGH'),
    (r'gho_[A-Za-z0-9]{36}',                               'GitHub OAuth Token',    'HIGH'),
    (r'ghs_[A-Za-z0-9]{36}',                               'GitHub App Token',      'HIGH'),
    (r'github_pat_[A-Za-z0-9_]{82}',                       'GitHub Fine-grained PAT','HIGH'),
    (r'glpat-[A-Za-z0-9\-]{20}',                           'GitLab PAT',            'HIGH'),

    # Slack / Discord / Telegram
    (r'xox[baprs]-[A-Za-z0-9-]{10,}',                      'Slack Token',           'HIGH'),
    (r'https://hooks\.slack\.com/services/T[A-Z0-9/]+',    'Slack Webhook',         'HIGH'),
    (r'https://discord(app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+', 'Discord Webhook','HIGH'),
    (r'\b[0-9]{8,10}:AA[A-Za-z0-9_-]{32,35}',              'Telegram Bot Token',    'HIGH'),

    # Pagamentos
    (r'sk_live_[0-9a-zA-Z]{24,}',                          'Stripe Live Secret',    'HIGH'),
    (r'sk_test_[0-9a-zA-Z]{24,}',                          'Stripe Test Secret',    'MEDIUM'),
    (r'rk_live_[0-9a-zA-Z]{24,}',                          'Stripe Restricted Key', 'HIGH'),

    # JWT
    (r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', 'JSON Web Token', 'MEDIUM'),

    # Chaves privadas
    (r'-----BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----', 'Private Key block', 'HIGH'),

    # Twilio / SendGrid / Mailgun
    (r'AC[a-f0-9]{32}',                                    'Twilio Account SID',    'MEDIUM'),
    (r'SK[a-f0-9]{32}',                                    'Twilio API Key',        'MEDIUM'),
    (r'SG\.[A-Za-z0-9_-]{16,32}\.[A-Za-z0-9_-]{16,64}',    'SendGrid API Key',      'HIGH'),
    (r'key-[0-9a-zA-Z]{32}',                               'Mailgun API Key',       'MEDIUM'),

    # NPM / PyPI
    (r'npm_[A-Za-z0-9]{36}',                               'NPM Token',             'HIGH'),
    (r'pypi-AgEIc[A-Za-z0-9_-]{50,}',                      'PyPI Token',            'HIGH'),

    # Senha em URL
    (r'[a-zA-Z]{3,10}://[^/\s:@]{3,20}:[^/\s:@]{3,40}@[\w.-]+', 'Password in URL',   'HIGH'),

    # Genéricos (alta taxa de FP — rotulados como MEDIUM)
    (r'(?i)(api[_\-]?key|apikey|secret[_\-]?key|access[_\-]?token|auth[_\-]?token)[\'"\s:=]{1,4}[\'"]([A-Za-z0-9_\-]{16,})[\'"]',
     'Genérico: api/secret/token = "..."', 'MEDIUM'),
    (r'(?i)(password|passwd|pwd)[\'"\s:=]{1,4}[\'"]([^\'"\s]{6,})[\'"]',
     'Senha hardcoded', 'MEDIUM'),
]

# Domínios / hosts conhecidos por aparecer em strings (apenas informativo)
_INFRA_PATTERNS = [
    (r'\bs3\.amazonaws\.com/[a-z0-9.\-]+',                 'AWS S3 bucket'),
    (r'\b[a-z0-9.\-]+\.s3\.amazonaws\.com',                'AWS S3 bucket'),
    (r'\b[a-z0-9.\-]+\.firebaseio\.com',                   'Firebase Realtime DB'),
    (r'\b[a-z0-9.\-]+\.appspot\.com',                      'Google AppEngine/Firebase'),
    (r'\b[a-z0-9.\-]+\.azurewebsites\.net',                'Azure Web App'),
    (r'\bmongodb(\+srv)?://[^\s\'"]+',                     'MongoDB connection string'),
    (r'\bredis://[^\s\'"]+',                               'Redis connection string'),
    (r'\bpostgres(ql)?://[^\s\'"]+',                       'PostgreSQL connection string'),
    (r'\bmysql://[^\s\'"]+',                               'MySQL connection string'),
]


def scan_secrets(text_blob: str, max_findings: int = 60) -> dict:
    """Procura segredos hardcoded em um blob de texto (strings extraídas do binário).

    Retorna {findings: [...], infra: [...]}.
    Cada finding inclui um trecho redigido (primeiros + últimos chars apenas).
    """
    if not text_blob:
        return {'findings': [], 'infra': []}

    findings = []
    seen = set()
    for pattern, label, severity in _SECRET_PATTERNS:
        try:
            for m in re.finditer(pattern, text_blob):
                raw = m.group(0)
                key = (label, raw[:20])
                if key in seen:
                    continue
                seen.add(key)
                redacted = _redact(raw)
                findings.append({
                    'label': label,
                    'severity': severity,
                    'sample': redacted,
                    'length': len(raw),
                })
                if len(findings) >= max_findings:
                    break
        except re.error:
            continue
        if len(findings) >= max_findings:
            break

    infra = []
    seen_infra = set()
    for pattern, label in _INFRA_PATTERNS:
        for m in re.finditer(pattern, text_blob, re.IGNORECASE):
            host = m.group(0)
            if host in seen_infra:
                continue
            seen_infra.add(host)
            infra.append({'label': label, 'value': host[:200]})
            if len(infra) >= 30:
                break

    return {'findings': findings, 'infra': infra}


def _redact(s: str) -> str:
    """Mostra só os primeiros 4 e últimos 4 chars; resto vira ***. Para não vazar segredos no relatório."""
    if len(s) <= 12:
        return s[:4] + '***'
    return f'{s[:4]}…{s[-4:]} (len {len(s)})'


def enrich_report(path: str, report: dict, strings_blob: str = '') -> dict:
    """Adiciona ao report (in-place): yara, capa, virustotal, secrets, infra.

    Não levanta exceção — falhas individuais ficam registradas em `enrichment_errors`.
    """
    errs = []

    try:
        report['yara_matches'] = yara_scan(path)
    except Exception as exc:
        errs.append(f'yara: {exc}')
        report['yara_matches'] = []

    try:
        capa_data = capa_analyze(path)
        if capa_data:
            report['capa'] = capa_data
    except Exception as exc:
        errs.append(f'capa: {exc}')

    sha = report.get('sha256') or ''
    try:
        vt = virustotal_lookup(sha)
        if vt:
            report['virustotal'] = vt
    except Exception as exc:
        errs.append(f'virustotal: {exc}')

    if not strings_blob:
        # Se o analyzer não passou strings já extraídas, lê o arquivo cru.
        try:
            with open(path, 'rb') as f:
                raw = f.read(8 * 1024 * 1024)  # primeiros 8MB
            strings_blob = ' '.join(
                m.group().decode('ascii', errors='ignore')
                for m in re.finditer(rb'[ -~]{6,}', raw)
            )
        except Exception:
            strings_blob = ''

    try:
        secrets = scan_secrets(strings_blob)
        report['secrets'] = secrets['findings']
        report['infra']   = secrets['infra']
    except Exception as exc:
        errs.append(f'secrets: {exc}')

    if errs:
        report['enrichment_errors'] = errs

    return report
