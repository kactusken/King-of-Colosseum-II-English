"""000_01499: title plate - プロレス道場 -> Pro Wrestling Dojo (EXHIBITION MATCH above stays).
Pale lettering with a thin black outline, as the Japanese line."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B

STYLE = {'name': 'pale', 'fill': (212, 218, 239),
         'layers': [(2, (0, 0, 0), 90, (0, 0)), (1, (0, 0, 0), 252, (0, 0))],
         'ink': lambda p: p[3] > 200 and sum(p[:3]) > 300, 'clear_r': 3, 'keep_r': 2}
B.script('000_01499', [B.Line('Pro Wrestling Dojo', (162, 34, 188, 29), 22, max_w=360, at=256)],
         STYLE, (18, 13, 20, 22), band=(0, 0, 512, 128))
