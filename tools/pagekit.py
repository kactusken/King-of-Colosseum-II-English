#!/usr/bin/env python3
"""Shared pieces of the reference pages in docs/ (the player's guide, Match Maker route map,
Survival Road, Secret Shop, wrestler database): the common stylesheet, the theme switch, the site nav, and writing a
page from its template.

  pagekit.py                  rebuild every reference page (runs each page tool)

A template is a standalone HTML page with these placeholders:
  <!--HEAD-->     the theme script (dark unless the visitor picked light) and the font links
  /*COMMON_CSS*/  tools/pages_common.css, inside the page's <style>
  <!--NAV-->      the links between the pages (inside <header>, after the theme button)
  /*THEME_JS*/    the theme button's code (expects <button id="theme">), wlink(name, link), a
                  wrestler's name linked to the wrestler database, and the controller button icons
                  (disc('sq'|'x'|'o'|'tri'), DPAD, shoulder('R1'), stick('up'), PLUS)
  /*DATA*/        the page's data as JSON, inside <script type="application/json" id="data">
The pages need internet access only for Google Fonts.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

TOOLS = Path(__file__).resolve().parent
# (folder in docs/, nav label, tool that builds it)
PAGES = [('guide', "Player's guide", 'guidepage'),
         ('matchmaker-map', 'Match Maker map', 'mmmap'),
         ('survival-road', 'Survival Road', 'survivalmap'),
         ('secret-shop', 'Secret Shop & unlocks', 'shopmap'),
         ('wrestlers', 'Wrestlers', 'rosterdb')]

HEAD = '''<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..900&family=Noto+Sans+JP:wght@400;700&display=swap">
<script>
/* Dark unless the visitor picked light (the toggle in the header). */
try { document.documentElement.dataset.theme = localStorage.getItem("kc2-theme") === "light" ? "light" : "dark"; }
catch (e) { document.documentElement.dataset.theme = "dark"; }
</script>'''

THEME_JS = '''const themeBtn = document.getElementById("theme");
function syncTheme() { themeBtn.textContent = document.documentElement.dataset.theme === "light" ? "Dark mode" : "Light mode"; }
themeBtn.onclick = () => {
  const t = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("kc2-theme", t); } catch (e) { /* private window */ }
  syncTheme();
};
syncTheme();
/* a wrestler's name as a link to their page in the wrestler database (name: escaped HTML;
   link: 'roster/<id>' or 'templates/<id>' from the page's data; no link = plain name) */
function wlink(name, link) { return link ? `<a class="wl" href="../wrestlers/#${link}">${name}</a>` : name; }'''


# Controller button icons, styled like the game's own (dark disc, coloured symbol); one source for
# every page: the pages draw them from BUTTONS_JS, the guide gets them at build time (button()).
GLYPH = {
    'sq': '<rect x="6" y="6" width="8" height="8" rx="0.5" fill="none" style="stroke:var(--b-sq)" stroke-width="1.8"/>',
    'x': '<path d="M6.3 6.3l7.4 7.4M13.7 6.3l-7.4 7.4" style="stroke:var(--b-x)" stroke-width="1.9" stroke-linecap="round"/>',
    'o': '<circle cx="10" cy="10" r="4.4" fill="none" style="stroke:var(--b-o)" stroke-width="1.8"/>',
    'tri': '<path d="M10 5.4l4.6 8.1H5.4z" fill="none" style="stroke:var(--b-tri)" stroke-width="1.7" stroke-linejoin="round"/>',
}
DISC = ('<svg class="bi" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="9.2" '
        'style="fill:var(--b-disc);stroke:var(--b-ring)" stroke-width="0.8"/>@G@</svg>')
DPAD = ('<svg class="bi" viewBox="0 0 20 20" aria-hidden="true"><path d="M7.2 1.2h5.6v6h6v5.6h-6v6H7.2v-6h-6V7.2h6z" '
        'style="fill:var(--b-disc);stroke:var(--b-ring)" stroke-width="0.8"/><path d="M10 3l1.6 2.2H8.4zM10 17l1.6-2.2H8.4zM3 '
        '10l2.2-1.6v3.2zM17 10l-2.2-1.6v3.2z" style="fill:var(--b-pad)"/></svg>')
SHOULDER = ('<svg class="bi wide" viewBox="0 0 26 20" aria-hidden="true"><rect x="0.6" y="2.6" width="24.8" height="14.8" '
            'rx="4.5" style="fill:var(--b-disc);stroke:var(--b-ring)" stroke-width="0.8"/><text x="13" y="13.6" '
            'text-anchor="middle">@G@</text></svg>')
STICK = ('<svg class="bi" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="9.2" '
         'style="fill:var(--b-disc);stroke:var(--b-ring)" stroke-width="0.8"/><circle cx="10" cy="10" r="4.2" '
         'style="fill:none;stroke:var(--b-pad)" stroke-width="1.2" opacity=".55"/><path d="M10 2.6l2.8 3.6H7.2z" '
         'style="fill:var(--b-pad)" transform="rotate(@G@ 10 10)"/></svg>')
STICK_ROT = {'up': 0, 'right': 90, 'down': 180, 'left': 270}
BUTTON_NAMES = {'sq': 'Square', 'x': 'Cross', 'o': 'Circle', 'tri': 'Triangle'}
BUTTONS_JS = (f'const GLYPH = {json.dumps(GLYPH)};\n'
              f'const disc = g => {json.dumps(DISC)}.replace("@G@", GLYPH[g]);\n'
              f'const DPAD = {json.dumps(DPAD)};\n'
              f'const shoulder = t => {json.dumps(SHOULDER)}.replace("@G@", t);\n'
              f'const STICK_ROT = {json.dumps(STICK_ROT)};\n'
              f'const stick = d => {json.dumps(STICK)}.replace("@G@", STICK_ROT[d]);\n'
              "const PLUS = '<span class=\"bplus\">+</span>';")


def button(kind, label=None):
    """A button icon as static HTML for a page's markup: kind 'sq'|'x'|'o'|'tri' (face button) or
    a shoulder label ('R1'); the name is kept as hidden text for search, copying and screen readers."""
    svg = DISC.replace('@G@', GLYPH[kind]) if kind in GLYPH else SHOULDER.replace('@G@', kind)
    return f'<span class="b">{svg}<span class="vh">{label or BUTTON_NAMES.get(kind, kind)}</span></span>'


def nav(current):
    links = [f'<a href="../{folder}/"' + (' aria-current="page"' if folder == current else '') + f'>{label}</a>'
             for folder, label, _ in PAGES]
    return '<nav class="site" aria-label="Reference pages">' + ''.join(links) + '</nav>'


def write(folder, template, data, out=None, transform=None):
    """Fill `template` (a Path) with the shared pieces and `data`; write docs/<folder>/index.html
    (or `out`). `transform(html)`, if given, changes the template text first. Returns (path, size
    in bytes)."""
    html = template.read_text(encoding='utf-8')
    if transform:
        html = transform(html)
    missing = [p for p in ('<!--HEAD-->', '/*COMMON_CSS*/', '<!--NAV-->', '/*THEME_JS*/', '/*DATA*/') if p not in html]
    if missing:
        sys.exit(f'{paths.show(template)}: no {", ".join(missing)} placeholder - see tools/pagekit.py')
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = (html.replace('<!--HEAD-->', HEAD)
                .replace('/*COMMON_CSS*/', (TOOLS / 'pages_common.css').read_text(encoding='utf-8'))
                .replace('<!--NAV-->', nav(folder))
                .replace('/*THEME_JS*/', THEME_JS + '\n' + BUTTONS_JS)
                .replace('/*DATA*/', blob))
    out = out or paths.DOCS / folder / 'index.html'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding='utf-8', newline='\n')
    return out, len(html.encode('utf-8'))


def main(argv=None):
    rest = paths.configure(sys.argv[1:] if argv is None else argv)
    if rest:
        sys.exit(f'unexpected arguments: {" ".join(rest)} (pagekit.py takes only the folder options)')
    import importlib
    for _, _, tool in PAGES:
        if (TOOLS / f'{tool}.py').exists():
            importlib.import_module(tool).main([])
    return 0


if __name__ == '__main__':
    sys.exit(main())
