import os
import sys
import asyncio
import platform

async def test_shell_creation():
    print("=== DIAGNÓSTICO COMPLETO DE SHELLS WINDOWS ===\n")
    
    # Testa diferentes métodos de criação de processo
    test_cases = [
        {
            "name": "PowerShell subprocess_shell",
            "cmd": "powershell.exe -Command \"Write-Host 'READY'\"",
            "method": "shell"
        },
        {
            "name": "CMD subprocess_shell", 
            "cmd": "cmd.exe /c echo READY",
            "method": "shell"
        },
        {
            "name": "PowerShell subprocess_exec",
            "cmd": ["powershell.exe", "-Command", "Write-Host 'READY'"],
            "method": "exec"
        },
        {
            "name": "CMD subprocess_exec",
            "cmd": ["cmd.exe", "/c", "echo READY"],
            "method": "exec"
        }
    ]
    
    for test in test_cases:
        print(f"🧪 Testando: {test['name']}")
        print(f"   Comando: {test['cmd']}")
        
        try:
            if test['method'] == 'shell':
                process = await asyncio.create_subprocess_shell(
                    test['cmd'],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *test['cmd'],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE
                )
            
            # Aguarda processo terminar
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
            
            print(f"   ✅ Código de saída: {process.returncode}")
            if stdout:
                print(f"   ✅ stdout: {stdout.decode().strip()}")
            if stderr:
                print(f"   ⚠️  stderr: {stderr.decode().strip()}")
                
        except asyncio.TimeoutError:
            print("   ❌ TIMEOUT - processo não terminou")
            process.kill()
        except Exception as e:
            print(f"   ❌ ERRO: {e}")
        
        print()

async def test_interactive_process():
    print("=== TESTE DE PROCESSO INTERATIVO ===\n")
    
    try:
        # Cria processo interativo
        process = await asyncio.create_subprocess_shell(
            "powershell.exe",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        print("✅ Processo criado, verificando estado...")
        await asyncio.sleep(2)
        
        if process.returncode is not None:
            print(f"❌ Processo morreu imediatamente com código: {process.returncode}")
            return False
        
        print("✅ Processo ainda rodando, testando comunicação...")
        
        # Envia comando
        process.stdin.write(b"echo 'TEST'\r\n")
        await process.stdin.drain()
        
        # Tenta ler resposta
        await asyncio.sleep(1)
        try:
            # Lê até 1024 bytes com timeout
            data = await asyncio.wait_for(process.stdout.read(1024), timeout=3)
            if data:
                print(f"✅ Resposta recebida: {data.decode('utf-8', errors='ignore')[:100]}...")
            else:
                print("❌ Nenhuma resposta recebida")
        except asyncio.TimeoutError:
            print("❌ Timeout ao ler resposta")
        
        # Limpa
        process.terminate()
        return True
        
    except Exception as e:
        print(f"❌ Erro no processo interativo: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(test_shell_creation())
    asyncio.run(test_interactive_process())