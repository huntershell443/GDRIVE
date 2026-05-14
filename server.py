import sys
import os

os.environ.setdefault('HF_HUB_DISABLE_SSL_VERIFICATION', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')

if __name__ == "__main__":
    try:
        # Startup diagnostics: try to detect local ollama CLI and print guidance
        # ai_assistant removed; skip Ollama CLI detection
        import uvicorn
        uvicorn.run(
            "drive_simulator.asgi:application",
            host="0.0.0.0",
            port=8787
        )
    except ImportError:
        try:
            from daphne.cli import CommandLineInterface
            args = [
                "-b", "0.0.0.0",
                "-p", "8787",
                "drive_simulator.asgi:application"
            ]
            CommandLineInterface().run(args)
        except ImportError:
            from waitress import serve
            from drive_simulator.wsgi import application
            serve(
                application,
                host='0.0.0.0',
                port=8787,
                max_request_body_size=100 * 1024 * 1024 * 1024
            )
