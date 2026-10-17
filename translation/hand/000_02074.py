"""000_02074: the English pause menu's commentator rows (実況 / 解説 and the commentators' names) in the
picture's own lettering: a monospaced pixel font on a 9-pixel grid, white with a dark outline.
Letters the picture already has (Return to the match / Camera highlight / ...) are copied cell by
cell; the ones it lacks (K M T Y j k s z .) are drawn below in the same style (2-pixel stems, cap
rows 5-19, x-height from row 9, baseline 19). A label holds 13 cells (its sprite is ~122 px wide),
so the names are initialled."""
from PIL import Image, ImageFilter

NAME = '000_02074'
SRC = f'review/images-original/{NAME}.png'
OUT = f'build/work/hand/out/{NAME}.png'
LINES = {0: 'Return to the match', 24: 'Camera highlight', 48: 'Camera mode',
         72: 'Exit from the match', 96: 'Exit from the mode'}
LABELS = {120: 'Caller', 144: 'Y. Tsuji', 168: 'Color', 192: 'K. Yamazaki', 216: 'M. Momota'}
CLEAR_RIGHT = 127          # the ON OFF / digit sprites start at x=128 - left alone
PITCH, X0 = 9, 4

# bright strokes of the missing letters: 9 columns, rows 5.. (cap/ascender top) of a 24-row line
DRAWN = {
    'T': (5, ['.#######.', '.#######.'] + ['...##....'] * 13),
    'Y': (5, ['.##...##.', '.##...##.', '..##.##..', '..##.##..', '...###...', '...###...']
          + ['...##....'] * 9),
    'K': (5, ['.##...##.', '.##..##..', '.##.##...', '.####....', '.###.....', '.####....',
              '.##.##...', '.##.##...', '.##..##..', '.##..##..', '.##...##.', '.##...##.',
              '.##....##', '.##....##', '.##....##']),
    'M': (5, ['##.....##', '###...###', '####.####', '##.###.##', '##..#..##'] + ['##.....##'] * 10),
    's': (9, ['..#####..', '.##...##.', '.##......', '.###.....', '..####...', '....####.',
              '......##.', '......##.', '.##...##.', '..#####..', '...###...']),
    'z': (9, ['.#######.', '.######..', '.....##..', '....##...', '....##...', '...##....',
              '..##.....', '..##.....', '.##......', '.#######.', '.#######.']),
    'k': (5, ['.##......'] * 5 + ['.##...##.', '.##..##..', '.##.##...', '.####....', '.###.....',
                                  '.####....', '.##.##...', '.##..##..', '.##...##.', '.##...##.']),
    'j': (5, ['.....##..', '.....##..', '.........', '.........'] + ['.....##..'] * 12
          + ['.##..##..', '..####...']),
    '.': (18, ['...##....', '...##....']),
}
WHITE, DARK, SOFT = (252, 252, 252, 246), (9, 9, 9, 246), (9, 9, 9, 162)


def drawn_cell(ch):
    top, rows = DRAWN[ch]
    bright = Image.new('L', (PITCH, 24), 0)
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c == '#':
                bright.putpixel((x, top + y), 255)
    near = bright.filter(ImageFilter.MaxFilter(3))
    far = near.filter(ImageFilter.MaxFilter(3))
    cell = Image.new('RGBA', (PITCH, 24), (0, 0, 0, 0))
    cell.paste(SOFT, (0, 0), far)
    cell.paste(DARK, (0, 0), near)
    cell.paste(WHITE, (0, 0), bright)
    return cell


def main():
    im = Image.open(SRC).convert('RGBA')
    cells = {}
    for y0, text in LINES.items():
        for i, ch in enumerate(text):
            if ch != ' ' and ch not in cells:
                x = X0 + PITCH * i
                cells[ch] = im.crop((x, y0, x + PITCH, y0 + 24))
    for ch in DRAWN:
        cells.setdefault(ch, drawn_cell(ch))
    background = im.getpixel((250, 250))
    for y0, text in LABELS.items():
        im.paste(background, (0, y0, CLEAR_RIGHT, y0 + 24))
        for i, ch in enumerate(text):
            if ch != ' ':
                x = X0 + PITCH * i
                if x + PITCH > CLEAR_RIGHT + 1:
                    raise SystemExit(f'{NAME}: "{text}" is wider than its sprite')
                im.alpha_composite(cells[ch], (x, y0))
    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    im.save(OUT)


if __name__ == '__main__':
    main()
