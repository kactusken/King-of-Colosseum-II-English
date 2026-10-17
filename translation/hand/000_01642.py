"""000_01642: tournament title banners -> English (pixel script; see banner_lists.py)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banner_lists import run

INKS = [(125,5,262,26), (29,35,452,27), (65,68,380,27), (5,100,500,27), (93,131,326,27),
        (7,163,499,28), (123,195,262,27), (76,228,354,26), (61,259,384,27),
        (95,322,320,27), (80,354,350,27), (32,386,443,28), (78,418,352,28), (31,450,444,28)]
ENGLISH = ['G1 Climax', 'Best of the Super Juniors', 'GHC Heavyweight Tournament',
           'GHC Junior Heavyweight Tournament', 'Champion Carnival', 'Junior Heavyweight Champion Carnival',
           'Fire Festival Tournament', 'Tenkaichi Jr. Tournament', 'WJ Strongest Wrestler Tournament',
           'G1 Tag Tournament', 'GHC Tag Team Tournament', 'Real World Tag Tournament',
           'Fire Festival Tag Tournament', 'WJ Strongest Tag Tournament']
if __name__ == '__main__':
    run('000_01642', INKS, ENGLISH)
