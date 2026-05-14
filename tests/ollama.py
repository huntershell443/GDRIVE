import requests
import json

def perguntar_ollama(prompt: str, model: str = "llama3"):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True  # habilita streaming de resposta
    }

    try:
        resposta_completa = ""
        with requests.post(url, json=payload, stream=True) as response:
            for linha in response.iter_lines():
                if linha:
                    try:
                        dados = json.loads(linha.decode('utf-8'))
                        print(dados["response"], end="", flush=True)
                        resposta_completa += dados["response"]
                    except json.JSONDecodeError:
                        continue
        print("\n\n✅ Resposta completa recebida.")
        return resposta_completa
    except Exception as e:
        print(f"❌ Erro ao se comunicar com o Ollama: {e}")
        return None

# --- Execução interativa ---
if __name__ == "__main__":
    while True:
        pergunta = input("\n🤖 Pergunte algo (ou 'sair'): ")
        if pergunta.lower() in ["sair", "exit", "quit"]:
            break
        print("\n🧠 Respondendo...\n")
        perguntar_ollama(pergunta)
