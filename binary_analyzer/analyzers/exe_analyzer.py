"""
EXE/PE static analyzer.
Uses pefile if available, falls back to basic byte analysis.
"""
import re
import hashlib
import math
import struct
from pathlib import Path
from collections import Counter

try:
    import pefile as _pefile
    PEFILE = True
except ImportError:
    PEFILE = False

SUSPICIOUS_IMPORTS = {
    'IsDebuggerPresent': 'Anti-debug',
    'CheckRemoteDebuggerPresent': 'Anti-debug',
    'NtQueryInformationProcess': 'Anti-debug/rootkit',
    'CreateRemoteThread': 'Injeção de processo',
    'WriteProcessMemory': 'Injeção de processo',
    'VirtualAllocEx': 'Injeção de processo',
    'OpenProcess': 'Acesso a processo externo',
    'LoadLibraryA': 'Carregamento dinâmico de DLL',
    'GetProcAddress': 'Resolução dinâmica de API',
    'WinExec': 'Execução de comando',
    'ShellExecute': 'Execução shell',
    'CreateProcess': 'Criação de processo',
    'RegOpenKeyEx': 'Acesso ao registro',
    'RegSetValueEx': 'Modificação do registro',
    'InternetOpen': 'Comunicação HTTP (WinInet)',
    'URLDownloadToFile': 'Download de arquivo',
    'WSAStartup': 'Comunicação de rede (Winsock)',
    'connect': 'Conexão de rede',
    'send': 'Envio de dados pela rede',
    'recv': 'Recepção de dados pela rede',
    'CryptEncrypt': 'Criptografia',
    'CryptDecrypt': 'Descriptografia',
    'SetWindowsHookEx': 'Keylogger/Hook',
    'GetAsyncKeyState': 'Captura de teclado',
    'FindFirstFile': 'Enumeração de arquivos',
    'DeleteFile': 'Deleção de arquivo',
}

SUSPICIOUS_STRING_PATTERNS = [
    (r'https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', 'IP direto como C2'),
    (r'\.onion\b', 'Endereço Tor (.onion)'),
    (r'cmd\.exe|powershell|wscript|cscript', 'Shell/Script'),
    (r'HKEY_LOCAL_MACHINE|HKLM|HKCU', 'Chaves de registro'),
    (r'%APPDATA%|%TEMP%|%SYSTEMROOT%', 'Diretórios do sistema'),
    (r'base64|Base64|B64', 'Encoding Base64'),
    (r'password|passwd|credential', 'Credenciais'),
    (r'bitcoin|monero|wallet', 'Possível ransomware/minerador'),
    (r'pastebin\.com|ngrok\.io|duckdns\.org', 'Hosting suspeito'),
    (r'keylog|screenshot|clipboard', 'Spyware'),
]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def _extract_strings(data: bytes, min_len: int = 6) -> list:
    pattern = rb'[ -~]{' + str(min_len).encode() + rb',}'
    return [m.group().decode('ascii', errors='ignore') for m in re.finditer(pattern, data)]


def _scan_suspicious_strings(strings: list) -> list:
    findings = []
    text = '\n'.join(strings)
    for pattern, label in SUSPICIOUS_STRING_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            findings.append({'label': label, 'samples': list(set(matches[:3]))})
    return findings


def _basic_exe_analysis(path: str) -> dict:
    """Fallback analysis without pefile."""
    with open(path, 'rb') as f:
        data = f.read()

    strings = _extract_strings(data, min_len=6)
    urls = [s for s in strings if s.startswith('http')][:20]
    ips  = [s for s in strings if re.match(r'\d{1,3}(?:\.\d{1,3}){3}', s)][:10]

    is_pe = data[:2] == b'MZ'
    pe_offset = struct.unpack_from('<I', data, 0x3c)[0] if len(data) > 0x40 else 0
    is_valid_pe = is_pe and len(data) > pe_offset + 4 and data[pe_offset:pe_offset+4] == b'PE\x00\x00'

    return {
        'method': 'basic (pefile não instalado)',
        'is_pe': is_pe,
        'is_valid_pe': is_valid_pe,
        'architecture': 'Desconhecida',
        'compile_timestamp': 'Desconhecido',
        'imports': [],
        'suspicious_imports': [],
        'sections': [],
        'strings_sample': list(set(urls + ips)),
        'suspicious_findings': _scan_suspicious_strings(strings),
        'overall_entropy': round(_entropy(data), 3),
        'is_packed': _entropy(data) > 7.0,
        'dll_characteristics': [],
        'subsystem': 'Desconhecido',
    }


