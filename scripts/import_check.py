import importlib, sys, traceback
sys.path.insert(0, r'c:\GDrive\drive_simulator')
mods = ['ai_assistant.views', 'ai_assistant.rag_qa']
for m in mods:
    try:
        importlib.import_module(m)
        print('Imported', m)
    except Exception:
        print('Failed to import', m)
        traceback.print_exc()
