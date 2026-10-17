"""000_03103: attendance plate 超満員札止め -> Sold Out! (red ExtraBold Italic, thick yellow outline)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B

CAP = 34   # Japanese red lettering is 44 px tall; same size on all three plates (03103-03105)
B.script('000_03103', [B.Line('Sold Out!', (125,7,261,44), CAP, max_w=470, at=256, font=B.ITALIC)],
         B.RED, (0, 0, 0, 0), clear_all=True)
