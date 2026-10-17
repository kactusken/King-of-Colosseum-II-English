"""000_03015: show-name atlas - 選手会興行 -> Wrestlers' Association Show (English above stays)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B

CAP = 22
B.script('000_03015', [B.Line('Wrestlers’ Association Show', (179, 131, 159, 27), CAP, max_w=404, at=258)],
         B.CREAM, (251, 242, 211, 4))
