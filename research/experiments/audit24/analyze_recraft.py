"""Structural stats for Recraft target SVGs vs our fresh HEAD outputs.

For each SVG: #paths, #subpaths, command mix (M/L/C/...), #unique fill colors,
file size, points count, stroke usage. Prints a table; also dumps per-target
palette (hex sorted by area proxy = subpath count using that fill).
"""
import pathlib, re, sys
from collections import Counter

CMD_RE = re.compile(r'[MmLlHhVvCcSsQqTtAaZz]')
PATH_RE = re.compile(r'<path[^>]*>', re.S)
D_RE = re.compile(r'\bd="([^"]+)"')
FILL_RE = re.compile(r'fill="([^"]+)"')
STROKE_RE = re.compile(r'stroke="([^"]+)"')

def stats(p):
    txt = p.read_text()
    paths = PATH_RE.findall(txt)
    cmds = Counter()
    fills = Counter()
    strokes = Counter()
    pts = 0
    for el in paths:
        m = D_RE.search(el)
        if m:
            c = Counter(CMD_RE.findall(m.group(1)))
            cmds.update(c)
            pts += sum(c[k] for k in 'MmLlCcSsQqTtAa')
        f = FILL_RE.search(el)
        if f and f.group(1) != 'none':
            fills[f.group(1).lower()] += 1
        s = STROKE_RE.search(el)
        if s and s.group(1) != 'none':
            strokes[s.group(1).lower()] += 1
    return {
        'file': p.name, 'kb': p.stat().st_size / 1024,
        'paths': len(paths), 'subpaths': cmds['M'] + cmds['m'],
        'pts': pts,
        'L': cmds['L'] + cmds['l'] + cmds['H'] + cmds['h'] + cmds['V'] + cmds['v'],
        'C': cmds['C'] + cmds['c'] + cmds['S'] + cmds['s'],
        'Q': cmds['Q'] + cmds['q'], 'A': cmds['A'] + cmds['a'],
        'fills': len(fills), 'strokes': len(strokes),
        'palette': fills.most_common(),
    }

def show(title, files):
    print(f'\n== {title} ==')
    print(f"{'target':22s} {'KB':>6s} {'paths':>5s} {'sub':>4s} {'pts':>5s} "
          f"{'L':>5s} {'C':>5s} {'Q':>4s} {'A':>3s} {'#col':>4s} {'strk':>4s}")
    for p in files:
        s = stats(p)
        print(f"{p.stem:22s} {s['kb']:6.1f} {s['paths']:5d} {s['subpaths']:4d} "
              f"{s['pts']:5d} {s['L']:5d} {s['C']:5d} {s['Q']:4d} {s['A']:3d} "
              f"{s['fills']:4d} {s['strokes']:4d}")

if __name__ == '__main__':
    root = pathlib.Path(__file__).resolve().parents[3]
    rec = sorted((root / 'data/targets').glob('*.svg'))
    ours = sorted((root / 'research/experiments/audit24/svg').glob('*.svg'))
    show('RECRAFT targets', rec)
    if ours:
        show('OURS (HEAD)', ours)
    if '--palette' in sys.argv:
        for p in rec:
            s = stats(p)
            print(f"\n{p.stem}: {len(s['palette'])} colors")
            for col, n in s['palette'][:24]:
                print(f'  {col:9s} x{n}')
