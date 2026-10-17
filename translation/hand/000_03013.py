"""000_03013: show-name atlas - 無我興行 -> Muga Show (the English show names above stay)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B

CAP = 22   # Japanese ink 28 px; a little larger than the list banners to sit with the serif caps above
B.script('000_03013', [B.Line('Muga Show', (194, 130, 125, 28), CAP, max_w=330, at=257)],
         B.CREAM, (251, 242, 211, 4))
