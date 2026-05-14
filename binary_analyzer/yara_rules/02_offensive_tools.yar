rule CobaltStrike_Beacon_Indicators : c2 beacon
{
    meta:
        description = "Strings/padrões comuns em beacons do Cobalt Strike"
        author = "GDriver"
        reference = "https://www.cobaltstrike.com"
        severity = "high"
    strings:
        $b1 = "%s as %s\\%s: %d" ascii
        $b2 = "beacon.dll" ascii wide nocase
        $b3 = "ReflectiveLoader" ascii
        $b4 = "Could not connect to pipe (%s): %d" ascii
        $b5 = { 73 70 72 6E 67 5F 4D 54 } // "sprng_MT"
    condition:
        2 of them
}

rule Metasploit_Meterpreter : c2 metasploit
{
    meta:
        description = "Meterpreter / Metasploit payload indicators"
        author = "GDriver"
        severity = "high"
    strings:
        $a1 = "metsrv.dll" ascii wide nocase
        $a2 = "meterpreter" ascii wide nocase
        $a3 = "stdapi_railgun_api" ascii
        $a4 = "/INITM" ascii
        $a5 = "ReflectiveLoader" ascii
    condition:
        2 of them
}

rule Empire_PowerShell : c2 powershell
{
    meta:
        description = "Empire / PowerShell agent strings"
        author = "GDriver"
        severity = "medium"
    strings:
        $a1 = "Invoke-Empire" ascii wide nocase
        $a2 = "Invoke-Mimikatz" ascii wide nocase
        $a3 = "Invoke-DCSync" ascii wide nocase
        $a4 = "Invoke-Kerberoast" ascii wide nocase
    condition:
        any of them
}

rule Sliver_C2 : c2
{
    meta:
        description = "Sliver C2 framework artifacts"
        author = "GDriver"
        reference = "https://github.com/BishopFox/sliver"
        severity = "high"
    strings:
        $a1 = "sliverpb." ascii
        $a2 = "BishopFox/sliver" ascii nocase
        $a3 = ".sliver/" ascii
    condition:
        any of them
}

rule PsExec_SysInternals : lateral_movement
{
    meta:
        description = "PsExec — pode ser uso legítimo ou lateral movement"
        author = "GDriver"
        severity = "medium"
    strings:
        $a = "PSEXESVC" ascii wide
        $b = "Sysinternals PsExec" ascii wide
    condition:
        any of them
}
