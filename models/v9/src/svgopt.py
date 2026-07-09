"""Lossless-ish SVG output optimization (structure, not geometry).

Traced SVGs carry huge XML overhead: thousands of <path fill transform> tags
(~60 bytes each), 3-decimal coordinates, per-path translate transforms. This
pass shrinks files WITHOUT changing what renders:

  1. bake `translate(x,y)` transforms into absolute M/L/C coordinates
  2. merge CONSECUTIVE paths with identical style attrs (consecutive only, so
     document paint order — and therefore stacking — is exactly preserved)
  3. round coordinates to 1 decimal (<=0.05px error at typical viewBox sizes)
  4. strip the XML prolog / generator comments

Paths using commands beyond absolute M/L/C/Z (e.g. potrace's relative c/l)
are left untouched except for safe tag-level cleanups: rounding relative
deltas would accumulate drift.

Verify with the quality metric: the optimized SVG must score identically.
"""
from __future__ import annotations

import re
from typing import List, Optional

_PATH_TAG_RE = re.compile(r"<path\b[^>]*/?>(?:</path>)?")
_ATTR_RE = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"')
_TRANSLATE_RE = re.compile(r"^\s*translate\(\s*([-\d.eE+]+)\s*[, ]\s*([-\d.eE+]+)\s*\)\s*$")
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_SIMPLE_D_RE = re.compile(r"^[MLCZmlcz\s\d.,eE+-]*$")
_ABS_ONLY_RE = re.compile(r"^[MLCZ\s\d.,eE+-]*$")
_PROLOG_RE = re.compile(r"<\?xml[^>]*\?>\s*|<!--.*?-->\s*", re.DOTALL)


def _fmt(v: float) -> str:
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return s if s != "-0" else "0"


def _shift_and_round_d(d: str, dx: float, dy: float) -> Optional[str]:
    """Offset all coordinates of an absolute M/L/C/Z path and round to 1dp."""
    if not _ABS_ONLY_RE.match(d):
        return None
    out: List[str] = []
    idx = 0
    is_x = True
    for tok in re.finditer(r"([MLCZ])|(" + _NUM_RE.pattern + ")", d):
        cmd, num = tok.group(1), tok.group(2)
        if cmd:
            out.append(cmd)
            is_x = True
        else:
            v = float(num) + (dx if is_x else dy)
            out.append(_fmt(v))
            is_x = not is_x
    return " ".join(out)


def optimize_svg(svg: str) -> str:
    """Auto-picks the gzip-smaller of two lossless variants:

    A) baked: translates folded into coords + consecutive same-style merge
       (best raw size, fewer elements — most editable)
    B) rounded: keep per-path translates, just round + strip prolog
       (translate layouts with 'M0 0' starts are surprisingly gzip-friendly)
    """
    import gzip as _gz
    baked = _optimize_baked(svg)
    rounded = _optimize_rounded(svg)
    return baked if len(_gz.compress(baked.encode())) <= len(_gz.compress(rounded.encode())) else rounded


def _optimize_rounded(svg: str) -> str:
    svg = _PROLOG_RE.sub("", svg)

    def repl(m: re.Match) -> str:
        tag = m.group(0)
        dm = re.search(r'\bd="([^"]*)"', tag)
        if not dm or not _ABS_ONLY_RE.match(dm.group(1)):
            return tag
        new_d = _shift_and_round_d(dm.group(1), 0.0, 0.0)
        if new_d is None:
            return tag
        return tag[: dm.start(1)] + new_d + tag[dm.end(1):]

    return _PATH_TAG_RE.sub(repl, svg)


def _optimize_baked(svg: str) -> str:
    svg = _PROLOG_RE.sub("", svg)

    # Pass 1: normalize each <path>: bake translate, round coords.
    pieces: List[dict] = []   # {'attrs': {...}, 'd': str, 'raw': tag}
    last_end = 0
    segments: List[object] = []  # str (non-path chunks) or dict (path)
    for m in _PATH_TAG_RE.finditer(svg):
        segments.append(svg[last_end:m.start()])
        tag = m.group(0)
        attrs = dict(_ATTR_RE.findall(tag))
        d = attrs.get("d")
        tr = attrs.get("transform", "")
        new = None
        if d is not None:
            tm = _TRANSLATE_RE.match(tr) if tr else None
            if tr == "" or tm:
                dx, dy = (float(tm.group(1)), float(tm.group(2))) if tm else (0.0, 0.0)
                new_d = _shift_and_round_d(d, dx, dy)
                if new_d is not None:
                    a = {k: v for k, v in attrs.items() if k not in ("d", "transform")}
                    new = {"attrs": a, "d": new_d}
        segments.append(new if new else tag)
        last_end = m.end()
    segments.append(svg[last_end:])

    # Pass 2: merge consecutive normalized paths with identical attrs.
    out: List[str] = []
    pending: Optional[dict] = None

    def flush():
        nonlocal pending
        if pending is not None:
            attrs = "".join(f' {k}="{v}"' for k, v in sorted(pending["attrs"].items()))
            out.append(f'<path d="{pending["d"]}"{attrs}/>')
            pending = None

    for seg in segments:
        if isinstance(seg, dict):
            if pending is not None and pending["attrs"] == seg["attrs"] \
                    and pending["attrs"].get("fill-rule", "nonzero") != "evenodd":
                pending["d"] += " " + seg["d"]
            else:
                flush()
                pending = dict(seg)
        else:
            if seg.strip():
                flush()
                out.append(seg)
            elif pending is None:
                out.append(seg)
    flush()
    return "".join(out)
