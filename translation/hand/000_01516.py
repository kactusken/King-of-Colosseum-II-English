"""000_01516: rule settings values (automatic render) + the unit cells of the digit strip at the
bottom, which the game puts after numbers ("30分" time limits, "5点" points). The strip's digits are
the game's own font at full size (sys font, white with a 2-pixel dark outline), so the units are
drawn from that font too: 分 -> "min" (scaled down evenly to fit the 24-pixel cell, on the digits' baseline), 点 -> "PT" (a lowercase p
would hang below the strip's last row)."""
import sys
from pathlib import Path
from PIL import Image, ImageFilter
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, 'tools')
import ui_common as U  # noqa: E402
import catalog, font  # noqa: E402

NAME = '000_01516'
CELLS = [((241, 487, 24, 25), 'min'), ((266, 487, 22, 25), 'PT')]   # x, y, w, h (outline included)
TOP = 484                      # row of the sys font cell's top for the strip (digit "2": glyph rows 5-28)
F = font.Font('sys')
DARK, FAR = (10, 9, 2, 248), (10, 9, 2, 108)       # the digits' outline and its soft edge


def glyph(ch):
    g = F.glyph(font.encode_text(ch)[0])
    m = Image.new('L', (32, 32), 0)
    for y in range(32):
        for x in range(32):
            m.putpixel((x, y), (g[y * 16 + x // 2] >> 4 * (x & 1) & 15) * 17)
    return m.crop((m.getbbox()[0], 0, m.getbbox()[2], 32))


def word(text, width):
    parts = [glyph(c) for c in text]
    w = sum(p.width for p in parts) + (len(parts) - 1)
    m = Image.new('L', (w, 32), 0)
    x = 0
    for p in parts:
        m.paste(p, (x, 0))
        x += p.width + 1
    if w > width:              # too wide: scale evenly, keeping the baseline (glyph row 28)
        k = width / w
        small = m.resize((width, round(32 * k)), Image.LANCZOS)
        m = Image.new('L', (width, 32), 0)
        m.paste(small, (0, 28 - round(28 * k)))
    return m.point(lambda v: min(255, v * 2))


def main():
    row = catalog.by_id(catalog.rows())[NAME]
    im = U.render_labels(NAME, row['japanese'], row['english'], row['boxes'], row['align'], row['font'])
    for (x, y, w, h), text in CELLS:
        im.paste((0, 0, 0, 0), (x, y, x + w, y + h))
        m = word(text, w - 4)
        cell = Image.new('L', (w, 32), 0)
        cell.paste(m, ((w - m.width) // 2, 0))
        fill = cell.crop((0, y - TOP, w, y - TOP + h))
        core = fill.point(lambda v: 255 if v > 90 else 0)
        near = core.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MaxFilter(3))   # 2 px, as the digits
        far = near.filter(ImageFilter.MaxFilter(3))
        layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        layer.paste(FAR, (0, 0), far)
        layer.paste(DARK, (0, 0), near)
        layer.alpha_composite(Image.merge('RGBA', [Image.new('L', (w, h), 253)] * 3 + [fill]))
        im.alpha_composite(layer, (x, y))
    out = Path('build/work/hand/out') / f'{NAME}.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)


if __name__ == '__main__':
    main()
