"""degradation_suite.py — idealization regression gauge (VectorArk idea, run 46).

Ground-truth-clean protocol: render each data/targets/*.svg CLEAN at RES;
degrade the render like a real-world raster (downscale → JPEG → upscale);
run the LIVE engine on the degraded raster; score the engine's output render
against the CLEAN render (dSSIM/dΔE). A perfect idealizer scores 1.0/0 —
every point lost is noise copied or structure destroyed, with no Recraft-
interpretation confound.

SECONDARY SIGNAL ONLY (same standing as recraft_gap): spot-finder + per-keep
gauge, never a keep/discard verdict. Usage:
  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python \
    eval/degradation_suite.py [target ...]     # default: all
Artifacts (degraded inputs + engine outputs) land in outputs/degsuite/.
"""
import io, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engines/quant/quant-hifi/src'))
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim
from skimage.color import rgb2lab, deltaE_ciede2000
from render import svg_to_rgb

RES = 1024          # clean-render + scoring resolution
DEG_SCALE = 0.45    # downscale factor before JPEG (blur via resampling)
JPEG_Q = 78

def degrade(clean_rgb: np.ndarray) -> Image.Image:
    im = Image.fromarray(clean_rgb.astype(np.uint8))
    small = im.resize((int(RES * DEG_SCALE),) * 2, Image.BICUBIC)
    buf = io.BytesIO()
    small.save(buf, 'JPEG', quality=JPEG_Q)
    return Image.open(buf).resize((RES, RES), Image.BICUBIC).convert('RGB')

def run_engine(img_path: pathlib.Path, out_svg: pathlib.Path) -> bool:
    r = subprocess.run([sys.executable, str(ROOT / 'run_model.py'), '-m', 'quant-hifi',
                        '-i', str(img_path), '-o', str(out_svg)],
                       capture_output=True, text=True, timeout=600)
    return r.returncode == 0 and out_svg.exists()

def main():
    names = sys.argv[1:] or sorted(p.stem for p in (ROOT / 'data/targets').glob('*.svg'))
    workdir = ROOT / 'outputs/degsuite'
    workdir.mkdir(parents=True, exist_ok=True)
    print(f"{'target':20s} {'dSSIM':>6s} {'dΔE':>6s}   (ours-from-degraded vs CLEAN render)")
    for n in names:
        clean = svg_to_rgb((ROOT / f'data/targets/{n}.svg').read_text(), RES, RES).astype(np.float64)
        deg_png = workdir / f'{n}.degraded.png'
        degrade(clean).save(deg_png)
        out_svg = workdir / f'{n}.ours.svg'
        if not run_engine(deg_png, out_svg):
            print(f'{n:20s}  ENGINE-FAIL')
            continue
        ours = svg_to_rgb(out_svg.read_text(), RES, RES).astype(np.float64)
        s = ssim(ours, clean, channel_axis=2, data_range=255.0)
        de = float(deltaE_ciede2000(rgb2lab(ours / 255.0), rgb2lab(clean / 255.0)).mean())
        print(f'{n:20s} {s:6.3f} {de:6.2f}')

if __name__ == '__main__':
    main()
