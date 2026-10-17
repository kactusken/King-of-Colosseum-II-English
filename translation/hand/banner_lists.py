"""Shared by 000_01628.py / 000_01642.py: the league / tournament name banners (one name per row,
centred on x=256, black text with a cream outline and glow)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B

CAP = 20        # Japanese ink is 27 px; Title Case with descenders must stay inside the 32 px pitch


def run(ident, inks, english):
    img = B.load(ident)
    lines = [B.Line(t, ink, CAP, max_w=496, at=256) for t, ink in zip(english, inks)]
    for n in B.draw_lines(img, lines, B.CREAM, background=(251, 242, 211, 4), clear_all=True):
        print(ident, n)
    B.save(img, ident)
