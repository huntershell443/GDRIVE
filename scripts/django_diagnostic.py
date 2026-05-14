import asyncio
import os
import sys

async def debug_process_creation():
    """Debug detalhado da criação de processos"""
    print("=== DEBUG DETALHADO DE PROCESSOS ===\n")
    
    test_cases = [
        {
            "name": "PowerShell básico",
            "cmd": "powershell.exe -NoLogo -NoExit -Command \"\"",
            "shell": True
        },
        {
            "name": "CMD básico", 
            "cmd": "cmd.exe /k echo.",
            "shell": True
        },
        {
            "name": "PowerShell exec",
            "cmd": ["powershell.exe", "-NoLogo", "-NoExit", "-Command", "\"\""],
            "shell": False
        },
        {
            "name": "CMD exec",
            "cmd": ["cmd.exe", "/k", "echo."],
            "shell": False
        }
    ]
    
    for test in test_cases:
        print(f"🧪 {test['name']}")
        print(f"   Comando: {test['cmd']}")
        
        try:
            if test['shell']:
                process = await asyncio.create_subprocess_shell(
                    test['cmd'],
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=os.getcwd()
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    *test['cmd'],
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=os.getcwd()
                )
            
            print(f"   ✅ Processo criado - PID: {process.pid}")
            print(f"   📊 Estado inicial: returncode={process.returncode}")
            
            # Aguarda um pouco
            await asyncio.sleep(2)
            
            print(f"   📊 Estado após 2s: returncode={process.returncode}")
            
            if process.returncode is not None:
                print(f"   🔴 PROCESSO MORREU com código: {process.returncode}")
                
                # Tenta capturar stderr
                try:
                    stderr_data = await asyncio.wait_for(process.stderr.read(), timeout=2)
                    if stderr_data:
                        print(f"   🔴 STDERR: {stderr_data.decode('utf-8', errors='ignore')}")
                    else:
                        print("   🔴 STDERR: (vazio)")
                except asyncio.TimeoutError:
                    print("   🔴 STDERR: (timeout)")
                except Exception as e:
                    print(f"   🔴 STDERR erro: {e}")
                    
                # Tenta capturar stdout também
                try:
                    stdout_data = await asyncio.wait_for(process.stdout.read(), timeout=2)
                    if stdout_data:
                        print(f"   🔴 STDOUT: {stdout_data.decode('utf-8', errors='ignore')}")
                except:
                    pass
            else:
                print("   🟢 PROCESSO AINDA RODANDO!")
                
                # Testa comunicação
                print("   📤 Testando comunicação...")
                try:
                    process.stdin.write(b"echo TEST\n")
                    await process.stdin.drain()
                    
                    # Tenta ler resposta
                    await asyncio.sleep(1)
                    try:
                        output = await asyncio.wait_for(process.stdout.read(1024), timeout=2)
                        if output:
                            print(f"   📥 Resposta: {output.decode('utf-8', errors='ignore')[:100]}...")
                        else:
                            print("   ⚠️  Nenhuma resposta")
                    except asyncio.TimeoutError:
                        print("   ⚠️  Timeout na leitura")
                        
                except Exception as e:
                    print(f"   ❌ Erro na comunicação: {e}")
                
                # Limpa
                process.terminate()
                await process.wait()
                
        except Exception as e:
            print(f"   💥 ERRO na criação: {e}")
            import traceback
            print(f"   💥 Traceback: {traceback.format_exc()}")
        
        print("-" * 50)

async def test_simple_commands():
    """Testa comandos simples para ver se funcionam"""
    print("\n=== TESTE DE COMANDOS SIMPLES ===\n")
    
    simple_commands = [
        "echo Hello World",
        "dir",
        "powershell -Command \"Write-Host 'Test'\"",
        "cmd /c echo Test"
    ]
    
    for cmd in simple_commands:
        print(f"🧪 Comando: {cmd}")
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                print(f"   ✅ Sucesso: {stdout.decode().strip()}")
            else:
                print(f"   ❌ Erro (code {process.returncode}): {stderr.decode()}")
                
        except Exception as e:
            print(f"   💥 Exceção: {e}")

if __name__ == "__main__":
    print(f"Python: {sys.version}")
    print(f"Directório: {os.getcwd()}")
    print()
    
    asyncio.run(debug_process_creation())
    asyncio.run(test_simple_commands())