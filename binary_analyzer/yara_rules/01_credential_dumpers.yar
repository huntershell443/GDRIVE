/*
   Regras de pre-triagem para binários encontrados em loot de pentest.
   Não pretende ser detecção AV — só sinaliza padrões clássicos para você decidir
   se vale abrir num lab antes de mexer.

   Para ampliar: clone https://github.com/Neo23x0/signature-base/ em yara_rules/
   (use --recurse-modules na sua cópia local).
*/

rule Mimikatz_Strings : credential_dumper
{
    meta:
        description = "Strings características do Mimikatz e variantes"
        author = "GDriver"
        reference = "https://github.com/gentilkiwi/mimikatz"
        severity = "high"
    strings:
        $a1 = "sekurlsa::logonpasswords" ascii wide nocase
        $a2 = "kerberos::list" ascii wide nocase
        $a3 = "lsadump::sam" ascii wide nocase
        $a4 = "privilege::debug" ascii wide nocase
        $a5 = "mimikatz" ascii wide nocase
        $a6 = "gentilkiwi" ascii wide nocase
    condition:
        2 of them
}

rule LaZagne_Tool : credential_dumper
{
    meta:
        description = "LaZagne password recovery tool"
        author = "GDriver"
        reference = "https://github.com/AlessandroZ/LaZagne"
        severity = "high"
    strings:
        $a1 = "LaZagne" ascii wide
        $a2 = "passwordsRecovery" ascii wide
        $a3 = "lazagne.softwares" ascii wide
    condition:
        any of them
}

rule WCE_Windows_Credential_Editor : credential_dumper
{
    meta:
        description = "Windows Credential Editor (wce.exe)"
        author = "GDriver"
        severity = "high"
    strings:
        $a1 = "Windows Credentials Editor" ascii wide
        $a2 = "wce.exe" ascii wide
        $a3 = "addNTLMCredential" ascii
    condition:
        any of them
}
