#!/usr/bin/env python3
"""Find runs of Shift-JIS text in binary files.

Usage: sjisscan.py [--min N] files...
Prints: file offset length text
"""


def is_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF


def scan(data, minchars):
    i, n = 0, len(data)
    while i < n:
        j, chars = i, 0
        while j < n:
            b = data[j]
            if is_lead(b) and j + 1 < n and 0x40 <= data[j + 1] <= 0xFC and data[j + 1] != 0x7F:
                j += 2
                chars += 1
            elif 0x20 <= b < 0x7F:
                j += 1
            else:
                break
        if chars >= minchars:
            try:
                yield i, j - i, data[i:j].decode('cp932')
            except UnicodeDecodeError:
                pass
            i = j
        else:
            i += 1


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='Find runs of Shift-JIS text in binary files.')
    ap.add_argument('files', nargs='+')
    ap.add_argument('--min', type=int, default=3, metavar='N', help='shortest run in characters (default: 3)')
    args = ap.parse_args(argv)
    minchars = args.min
    for path in args.files:
        data = open(path, 'rb').read()
        for off, ln, text in scan(data, minchars):
            print(f'{path}\t{off:06x}\t{ln}\t{text}')


if __name__ == '__main__':
    main()
