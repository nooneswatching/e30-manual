#!/usr/bin/env python3
"""Build everything: OCR the manuals, compile the parts catalogue. Extra arguments go to build_manuals."""
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
rc = subprocess.call([sys.executable, str(TOOLS / "build_manuals.py"), *sys.argv[1:]])
rc |= subprocess.call([sys.executable, str(TOOLS / "build_parts.py")])
if rc == 0:
    print("\nBuild complete. Preview with:  python tools/serve.py")
sys.exit(rc)
