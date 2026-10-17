"""000_03019: show-name atlas - １０周年記念大会 -> 10th Anniversary Show (the English names stay)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B

CAP = 22
B.script('000_03019', [B.Line('10th Anniversary Show', (144, 66, 235, 28), CAP, max_w=280, at=262)],
         B.CREAM, (251, 242, 211, 4))
