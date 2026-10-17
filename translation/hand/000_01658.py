"""000_01658: green 追加 plate -> "ADD" in the style of the ORIGINAL plate above it
(light cyan letters on a fat dark-green blob). Run from the project root."""
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
# regular weight matches the ORIGINAL plate (Arial-like); DejaVu Sans (same licence as tools/fonts/DejaVuSans-Bold.ttf)
FONT = next(f for f in ('tools/fonts/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'tools/fonts/DejaVuSans-Bold.ttf') if os.path.exists(f))
SRC, DST = 'review/images-original/000_01658.png', 'build/work/hand/out/000_01658.png'
FILL, BLOB, MID = (166, 245, 244, 255), (35, 106, 5, 255), (64, 139, 65, 255)
im = Image.open(SRC).convert('RGBA')
im.paste((0, 0, 0, 0), (0, 352, 128, 378))            # clear 追 加 (rows 352-376)
# letters: cap height 13 like ORIGINAL (rows 334-346), left edge x=6
size = next(s for s in range(30, 6, -1)
            if (lambda b: b[3] - b[1])(ImageFont.truetype(FONT, s).getbbox('H')) <= 13)
font = ImageFont.truetype(FONT, size)
m = Image.new('L', im.size, 0)
d = ImageDraw.Draw(m); d.fontmode = '1'
b = font.getbbox('ADD')
d.text((6 - b[0], 358 - b[1]), 'ADD', font=font, fill=255)
blob = m.filter(ImageFilter.MaxFilter(7))              # 3-pixel green margin like ORIGINAL
soft = blob.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
layer.paste((9, 13, 13, 255), mask=soft.point(lambda v: v // 4))   # faint dark halo
layer.paste(BLOB, mask=blob)
layer.paste(MID, mask=m.filter(ImageFilter.MaxFilter(3)).point(lambda v: 255 if v else 0))
layer.paste(BLOB, mask=Image.eval(m.filter(ImageFilter.MaxFilter(3)), lambda v: 0))
layer.paste(FILL, mask=m)
im.alpha_composite(layer)
im.save(DST)
