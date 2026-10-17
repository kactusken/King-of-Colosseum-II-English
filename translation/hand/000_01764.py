"""000_01764: 更新 (update) buttons -> "Update": orange active button (white letters) and grey
inactive one (grey letters), black outline, on the button's own row gradient (each row repainted
from a clean column left of the old lettering). SAVE / LOAD stays. Run from the project root."""
import sys
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_common import font_for_cap, text_mask  # noqa: E402

im = Image.open('review/images-original/000_01764.png').convert('RGBA')
px = im.load()
EDGE = (15, 11, 3, 255)
# (clean source column, lettering columns x0..x1, rows y0..y1, letter colour, centre x)
BUTTONS = [(13, 16, 56, 103, 121, (255, 255, 255, 255), 36.5),
           (92, 94, 134, 103, 122, (144, 142, 141, 255), 114.5)]
font = font_for_cap(10)
for src, x0, x1, y0, y1, fill, cx in BUTTONS:
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            px[x, y] = px[src, y]
    m = text_mask(im.size, 'Update', font, cx, 112, 'center')
    hard = m.point(lambda v: 255 if v > 60 else v * 4)
    edge = ImageChops.lighter(hard.filter(ImageFilter.MaxFilter(3)),
                              ImageChops.offset(hard, 1, 1).filter(ImageFilter.MaxFilter(3)))
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    layer.paste(EDGE, mask=edge)
    layer.paste(fill, mask=m)
    im.alpha_composite(layer)
im.save('build/work/hand/out/000_01764.png')
