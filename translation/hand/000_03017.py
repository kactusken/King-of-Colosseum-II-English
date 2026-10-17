"""000_03017: show-name atlas - 真世紀創造。/ 真天地創造。 -> English (01 Division, VAST ENERGY, 01 WORLD stay)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B

CAP = 22
B.script('000_03017', [B.Line('Creation of a New Era.', (159, 66, 177, 28), CAP, max_w=300, at=247),
                       B.Line('Creation of a New World.', (159, 98, 177, 28), CAP, max_w=300, at=247)],
         B.CREAM, (251, 242, 211, 6))