def _pefile_analysis(path: str) -> dict:
    pe = _pefile.PE(path)

    # Architecture
    machine = pe.FILE_HEADER.Machine
    arch_map = {0x014c: 'x86 (32-bit)', 0x8664: 'x64 (64-bit)', 0x01c0: 'ARM', 0xaa64: 'ARM64'}
    arch = arch_map.get(machine, f'0x{machine:04x}')

    # Timestamp
    import datetime
    try:
        ts = datetime.datetime.utcfromtimestamp(pe.FILE_HEADER.TimeDateStamp).strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        ts = str(pe.FILE_HEADER.TimeDateStamp)

    # Imports
    imports = []
    suspicious_imports = []
    try:
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll_name = entry.dll.decode('utf-8', errors='ignore')
            funcs = []
            for imp in entry.imports:
                name = imp.name.decode('utf-8', errors='ignore') if imp.name else f'ord_{imp.ordinal}'
                funcs.append(name)
                if name in SUSPICIOUS_IMPORTS:
                    suspicious_imports.append({'api': name, 'dll': dll_name, 'risk': SUSPICIOUS_IMPORTS[name]})
            imports.append({'dll': dll_name, 'functions': funcs[:20]})
    except AttributeError:
        pass

    # Sections + entropy
    sections = []
    overall_data = b''
    for sec in pe.sections:
        name = sec.Name.decode('utf-8', errors='ignore').rstrip('\x00')
        data = sec.get_data()
        ent = round(_entropy(data), 3)
        overall_data += data
        sections.append({
            'name': name,
            'virtual_size': sec.Misc_VirtualSize,
            'raw_size': sec.SizeOfRawData,
            'entropy': ent,
            'high_entropy': ent > 7.0,
            'characteristics': f'0x{sec.Characteristics:08x}',
        })

    # Strings from all section data
    strings = _extract_strings(overall_data, min_len=6)
    urls = [s for s in strings if s.startswith('http')][:20]
    ips  = [s for s in strings if re.match(r'\d{1,3}(?:\.\d{1,3}){3}', s)][:10]

    # Subsystem
    try:
        sub_map = {1: 'Native', 2: 'Windows GUI', 3: 'Console', 9: 'Windows CE', 14: 'EFI Application'}
        subsystem = sub_map.get(pe.OPTIONAL_HEADER.Subsystem, str(pe.OPTIONAL_HEADER.Subsystem))
    except Exception:
        subsystem = 'Desconhecido'

    # DLL characteristics flags
    try:
        chars = pe.OPTIONAL_HEADER.DllCharacteristics
        dll_chars = []
        if chars & 0x0040: dll_chars.append('DYNAMIC_BASE (ASLR)')
        if chars & 0x0100: dll_chars.append('NX_COMPAT (DEP)')
        if chars & 0x0400: dll_chars.append('NO_SEH')
        if chars & 0x4000: dll_chars.append('GUARD_CF (Control Flow Guard)')
    except Exception:
        dll_chars = []

    pe.close()

    return {
        'method': 'pefile',
        'is_pe': True,
        'is_valid_pe': True,
        'architecture': arch,
        'compile_timestamp': ts,
        'imports': imports,
        'suspicious_imports': suspicious_imports,
        'sections': sections,
        'strings_sample': list(set(urls + ips)),
        'suspicious_findings': _scan_suspicious_strings(strings),
        'overall_entropy': round(_entropy(overall_data), 3),
        'is_packed': any(s['high_entropy'] for s in sections),
        'dll_characteristics': dll_chars,
        'subsystem': subsystem,
    }


def _compute_risk(report: dict) -> int:
    score = 0
    score += min(len(report.get('suspicious_imports', [])) * 6, 40)
    score += min(len(report.get('suspicious_findings', [])) * 7, 35)
    if report.get('is_packed'):
        score += 15
    if any('Anti-debug' in i.get('risk', '') for i in report.get('suspicious_imports', [])):
        score += 10
    if any('Injeção' in i.get('risk', '') for i in report.get('suspicious_imports', [])):
        score += 15
    if any('ransomware' in f.get('label', '') for f in report.get('suspicious_findings', [])):
        score += 20
    if any('C2' in f.get('label', '') for f in report.get('suspicious_findings', [])):
        score += 15
    return min(score, 100)


def analyze_exe(path: str) -> dict:
    file_info = {
        'sha256': _sha256(path),
        'size_bytes': Path(path).stat().st_size,
        'file_name': Path(path).name,
        'type': 'Executável PE (Windows)',
    }

    try:
        details = _pefile_analysis(path) if PEFILE else _basic_exe_analysis(path)
    except Exception as e:
        details = {'error': str(e), 'method': 'failed'}

    # Strings já extraídas pelos analisadores podem entrar no scan de credenciais.
    try:
        with open(path, 'rb') as f:
            data = f.read()
        strings_blob = ' '.join(_extract_strings(data, min_len=6))
    except Exception:
        strings_blob = ''

    report = {**file_info, **details}
    report['risk_score'] = _compute_risk(report)

    # Enriquecimento (YARA, capa, VT, segredos hardcoded). Tudo opcional.
    try:
        from binary_analyzer.enrichment import enrich_report
        enrich_report(path, report, strings_blob=strings_blob)
        report['risk_score'] = _enriched_risk(report)
    except Exception:
        pass

    return report


def _enriched_risk(report: dict) -> int:
    """Recalcula risco somando enriquecimentos."""
    score = report.get('risk_score') or 0
    # YARA: cada match de regra adiciona 8, máx 30
    score += min(len(report.get('yara_matches') or []) * 8, 30)
    # Segredos HIGH = 12 cada, MEDIUM = 4 cada (máx 30)
    sec_score = 0
    for s in report.get('secrets') or []:
        sec_score += 12 if s.get('severity') == 'HIGH' else 4
    score += min(sec_score, 30)
    # VirusTotal: malicious >= 5 = +30, >= 1 = +15
    vt = report.get('virustotal') or {}
    if vt.get('known'):
        m = vt.get('malicious', 0)
        if m >= 5:
            score += 30
        elif m >= 1:
            score += 15
    return min(score, 100)
