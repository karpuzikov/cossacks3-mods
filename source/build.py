"""Build 2x resolution font atlases for Cossacks 3.

Each glyph is re-rendered from the vector font and registered against the
original bitmap glyph, so on-screen size and position stay identical and the
game's metric files need no change.
"""
import json, re, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from fontTools.ttLib import TTFont

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Cossacks 3")
FONTS = Path(__file__).parent / "fonts"
OUT = Path(sys.argv[1])
FACES = {"serif": "LinLibertine_R.otf", "sans": "LinBiolinum_R.otf",
         "opensans": "OpenSans-Regular.ttf"}
SS = 4          # supersampling relative to the 2x output
SCALE = 2       # output atlas scale

fonts, cmaps = {}, {}
def font(face, em):
    key = (face, em)
    if key not in fonts:
        fonts[key] = ImageFont.truetype(str(FONTS / FACES[face]), em,
                                        layout_engine=ImageFont.Layout.BASIC)
    return fonts[key]

def has_glyph(face, ch):
    if face not in cmaps:
        cmaps[face] = TTFont(FONTS / FACES[face]).getBestCmap()
    return ord(ch) in cmaps[face]

REF_EM = 512
def master(face, ch):
    """Large render. Returns (image, x0, y0) with x0,y0 relative to the pen on the baseline."""
    f = font(face, REF_EM)
    box = f.getbbox(ch, anchor="ls")
    w, h = box[2] - box[0], box[3] - box[1]
    if w <= 0 or h <= 0:
        return None
    pad = 64
    im = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(im).text((pad - box[0], pad - box[1]), ch, font=f, fill=255, anchor="ls")
    return im, box[0] - pad, box[1] - pad

def render(m, cell, factor, sx, sy, ox, oy):
    """Render a master into a cell of size cell*factor. sx,sy = em size in 1x pixels,
    ox,oy = pen position / baseline in 1x pixels."""
    im, x0, y0 = m
    kx, ky = sx * factor / REF_EM, sy * factor / REF_EM
    size = cell * factor
    hi = size * SS
    # map output (supersampled) pixel -> master pixel
    a, e = 1 / (kx * SS), 1 / (ky * SS)
    c = -ox * factor / kx - x0
    f = -oy * factor / ky - y0
    # prefilter the master to avoid aliasing during the affine sample
    red = max(1, int(min(a, e)))
    src = im.reduce(red) if red > 1 else im
    big = src.transform((hi, hi), Image.Transform.AFFINE,
                        (a / red, 0, c / red, 0, e / red, f / red), Image.Resampling.BILINEAR)
    return np.asarray(big.reduce(SS), np.float32) / 255

def corr(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float((a * b).sum() / (na * nb)) if na and nb else 0.0

def moments(a):
    ys, xs = np.nonzero(a > 0.25)
    if not len(xs):
        return None
    return xs.min(), xs.max() + 1, ys.min(), ys.max() + 1

def place(m, orig, sx, sy, ox, oy, steps):
    """Hill-climb the pen position so the 1x render matches the original glyph."""
    cell = orig.shape[0]
    best = corr(render(m, cell, 1, sx, sy, ox, oy), orig)
    for d in steps:
        moved = True
        while moved:
            moved = False
            for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
                s = corr(render(m, cell, 1, sx, sy, ox + dx, oy + dy), orig)
                if s > best + 1e-6:
                    best, ox, oy, moved = s, ox + dx, oy + dy, True
                    break
    return best, ox, oy

def initial_pos(m, orig, sx, sy):
    cell = orig.shape[0]
    o = moments(orig)
    probe = moments(render(m, cell, 1, sx, sy, cell * 0.25, cell * 0.7))
    if o is None or probe is None:
        return cell * 0.25, cell * 0.7
    return (cell * 0.25 + (o[0] + o[1] - probe[0] - probe[1]) / 2,
            cell * 0.7 + (o[2] + o[3] - probe[2] - probe[3]) / 2)

FIT_CHARS = "HEBDRnhodpagmx0258"

def fit_size(face, cells, px):
    """Find the em size (separately in x and y) and the shared baseline of one atlas."""
    samples = [(master(face, ch), cells[ord(ch)]) for ch in FIT_CHARS]
    def score(sx, sy):
        res = [place(m, o, sx, sy, *initial_pos(m, o, sx, sy), (0.5, 0.25)) for m, o in samples]
        return np.mean([r[0] for r in res]), float(np.median([r[2] for r in res]))
    best = max((score(e, e)[0], e) for e in np.arange(px - 1, px * 1.5 + 1, 0.5))[1]
    sx = sy = float(best)
    for d in (0.4, 0.2, 0.1):
        sy = max((score(sx, sy + k * d)[0], sy + k * d) for k in (-1, 0, 1))[1]
        sx = max((score(sx + k * d, sy)[0], sx + k * d) for k in (-1, 0, 1))[1]
    s, base = score(sx, sy)
    return sx, sy, base, s

def upscale_original(orig):
    """Fallback for symbols the vector font cannot reproduce."""
    cell = orig.shape[0]
    im = Image.fromarray((orig * 255).astype(np.uint8))
    im = im.resize((cell * SCALE,) * 2, Image.Resampling.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=0))
    return np.asarray(im, np.float32) / 255

