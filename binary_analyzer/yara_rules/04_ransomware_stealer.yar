rule Ransomware_Generic_Notes : ransomware
{
    meta:
        description = "Strings comuns em notas de resgate de ransomware"
        author = "GDriver"
        severity = "high"
    strings:
        $a1 = "your files have been encrypted" ascii wide nocase
        $a2 = "all your files are encrypted" ascii wide nocase
        $a3 = "decryptor" ascii wide nocase
        $a4 = "bitcoin address" ascii wide nocase
        $a5 = ".onion" ascii wide
        $a6 = "ransom" ascii wide nocase
    condition:
        2 of them
}

rule InfoStealer_Browser_Paths : infostealer
{
    meta:
        description = "Caminhos de bancos de dados de browser usados por stealers"
        author = "GDriver"
        severity = "high"
    strings:
        $a1 = "Login Data" ascii wide
        $a2 = "Cookies" ascii wide
        $a3 = "Web Data" ascii wide
        $a4 = "Local State" ascii wide
        $a5 = "\\Google\\Chrome\\User Data" ascii wide
        $a6 = "\\Mozilla\\Firefox\\Profiles" ascii wide
        $a7 = "\\Microsoft\\Edge\\User Data" ascii wide
    condition:
        3 of them
}

rule Crypto_Wallet_Stealer : infostealer crypto
{
    meta:
        description = "Strings que indicam roubo de carteiras cripto"
        author = "GDriver"
        severity = "high"
    strings:
        $a1 = "wallet.dat" ascii wide nocase
        $a2 = "Electrum" ascii wide
        $a3 = "Exodus" ascii wide
        $a4 = "Atomic\\Local Storage" ascii wide
        $a5 = "MetaMask" ascii wide
    condition:
        2 of them
}

rule Discord_Token_Stealer : infostealer discord
{
    meta:
        description = "Padrões de stealer de token do Discord"
        author = "GDriver"
        severity = "high"
    strings:
        $a1 = "discord.com/api/v9/users/@me" ascii wide
        $a2 = "Local Storage\\leveldb" ascii wide
        $a3 = "discord_desktop_core" ascii wide
        $a4 = "MTk[A-Za-z0-9_-]{23}\\.[A-Za-z0-9_-]{6}\\.[A-Za-z0-9_-]{27}" ascii
    condition:
        2 of them
}
