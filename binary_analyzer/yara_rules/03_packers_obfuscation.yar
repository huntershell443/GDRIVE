rule UPX_Packer : packer
{
    meta:
        description = "UPX packer (PE/ELF)"
        author = "GDriver"
        severity = "low"
    strings:
        $a1 = "UPX!" ascii
        $a2 = "UPX0" ascii
        $a3 = "UPX1" ascii
    condition:
        any of them
}

rule Themida_VMProtect : packer commercial_protector
{
    meta:
        description = "Themida ou VMProtect (proteção comercial)"
        author = "GDriver"
        severity = "medium"
    strings:
        $t1 = ".themida" ascii
        $t2 = "Themida" ascii nocase
        $v1 = ".vmp0" ascii
        $v2 = ".vmp1" ascii
        $v3 = "VMProtect" ascii nocase
    condition:
        any of them
}

rule Confuser_Net_Obfuscator : obfuscator dotnet
{
    meta:
        description = "ConfuserEx — ofuscador .NET muito comum em malware"
        author = "GDriver"
        severity = "medium"
    strings:
        $a1 = "ConfuserEx" ascii wide
        $a2 = "Confuser " ascii wide
        $a3 = "DoubleProxy" ascii
    condition:
        any of them
}
