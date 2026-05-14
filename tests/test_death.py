import asyncio
import os

async def test_why_process_dies():
    """Testa para descobrir POR QUE os processos morrem"""
    print("=== INVESTIGAÇÃO: POR QUE PROCESSOS MORREM? ===\n")
    
    test_commands = [
        "powershell.exe -NoLogo -NoExit -Command \"\"",
        "cmd.exe /k echo.",
        "powershell.exe -Command \"while($true) { Start-Sleep -Seconds 3600 }\"",
        "cmd.exe /c \"echo TEST && pause >nul\"",
    ]
    
    for cmd in test_commands:
        print(f"🧪 Testando: {cmd}")
        
        try:
            # Cria processo
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd()
            )
            
            print("   ✅ Processo criado")
            
            # Verifica estado após 1 segundo
            await asyncio.sleep(1)
            print(f"   📊 Estado após 1s: returncode={process.returncode}")
            
            # Se morreu, tenta capturar stderr
            if process.returncode is not None:
                try:
                    stderr_data = await asyncio.wait_for(process.stderr.read(), timeout=2)
                    stderr_text = stderr_data.decode('utf-8', errors='ignore')
                    print(f"   🔴 STDERR: {stderr_text}")
                except asyncio.TimeoutError:
                    print("   🔴 STDERR: (timeout)")
                except Exception as e:
                    print(f"   🔴 STDERR erro: {e}")
            else:
                print("   🟢 Processo ainda rodando!")
                # Limpa
                process.terminate()
                await process.wait()
                
        except Exception as e:
            print(f"   ❌ Erro: {e}")
        
        print()

if __name__ == "__main__":
    asyncio.run(test_why_process_dies())