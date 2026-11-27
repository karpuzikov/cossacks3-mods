"""Tooltip seams: move each tooltip piece to unused space in tex02, surrounded by copies
of its own edge pixels, so linear filtering never mixes in anything else."""
import re, struct
from pathlib import Path
import numpy as np
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Cossacks 3")
MOD = GAME / "mods" / "HD Fonts 4K"
PAD = 2
H = 760  # enough rows of the 1024-high strips for any tooltip
# part -> new (x, y)
NEW = {"background": (200, 262), "left": (344, 262), "right": (368, 262),
       "top": (480, 280), "bottom": (480, 304), "corner_lt": (640, 280),
       "corner_rt": (656, 280), "corner_lb": (672, 280), "corner_rb": (688, 280)}

mat = (GAME / "data/hud/hud.mat").read_bytes()
raw = bytearray((GAME / "data/hud/textures/ui/tex02.bmp").read_bytes())
off = struct.unpack_from("<I", raw, 10)[0]
w, h, _, bpp = struct.unpack_from("<iiHH", raw, 18)
assert (w, h, bpp) == (1024, 1024, 32)
img = np.frombuffer(raw, np.uint8, w * h * 4, off).reshape(h, w, 4)[::-1]  # top-down view
src = img.copy()

# area used by every tex02 material, to prove the destinations are free
used = np.zeros((h, w), bool)
for sec in re.findall(rb"(?ms)^section\.begin.*?^section\.end", mat):
    if re.search(rb"LibTextureName = tex02\s", sec):
        x, y, cw, ch = (int(re.search(rb"Coord%s = (\d+)" % k, sec)[1]) for k in (b"X", b"Y", b"W", b"H"))
        used[np.ix_(np.arange(y, y + ch) % h, np.arange(x, x + cw) % w)] = True

for part, (nx, ny) in NEW.items():
    name = f"Material.Name = tex02.tooltip.{part}".encode()
    found = list(re.finditer(re.escape(name) + rb"\s.*?section\.end", mat, re.S))
    assert len(found) == 1, part
    old = new = found[0].group()
    x, y, cw, ch = (int(re.search(rb"Coord%s = (\d+)" % k, old)[1]) for k in (b"X", b"Y", b"W", b"H"))
    ch = min(ch, H)
    piece = src[np.ix_(np.arange(y, y + ch) % h, np.arange(x, x + cw) % w)]
    dst = (slice(ny - PAD, ny + ch + PAD), slice(nx - PAD, nx + cw + PAD))
    assert dst[0].stop <= h and not used[dst].any() and not img[dst][..., 3].any(), f"{part}: not free"
    img[dst] = np.pad(piece, ((PAD, PAD), (PAD, PAD), (0, 0)), "edge")
    used[dst] = True
    for key, val in ((b"CoordX", nx), (b"CoordY", ny), (b"CoordH", ch)):
        new, n = re.subn(key + rb" = \d+", key + b" = %d" % val, new)
        assert n == 1
    mat = mat.replace(old, new)
    assert np.array_equal(img[ny:ny + ch, nx:nx + cw], piece)

(MOD / "data/hud/hud.mat").write_bytes(mat)
dest = MOD / "data/hud/textures/ui/tex02.bmp"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_bytes(raw)
print("ok")
