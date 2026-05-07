import sys
sys.path.insert(0, r"C:\TESSR-LOGIC")

import backend.agents.coder as c
import backend.agents.architect as a
import backend.agents.smoke_tester as s
import backend.config as cfg

print('Coder prompt length:', len(c._CODER_SYSTEM_DEFAULT))
print('Architect prompt length:', len(a._ARCHITECT_SYSTEM_DEFAULT))
print('Timeout:', cfg.settings.ollama_timeout)
print('Coder ONE styles.css:', 'EXACTLY ONE styles.css' in c._CODER_SYSTEM_DEFAULT)
print('Coder shared app.js:', 'EXACTLY ONE app.js' in c._CODER_SYSTEM_DEFAULT)
print('Smoke is_data_file:', 'is_data_file' in open(s.__file__, encoding='utf-8').read())
print('Smoke != 1 css:', 'len(css_files) != 1' in open(s.__file__, encoding='utf-8').read())
print('ALL OK')
