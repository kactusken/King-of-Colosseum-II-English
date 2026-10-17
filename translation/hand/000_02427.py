"""000_02427: finals intro screen - caption in English, bronze 決勝！ title art kept (caption.py)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from caption import run

run('000_02427', [(45, 336, 551, 18), (51, 367, 538, 18), (70, 399, 499, 18)],
    ['The King of Colosseum Tournament:', 'the chosen warriors face the final battle.',
     'Win it and claim the title of the strongest!'])
