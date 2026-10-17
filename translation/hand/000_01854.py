"""000_01854: 'retired' plate 引退 -> Retired (plain white, no outline, as the original).
Its duplicates 000_01916 / 000_02259 follow it (dup_of)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B

STYLE = {'name': 'plain-white', 'fill': (255, 255, 255), 'layers': [],
         'ink': lambda p: p[3] > 20, 'clear_r': 0, 'keep_r': 0}
# Japanese ink 17,43 - 108,84 (41 px tall); the English fills the same width
B.script('000_01854', [B.Line('Retired', (17, 43, 91, 41), 30, max_w=110, at=64)],
         STYLE, (16, 12, 15, 0), clear_all=True)
