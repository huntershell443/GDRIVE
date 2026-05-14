import sys, os, time, traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import ai_assistant.local_model as lm
except Exception:
    print('ai_assistant.local_model not available; skipping test.')
    raise SystemExit(0)

def now():
    return time.strftime('%Y-%m-%d %H:%M:%S')

def p(msg):
    print(msg)
    sys.stdout.flush()

p(f"[{now()}] PID: {os.getpid()}")
p(f"[{now()}] OLLAMA_CLI_PATH env: {os.environ.get('OLLAMA_CLI_PATH')}")
p(f"[{now()}] Detected CLI: {lm.find_ollama_cli()}")
p(f"[{now()}] Model: {lm.DEFAULT_MODEL}")
p(f"[{now()}] Startup timeout: {lm.STARTUP_TIMEOUT}")

sid = 'send-test-001'
try:
    p(f"[{now()}] Starting session...")
    lm.start_ollama_session(sid, timeout=180)
    p(f"[{now()}] Session started. Sending question...")
    t0 = time.time()
    resp = lm.send_to_ollama_session(sid, 'O que você faz?', timeout=180)
    dt = time.time() - t0
    p(f"[{now()}] send_to_ollama_session returned in {dt:.1f}s")
    p('\n--- RESPONSE (repr) ---')
    p(repr(resp))
    p('--- RESPONSE (text) ---')
    p(resp)
    p('--- END RESPONSE ---\n')
except Exception:
    print(f"[{now()}] Exception occurred:")
    traceback.print_exc()
finally:
    try:
        lm.stop_ollama_session(sid)
        p(f"[{now()}] Session stopped")
    except Exception:
        traceback.print_exc()

p(f"[{now()}] Done")
