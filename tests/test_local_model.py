import sys
import os
import traceback
import time
# ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
try:
    import ai_assistant.local_model as lm
except Exception:
    print('ai_assistant.local_model not available; skipping test.')
    raise SystemExit(0)

print('OLLAMA_CLI (detected):', lm.find_ollama_cli())
print('DEFAULT_MODEL:', lm.DEFAULT_MODEL)
print('DEFAULT_TIMEOUT:', lm.DEFAULT_TIMEOUT)
print('STARTUP_TIMEOUT:', lm.STARTUP_TIMEOUT)

# Test non-blocking session start/stop
session_id = 'test-session-123'
try:
    print('\n--- start_ollama_session (non-blocking) ---')
    lm.start_ollama_session(session_id)
    print('started session', session_id)
    # wait a bit for process to spawn (do not send any messages)
    time.sleep(2)
finally:
    try:
        print('\n--- stop_ollama_session ---')
        lm.stop_ollama_session(session_id)
        print('stopped session')
    except Exception:
        traceback.print_exc()

print('\nTest finished')
