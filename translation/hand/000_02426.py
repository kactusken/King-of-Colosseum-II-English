"""000_02426: qualifiers intro screen - caption in English, bronze 予選 title art kept (caption.py)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from caption import run

run('000_02426', [(92, 337, 456, 18), (70, 367, 490, 18), (52, 399, 536, 18)],
    ['To enter the final tournament,', 'you must get through the qualifiers.',
     'Beat every rival and win your place!'])
