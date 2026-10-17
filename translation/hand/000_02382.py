"""000_02382: drawn in the game's own font at half size - see stat_list.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stat_list  # noqa: E402

if __name__ == '__main__':
    stat_list.main('000_02382')
