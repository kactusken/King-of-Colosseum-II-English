"""000_01628: league title banners -> English (pixel script; see banner_lists.py)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banner_lists import run

INKS = [(125,5,262,26), (29,35,452,27), (95,67,324,28), (35,99,444,28), (93,131,326,27),
        (7,163,499,28), (213,195,80,27), (106,226,298,28), (91,258,328,28),
        (140,322,234,27), (110,354,294,28), (62,386,387,28), (168,418,176,28), (61,450,388,28)]
ENGLISH = ['G1 Climax', 'Best of the Super Juniors', 'GHC Heavyweight League',
           'GHC Junior Heavyweight League', 'Champion Carnival', 'Junior Heavyweight Champion Carnival',
           'Fire Festival', 'Tenkaichi Jr. League', 'WJ Strongest Wrestler League',
           'G1 Tag League', 'GHC Tag Team League', 'Real World Tag League', 'Fire Festival Tag',
           'WJ Strongest Tag League']
if __name__ == '__main__':
    run('000_01628', INKS, ENGLISH)
