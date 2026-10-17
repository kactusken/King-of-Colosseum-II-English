#!/usr/bin/env python3
"""Shared pieces of the reference pages in docs/ (Match Maker route map, Survival Road, Secret
Shop, wrestler database): the common stylesheet, the theme switch, the site nav, and writing a
page from its template.

  pagekit.py                  rebuild every reference page (runs each page tool)

A template is a standalone HTML page with these placeholders:
  <!--HEAD-->     the theme script (dark unless the visitor picked light) and the font links
  /*COMMON_CSS*/  tools/pages_common.css, inside the page's <style>
  <!--NAV-->      the links between the pages (inside <header>, after the theme button)
  /*THEME_JS*/    the theme button's code (expects <button id="theme">) and wlink(name, link), a
                  wrestler's name linked to the wrestler database
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
PAGES = [('matchmaker-map', 'Match Maker map', 'mmmap'),
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


def nav(current):
    links = [f'<a href="../{folder}/"' + (' aria-current="page"' if folder == current else '') + f'>{label}</a>'
             for folder, label, _ in PAGES]
    return '<nav class="site" aria-label="Reference pages">' + ''.join(links) + '</nav>'


def write(folder, template, data, out=None):
    """Fill `template` (a Path) with the shared pieces and `data`; write docs/<folder>/index.html
    (or `out`). Returns (path, size in bytes)."""
    html = template.read_text(encoding='utf-8')
    missing = [p for p in ('<!--HEAD-->', '/*COMMON_CSS*/', '<!--NAV-->', '/*THEME_JS*/', '/*DATA*/') if p not in html]
    if missing:
        sys.exit(f'{paths.show(template)}: no {", ".join(missing)} placeholder - see tools/pagekit.py')
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = (html.replace('<!--HEAD-->', HEAD)
                .replace('/*COMMON_CSS*/', (TOOLS / 'pages_common.css').read_text(encoding='utf-8'))
                .replace('<!--NAV-->', nav(folder))
                .replace('/*THEME_JS*/', THEME_JS)
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
