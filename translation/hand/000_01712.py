"""000_01712: hint bar ○決定 ×戻る -> "○ OK  × Back" (plain white on the bar's own translucent
black); title プロレス道場 (black letters, cream outline) -> "Pro Wrestling Dojo" in the same
style. START SKIP stays. Run from the project root."""
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_common import plain_text, font_for_cap, dojo_title  # noqa: E402

im = Image.open('review/images-original/000_01712.png').convert('RGBA')
im.paste((0, 0, 0, 0), (155, 38, 360, 75))          # old title (rows 40-72, x 161-352) + halo
dojo_title(im, 256, 56, cap=21)
font = font_for_cap(11)
BAR = (0, 0, 0, 204)
plain_text(im, (37, 9, 72, 26), 'OK', font, BAR, x=40, cy=17.5)
plain_text(im, (109, 9, 164, 26), 'Back', font, BAR, x=112, cy=17.5)
im.save('build/work/hand/out/000_01712.png')
