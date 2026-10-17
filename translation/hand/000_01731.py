"""000_01731: round red 済 (done) stamp -> "DONE" in the stamp's red with a cream outline, inside
the kept ring. The yellow arrow stays. Run from the project root."""
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_common import stamp  # noqa: E402

im = Image.open('review/images-original/000_01731.png').convert('RGBA')
stamp(im, 36.5, 36.5, 26.5, 'DONE', 15, (0, 0, 0, 0), grow=3, track=3)
im.save('build/work/hand/out/000_01731.png')
