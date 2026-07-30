#!/bin/bash

echo "=== DEBUG STARTUP SCRIPT ==="
echo "Date: $(date)"
echo "User: $(whoami)"
echo "PWD: $(pwd)"
echo "Python: $(which python)"
echo "Python version: $(python --version 2>&1)"

echo -e "\n=== ENVIRONMENT ==="
echo "PATH: $PATH"
echo "PYTHONPATH: $PYTHONPATH"

echo -e "\n=== CHECKING PYTHON IMPORTS ==="
python -c "import sys; print('sys.path:', sys.path)" 2>&1

echo -e "\n=== TESTING CORE IMPORTS ==="
python -c "
import sys
try:
    print('Testing uvicorn...', end=' ')
    import uvicorn
    print('OK')
except Exception as e:
    print(f'FAILED ({type(e).__name__})')

try:
    print('Testing fastapi...', end=' ')
    import fastapi
    print('OK')
except Exception as e:
    print(f'FAILED ({type(e).__name__})')

try:
    print('Testing src.api.main...', end=' ')
    import src.api.main
    print('OK')
except Exception as e:
    print(f'FAILED ({type(e).__name__})')
" 2>&1

echo -e "\n=== ATTEMPTING TO START API ==="
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8003 2>&1 | head -50
