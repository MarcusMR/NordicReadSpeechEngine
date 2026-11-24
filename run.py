# SPDX-License-Identifier: GPL-3.0-or-later
"""Run this standalone source checkout, without installing its Python package."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

if __name__ == '__main__':
    from nordicread_speech_engine.__main__ import main
    raise SystemExit(main())
