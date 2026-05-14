import sys
sys.path.insert(0, r'c:\GDrive\drive_simulator')
import importlib
try:
    importlib.import_module('file_manager.urls')
    print('IMPORT_OK')
except Exception as e:
    import traceback
    traceback.print_exc()
    print('IMPORT_ERROR')