def drop_edge_speck(c):
    """Some original cells have a stray dot in the last column, far from the glyph."""
    cols = np.nonzero((c > 0.05).any(axis=0))[0]
    if len(cols) < 2 or cols[-1] != c.shape[1] - 1:
        return c
    gap = np.nonzero(np.diff(cols) > c.shape[1] // 4)[0]
    if not len(gap) or len(cols) - gap[-1] - 1 > 2:
        return c
    c = c.copy()
    c[:, cols[gap[-1] + 1]:] = 0
    return c

def process(path):
    codepage, name = path.parent.name, path.name
    _, face, px, _ = name.split(".")
    px = int(px)
    src = Image.open(path).convert("L")
    cell = src.width // 16
    atlas = np.asarray(src, np.float32) / 255
    # grid: high nibble = column, low nibble = row
    cells = [atlas[(i % 16) * cell:(i % 16 + 1) * cell, (i // 16) * cell:(i // 16 + 1) * cell]
             for i in range(256)]
    cells = [drop_edge_speck(c) for c in cells]
    sx, sy, base, fit = fit_size(face, cells, px)

    placed, fallback = {}, []
    for i in range(256):
        orig = cells[i]
        if orig.max() < 0.1:
            continue
        # cp1252 second: the Turkish Open Sans atlas holds Latin-1 letters
        for cp in dict.fromkeys((codepage, "1252")):
            ch = bytes([i]).decode("cp" + cp, errors="ignore")
            m = master(face, ch) if ch and has_glyph(face, ch) else None
            if m is None:
                continue
            x, y = initial_pos(m, orig, sx, sy)
            steps = (1, 0.5, 0.25, 0.125)
            s, ox, oy = max(place(m, orig, sx, sy, x, y0, steps) for y0 in (base, y))
            if s >= 0.86:
                break
        else:
            fallback.append(i)
            continue
        # keep one baseline unless this glyph clearly needs another (hinting differences)
        if abs(oy - base) < 0.4:
            oy = base
            s, ox = max((corr(render(m, cell, 1, sx, sy, ox + k, oy), orig), ox + k)
                        for k in (-0.25, -0.125, 0, 0.125, 0.25))
        placed[i] = (m, ox, oy, s)

    # match stroke weight of the original with one gamma value per atlas
    ref = [(cells[i], render(m, cell, 1, sx, sy, ox, oy)) for i, (m, ox, oy, _) in placed.items()]
    target = sum(o.sum() for o, _ in ref)
    gamma = min(np.arange(0.6, 1.31, 0.02),
                key=lambda g: abs(sum((r ** g).sum() for _, r in ref) - target))
    gamma = float(np.clip(gamma, 0.7, 1.1))

    big = cell * SCALE
    out = np.zeros((big * 16, big * 16), np.float32)
    for i in range(256):
        if i in placed:
            m, ox, oy, _ = placed[i]
            g = render(m, cell, SCALE, sx, sy, ox, oy) ** gamma
        elif i in fallback:
            g = upscale_original(cells[i])
        else:
            continue
        out[(i % 16) * big:(i % 16 + 1) * big, (i // 16) * big:(i // 16 + 1) * big] = g

    dest = OUT / "data" / "hud" / "textures" / "font" / codepage / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8), "L").save(dest)
    scores = [v[3] for v in placed.values()]
    return dict(file=f"{codepage}/{name}", size=out.shape[0], em=[round(sx, 2), round(sy, 2)],
                gamma=round(gamma, 2), fit=round(float(fit), 3), vector=len(placed),
                upscaled=len(fallback), median=round(float(np.median(scores)), 3),
                upscaled_chars="".join(bytes([i]).decode("cp" + codepage, errors="replace") for i in fallback))

def patch_filtering():
    """Linear filtering, so 2x atlases also look right where text is drawn at 1x."""
    hud = GAME / "data" / "hud"
    files = [hud / "ref" / cp / "reffontbase.lib" for cp in ("1250", "1251", "1252")]
    files.append(hud / "font1254.lib")   # 1254 stores its materials inline
    for f in files:
        data = f.read_bytes()
        data, a = re.subn(rb"(?i)(magfilter\s*=\s*)maNearest", rb"\1maLinear", data)
        data, b = re.subn(rb"(?i)(minfilter\s*=\s*)miNearest", rb"\1miLinear", data)
        assert a and b, f"no filter settings found in {f}"
        dest = OUT / f.relative_to(GAME)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print(f.name, f.parent.name, "filters changed:", a, b)

if __name__ == "__main__":
    from concurrent.futures import ProcessPoolExecutor
    files = sorted((GAME / "data" / "hud" / "textures" / "font").glob("*/font.*.bmp"))
    if len(sys.argv) > 2:
        files = [f for f in files if re.search(sys.argv[2], f"{f.parent.name}/{f.name}")]
    with ProcessPoolExecutor() as pool:
        report = list(pool.map(process, files))
    for r in report:
        print(json.dumps(r, ensure_ascii=True))
    patch_filtering()
