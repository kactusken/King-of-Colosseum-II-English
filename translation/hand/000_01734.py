"""000_01734: small 済 (done) stamp at the right of the gauge bar -> "DONE" in the stamp's red with
a cream outline, inside the kept ring. The bar stays. Run from the project root."""
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_common import stamp  # noqa: E402

im = Image.open('review/images-original/000_01734.png').convert('RGBA')
stamp(im, 484.5, 28.5, 19, 'DONE', 8, (0, 0, 0, 4), red=(169, 13, 1, 255), cream=(247, 244, 179, 255), grow=3, track=2)
im.save('build/work/hand/out/000_01734.png')
