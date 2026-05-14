"""
APK static analyzer.
Tries androguard first (full analysis), falls back to zipfile-based analysis.
"""
import re
import zipfile
import hashlib
import struct
from pathlib import Path

try:
    from androguard.core.bytecodes.apk import APK as _AndroAPK
    ANDROGUARD = True
except ImportError:
    ANDROGUARD = False

# Permissions considered dangerous by Android
DANGEROUS_PERMISSIONS = {
    'android.permission.READ_SMS', 'android.permission.SEND_SMS',
    'android.permission.RECEIVE_SMS', 'android.permission.READ_CALL_LOG',
    'android.permission.READ_CONTACTS', 'android.permission.WRITE_CONTACTS',
    'android.permission.ACCESS_FINE_LOCATION', 'android.permission.ACCESS_COARSE_LOCATION',
    'android.permission.RECORD_AUDIO', 'android.permission.CAMERA',
    'android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE',
    'android.permission.PROCESS_OUTGOING_CALLS', 'android.permission.READ_PHONE_STATE',
    'android.permission.USE_BIOMETRIC', 'android.permission.USE_FINGERPRINT',
    'android.permission.GET_ACCOUNTS', 'android.permission.MANAGE_ACCOUNTS',
    'android.permission.CHANGE_NETWORK_STATE', 'android.permission.INTERNET',
    'android.permission.RECEIVE_BOOT_COMPLETED', 'android.permission.SYSTEM_ALERT_WINDOW',
    'android.permission.BIND_ACCESSIBILITY_SERVICE',
    'android.permission.REQUEST_INSTALL_PACKAGES',
    'android.permission.PACKAGE_USAGE_STATS',
}

# Suspicious string patterns
SUSPICIOUS_PATTERNS = [
    (r'https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', 'IP direto como C2'),
    (r'(?:Base64|base64)\.decode', 'Decodificação Base64 em runtime'),
    (r'Runtime\.exec|ProcessBuilder', 'Execução de processos'),
    (r'DexClassLoader|PathClassLoader|loadDex', 'Carregamento dinâmico de código'),
    (r'getDeviceId|getSubscriberId|getImei', 'Coleta de ID do dispositivo'),
    (r'Cipher\.getInstance|SecretKeySpec', 'Criptografia'),
    (r'TelephonyManager|SmsManager', 'Acesso a SMS/Telefonia'),
    (r'admin\.DeviceAdminReceiver|android\.app\.admin', 'Admin de dispositivo'),
    (r'\.onion\b', 'Endereço Tor (.onion)'),
    (r'pastebin\.com|ngrok\.io|duckdns\.org', 'Hosting suspeito'),
    (r'su\b.*shell|/system/bin/su', 'Root/SU'),
    (r'Accessibility|accessibility.*service', 'Serviço de acessibilidade'),
]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _extract_strings(data: bytes, min_len: int = 6) -> list:
    """Extract printable ASCII strings from binary data."""
    pattern = rb'[ -~]{' + str(min_len).encode() + rb',}'
    return [m.group().decode('ascii', errors='ignore') for m in re.finditer(pattern, data)]


def _scan_suspicious(strings: list) -> list:
    findings = []
    text = '\n'.join(strings)
    for pattern, label in SUSPICIOUS_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            findings.append({'label': label, 'samples': list(set(matches[:3]))})
    return findings


def _parse_axml_package(data: bytes) -> str:
    """
    Minimal AXML (Android Binary XML) parser to extract package name.
    Returns empty string if parsing fails.
    """
    try:
        # AXML magic: 0x00080003
        if len(data) < 8 or data[:4] != b'\x03\x00\x08\x00':
            return ''
        # Walk chunks looking for START_ELEMENT (0x00100102)
        offset = 8
        while offset + 16 < len(data):
            chunk_type = struct.unpack_from('<H', data, offset)[0]
            chunk_size = struct.unpack_from('<I', data, offset + 4)[0]
            if chunk_type == 0x0102:  # START_ELEMENT
                # attribute area starts at offset+28, each attr=20 bytes
                attr_count = struct.unpack_from('<H', data, offset + 28)[0]
                for i in range(attr_count):
                    a_off = offset + 36 + i * 20
                    if a_off + 20 > len(data):
                        break
                    name_idx  = struct.unpack_from('<I', data, a_off + 4)[0]
                    val_type  = struct.unpack_from('<B', data, a_off + 15)[0]
                    val_data  = struct.unpack_from('<I', data, a_off + 16)[0]
                    # val_type 3 = string
                    if val_type == 3:
                        # read string pool entry is complex; skip for now
                        pass
            if chunk_size == 0:
                break
            offset += chunk_size
    except Exception:
        pass
    return ''


