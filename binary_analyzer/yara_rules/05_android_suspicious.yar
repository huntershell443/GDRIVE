rule Android_RAT_Strings : android rat
{
    meta:
        description = "Indicadores genéricos de RAT/spyware Android"
        author = "GDriver"
        severity = "high"
    strings:
        $a1 = "android.permission.BIND_ACCESSIBILITY_SERVICE" ascii
        $a2 = "android.permission.SYSTEM_ALERT_WINDOW" ascii
        $a3 = "android.permission.READ_SMS" ascii
        $a4 = "android.permission.RECORD_AUDIO" ascii
        $a5 = "DeviceAdminReceiver" ascii
        $a6 = "AccessibilityService" ascii
    condition:
        4 of them
}

rule Android_Banking_Trojan : android banker
{
    meta:
        description = "Strings comuns em banking trojans Android"
        author = "GDriver"
        severity = "high"
    strings:
        $a1 = "overlay" ascii wide nocase
        $a2 = "inject" ascii wide nocase
        $a3 = "android.intent.action.SMS_RECEIVED" ascii
        $a4 = "getRunningTasks" ascii
        $a5 = "getRunningAppProcesses" ascii
        $a6 = "android.permission.BIND_ACCESSIBILITY_SERVICE" ascii
    condition:
        4 of them
}

rule Android_Frida_Detection : android instrumentation
{
    meta:
        description = "App tenta detectar Frida (anti-instrumentação)"
        author = "GDriver"
        severity = "low"
    strings:
        $a1 = "frida-server" ascii
        $a2 = "re.frida.server" ascii
        $a3 = "fridagadget" ascii nocase
        $a4 = "/data/local/tmp/re.frida" ascii
    condition:
        any of them
}
