"""Shared by 000_02381 / 000_02382: the match-condition and statistics lists, drawn in the game's own
system font at half size like the Japanese (16-pixel rows, plain white on transparent). The
automatic renderer's condensed bold face was unreadable at this size ("Mode" read "Hode").

Each label is the row's English (graphics.csv), drawn from the font's full-width glyphs with the
game's proportional width rule (tools/font.py), then halved; a label wider than the picture is
squeezed horizontally to fit. '=' leaves a label as it is."""
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, 'tools')
import catalog, font  # noqa: E402

F = font.Font('sys')
ROW = 16                     # list pitch: the game font's 32-pixel cell at half size


def label_mask(text):
    """L mask, 16 rows high, of `text` in the system font at half size."""
    codes = font.encode_text(text)
    width = sum(F.width(c)[1] * 2 for c in codes) + 4
    img = [[0] * width for _ in range(32)]
    font.draw(F, codes, img, 0, 0)
    m = Image.new('L', (width, 32))
    m.putdata([v * 17 for row in img for v in row])
    m = m.crop((0, 0, max(1, m.getbbox()[2] if m.getbbox() else 1), 32))
    return m.resize((max(1, m.width // 2), ROW), Image.LANCZOS)


def main(name):
    row = catalog.by_id(catalog.rows())[name]
    im = Image.open(f'review/images-original/{name}.png').convert('RGBA')
    boxes = [tuple(map(int, b.split(','))) for b in row['boxes'].split(';')]
    texts = [t.strip() for t in row['english'].split(' | ')]
    assert len(boxes) == len(texts), f'{name}: {len(boxes)} boxes, {len(texts)} labels'
    for (x, y, w, h), text in zip(boxes, texts):
        if text == '=':
            continue
        top = round(y / ROW) * ROW                      # the label's row on the list grid
        im.paste((255, 255, 255, 0), (0, top, im.width, top + ROW))
        m = label_mask(text)
        room = im.width - 2
        if m.width > room:
            m = m.resize((room, ROW), Image.LANCZOS)
        layer = Image.new('RGBA', m.size, (255, 255, 255, 0))
        layer.putalpha(m.point(lambda v: min(255, round(v * 1.4))))
        im.alpha_composite(layer, (1, top))
    out = Path('build/work/hand/out') / f'{name}.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