def _basic_apk_analysis(path: str) -> dict:
    """Zipfile-based analysis when androguard is not available."""
    report: dict = {
        'method': 'basic (androguard não instalado)',
        'package': '',
        'version_name': '',
        'version_code': '',
        'min_sdk': '',
        'target_sdk': '',
        'permissions': [],
        'dangerous_permissions': [],
        'activities': [],
        'services': [],
        'receivers': [],
        'providers': [],
        'files': [],
        'suspicious_findings': [],
        'certificate': {},
        'native_libs': [],
        'strings_sample': [],
    }

    try:
        with zipfile.ZipFile(path, 'r') as z:
            names = z.namelist()
            report['files'] = names

            # Native libs
            report['native_libs'] = [n for n in names if n.endswith('.so')]

            # Certificate fingerprint from META-INF
            cert_files = [n for n in names if n.startswith('META-INF/') and
                          (n.endswith('.RSA') or n.endswith('.DSA') or n.endswith('.EC'))]
            if cert_files:
                cert_data = z.read(cert_files[0])
                report['certificate'] = {
                    'file': cert_files[0],
                    'sha256': hashlib.sha256(cert_data).hexdigest(),
                    'size_bytes': len(cert_data),
                }

            # String extraction from classes.dex
            all_strings: list = []
            dex_files = [n for n in names if re.match(r'classes\d*\.dex', n)]
            for dex in dex_files[:3]:
                dex_data = z.read(dex)
                all_strings.extend(_extract_strings(dex_data, min_len=8))

            # Filter useful strings
            urls = [s for s in all_strings if s.startswith('http')][:20]
            ips  = [s for s in all_strings if re.match(r'\d{1,3}(?:\.\d{1,3}){3}', s)][:10]
            report['strings_sample'] = list(set(urls + ips))
            report['suspicious_findings'] = _scan_suspicious(all_strings)

            # Try binary manifest parse
            if 'AndroidManifest.xml' in names:
                manifest_data = z.read('AndroidManifest.xml')
                pkg = _parse_axml_package(manifest_data)
                if pkg:
                    report['package'] = pkg

                # Brute-force permission strings from binary manifest
                perms_raw = re.findall(rb'android\.permission\.[A-Z_]+', manifest_data)
                perms = list({p.decode() for p in perms_raw})
                report['permissions'] = perms
                report['dangerous_permissions'] = [p for p in perms if p in DANGEROUS_PERMISSIONS]

    except Exception as e:
        report['error'] = str(e)

    return report


def _androguard_analysis(path: str) -> dict:
    """Full analysis using androguard."""
    apk = _AndroAPK(path)
    perms = apk.get_permissions()
    dangerous = [p for p in perms if p in DANGEROUS_PERMISSIONS]

    cert_info = {}
    try:
        cert = apk.get_certificate(apk.get_signature_name())
        if cert:
            cert_info = {
                'sha1': apk.get_signature_names(),
                'issuer': str(cert.issuer.human_friendly),
                'subject': str(cert.subject.human_friendly),
                'not_before': str(cert['tbs_certificate']['validity']['not_before'].native),
                'not_after':  str(cert['tbs_certificate']['validity']['not_after'].native),
                'self_signed': cert.issuer == cert.subject,
            }
    except Exception:
        pass

    # String extraction from DEX
    all_strings: list = []
    try:
        with zipfile.ZipFile(path, 'r') as z:
            for n in z.namelist():
                if re.match(r'classes\d*\.dex', n):
                    all_strings.extend(_extract_strings(z.read(n), min_len=8))
    except Exception:
        pass

    urls = [s for s in all_strings if s.startswith('http')][:20]
    ips  = [s for s in all_strings if re.match(r'\d{1,3}(?:\.\d{1,3}){3}', s)][:10]

    return {
        'method': 'androguard',
        'package': apk.get_package(),
        'version_name': apk.get_androidversion_name() or '',
        'version_code': apk.get_androidversion_code() or '',
        'min_sdk': apk.get_min_sdk_version() or '',
        'target_sdk': apk.get_target_sdk_version() or '',
        'permissions': perms,
        'dangerous_permissions': dangerous,
        'activities': apk.get_activities(),
        'services': apk.get_services(),
        'receivers': apk.get_receivers(),
        'providers': apk.get_providers(),
        'files': list(zipfile.ZipFile(path).namelist()),
        'native_libs': apk.get_libraries(),
        'suspicious_findings': _scan_suspicious(all_strings),
        'certificate': cert_info,
        'strings_sample': list(set(urls + ips)),
    }


def _compute_risk(report: dict) -> int:
    score = 0
    dp = report.get('dangerous_permissions', [])
    score += min(len(dp) * 5, 30)

    findings = report.get('suspicious_findings', [])
    score += min(len(findings) * 8, 40)

    if report.get('native_libs'):
        score += 5
    if any('C2' in f.get('label', '') for f in findings):
        score += 15
    if any('Root' in f.get('label', '') for f in findings):
        score += 15
    if any('Tor' in f.get('label', '') for f in findings):
        score += 10
    if any('admin' in p.lower() for p in report.get('permissions', [])):
        score += 10

    return min(score, 100)


def analyze_apk(path: str) -> dict:
    file_info = {
        'sha256': _sha256(path),
        'size_bytes': Path(path).stat().st_size,
        'file_name': Path(path).name,
        'type': 'APK Android',
    }

    try:
        details = _androguard_analysis(path) if ANDROGUARD else _basic_apk_analysis(path)
    except Exception as e:
        details = {'error': str(e)}

    # Coleta strings dos DEX para o scan de credenciais.
    strings_blob = ''
    try:
        with zipfile.ZipFile(path, 'r') as z:
            buf = []
            for n in z.namelist():
                if re.match(r'classes\d*\.dex', n):
                    buf.extend(_extract_strings(z.read(n), min_len=6))
            strings_blob = ' '.join(buf)
    except Exception:
        pass

    report = {**file_info, **details}
    report['risk_score'] = _compute_risk(report)

    try:
        from binary_analyzer.enrichment import enrich_report
        enrich_report(path, report, strings_blob=strings_blob)
        report['risk_score'] = _enriched_risk_apk(report)
    except Exception:
        pass

    return report


def _enriched_risk_apk(report: dict) -> int:
    score = report.get('risk_score') or 0
    score += min(len(report.get('yara_matches') or []) * 8, 30)
    sec_score = 0
    for s in report.get('secrets') or []:
        sec_score += 12 if s.get('severity') == 'HIGH' else 4
    score += min(sec_score, 30)
    vt = report.get('virustotal') or {}
    if vt.get('known'):
        m = vt.get('malicious', 0)
        if m >= 5:
            score += 30
        elif m >= 1:
            score += 15
    return min(score, 100)
