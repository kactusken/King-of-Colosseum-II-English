"""000_02468: 魂の殿堂 under the striped panel -> Hall of Souls (the panel art stays)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B

B.script('000_02468', [B.Line('Hall of Souls', (198, 283, 118, 27), 21, max_w=240, at=257)],
         B.CREAM_THIN, (0, 0, 0, 0), band=(0, 276, 512, 236))
