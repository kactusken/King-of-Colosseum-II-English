"""000_03020: event results ranking - help line (light, dark outline) + venue list (dark, cream glow)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bannerlib as B

VENUES = [((154,27,205,27), 'Spike Dome'), ((187,59,143,27), 'Nippon Butokan'),
          ((168,91,177,27), 'Oedo Kokugikan'), ((151,122,206,28), 'Rinkai Colosseum'),
          ((169,155,177,26), 'Yurakuen Hall'), ((171,186,173,27), 'Meifa Ariake'),
          ((153,219,207,27), 'Sendagaya Gymnasium'), ((199,251,116,27), 'Kawashima Stadium'),
          ((198,283,116,27), 'Regional Venue')]
img = B.load('000_03020')
img.paste(B.Image.new('RGBA', img.size, (251, 242, 212, 0)))
notes = []
for st, lines in ((B.LIGHT_ON_DARK, [B.Line("Check the ranking of each show's results".replace("'", '’'),
                                            (56, 1, 400, 22), 13, max_w=440, at=256)]),
                  (B.CREAM, [B.Line(t, ink, 20, max_w=300, at=256) for ink, t in VENUES])):
    for ln in lines:
        layer, note, where = B.render_line(img.size, ln, st)
        B.merge_max(img, layer)
        print('000_03020', ln.text, where, note)
B.save(img, '000_03020')
