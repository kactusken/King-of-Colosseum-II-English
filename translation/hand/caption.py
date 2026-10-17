"""Shared by 000_02426.py / 000_02427.py: the 640x448 intro screens. The big bronze title (予選 /
決勝！) is artwork over the crowd and lightning and stays as drawn; the three caption lines in the
dark band (y 324-432) are inpainted away and redrawn in English, light grey with a dark shadow."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B
from PIL import Image

STYLE = {'name': 'caption', 'fill': (220, 219, 224),
         'layers': [(1, (10, 9, 8), 150, (0, 0)), (1, (10, 9, 8), 230, (1, 1))]}
CAP = 15          # Japanese ink 18 px
CENTRE = 320


def run(ident, inks, english):
    img = B.load(ident)
    px = img.load()
    mask = Image.new('L', img.size, 0)
    for x0, y0, w, h in inks:          # each caption line's strip, with its shadow and the 。
        mask.paste(255, (x0 - 4, y0 - 3, x0 + w + 16, y0 + h + 4))
    B.inpaint(img, mask)
    for (x0, y0, w, h), text in zip(inks, english):
        ln = B.Line(text, (x0, y0, w, h), CAP, max_w=600, at=CENTRE)
        layer, note, where = B.render_line(img.size, ln, STYLE)
        img.alpha_composite(layer)
        print(ident, text, where, note)
    B.save(img, ident)
