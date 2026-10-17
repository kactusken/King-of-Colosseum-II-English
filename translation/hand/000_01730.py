"""000_01730: hint bar ○決定 ×キャンセル -> "○ OK  × Cancel" (plain white on the bar's own
translucent black); title プロレス道場 -> "Pro Wrestling Dojo" in the same black-on-cream style as
000_01712. The blue streak background stays. Run from the project root."""
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_common import plain_text, font_for_cap, dojo_title  # noqa: E402

im = Image.open('review/images-original/000_01730.png').convert('RGBA')
im.paste((0, 0, 0, 0), (154, 358, 360, 396))        # old title (rows 360-393, x 160-351) + halo
dojo_title(im, 256, 377, cap=21)
font = font_for_cap(11)
BAR = (0, 0, 0, 204)
plain_text(im, (38, 331, 73, 348), 'OK', font, BAR, x=41, cy=339.5)
plain_text(im, (110, 331, 165, 348), 'Cancel', font, BAR, x=113, cy=339.5)
im.save('build/work/hand/out/000_01730.png')
