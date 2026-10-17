"""000_03091 attendance plate: redraw the orange italic title '観客動員数' as 'Attendance' and
clear the 人 counter after the digit strip (the number stands alone in English).
Reads review/images-original/000_03091.png, writes build/work/hand/out/000_03091.png.
Run from the project root with .venv/bin/python."""
from PIL import Image, ImageDraw, ImageFont

SRC = 'review/images-original/000_03091.png'
OUT = 'build/work/hand/out/000_03091.png'
FONT = 'tools/fonts/BarlowCondensed-ExtraBoldItalic.ttf'
ORANGE = (231, 160, 5, 255)
TEXT_AREA = (24, 14, 441, 52)       # inside the plate's inner border (exclusive right/bottom)
TEXT_X, TOP, BOTTOM = 28, 16, 48    # original lettering: x from 28, rows 16..48
COUNTER = (320, 85, 360, 124)       # the 人 glyph after the digits

im = Image.open(SRC).convert('RGBA')
d = ImageDraw.Draw(im)
d.rectangle((TEXT_AREA[0], TEXT_AREA[1], TEXT_AREA[2] - 1, TEXT_AREA[3] - 1), fill=(0, 0, 0, 255))
d.rectangle((COUNTER[0], COUNTER[1], COUNTER[2] - 1, COUNTER[3] - 1), fill=(0, 0, 0, 0))

text = 'Attendance'
cap = BOTTOM - TOP + 1 - 3              # a little under the kanji height, like the menu lettering
size = 10
while True:                             # largest size whose cap height fits
    f = ImageFont.truetype(FONT, size + 1)
    b = f.getbbox('A')
    if b[3] - b[1] > cap:
        break
    size += 1
font = ImageFont.truetype(FONT, size)
b = font.getbbox(text)
# draw 4x and downsample for soft edges like the original's anti-aliasing
S = 4
big = Image.new('L', (im.width * S, im.height * S), 0)
fb = ImageFont.truetype(FONT, size * S)
bb = fb.getbbox('A')
y_big = (TOP + (BOTTOM - TOP + 1 - cap) // 2) * S - bb[1]
ImageDraw.Draw(big).text((TEXT_X * S - fb.getbbox(text)[0], y_big), text, font=fb, fill=255)
mask = big.resize(im.size, Image.LANCZOS)
layer = Image.new('RGBA', im.size, ORANGE)
clip = Image.new('L', im.size, 0)
ImageDraw.Draw(clip).rectangle((TEXT_AREA[0], TEXT_AREA[1], TEXT_AREA[2] - 1, TEXT_AREA[3] - 1), fill=255)
from PIL import ImageChops
mask = ImageChops.multiply(mask, clip)
im.paste(layer, (0, 0), mask)
im.save(OUT)
print('wrote', OUT, 'font size', size)
