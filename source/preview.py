"""Draw sample text exactly as the game lays it out: original at 2x nearest vs the new atlas."""
import re, sys
from pathlib import Path
from PIL import Image, ImageDraw
from build import GAME

NEW = Path(sys.argv[1])
cp = "1252"

def metrics(face):
    kind = re.match(r"[a-z]+", face).group()
    lib = {"opensans": ""}.get(kind, kind)
    text = (GAME / f"data/hud/ref/{cp}/reffont{lib}.lib").read_text("latin1")
    sec = re.search(rf"(?ms)^{face}\s*:\s*section\.begin.*?^section\.end", text).group()
    return [tuple(map(int, g)) for g in re.findall(
        r"Width = (-?\d+)\s+OffsX = (-?\d+)\s+OffsY = (-?\d+)\s+PixelW = (\d+)", sec)]

def draw(canvas, atlas, face, text, x, y, color):
    info = metrics(face)
    for b in text.encode("cp" + cp):
        w, offx, offy, pw = info[b]
        cell = atlas.width // 16
        g = atlas.crop(((b // 16) * cell, (b % 16) * cell, (b // 16 + 1) * cell, (b % 16 + 1) * cell))
        g = g.resize((pw * 2, pw * 2), Image.Resampling.NEAREST)
        canvas.paste(Image.new("RGB", g.size, color), (x - offx * 2, y - offy * 2), g)
        x += w * 2

lines = [("serif14", "Campaign  Multiplayer  Random Map  Tutorial  Load Game  Settings"),
         ("serif14", "1. Sale has come! Cossacks 3 is taking part in Summer Sale, -60% discounts"),
         ("serif21", "Huge patch, sale and many details: AVWTgjpqy @&%"),
         ("serif10", "Small serif 10: the quick brown fox jumps over the lazy dog 0123456789"),
         ("sans12", "Sans 12: Wheat 1250  Wood 380  Stone 42  (peasants) [idle]"),
         ("sans21", "Sans 21: Encyclopedia & Mods Workshop"),
         ("opensans12", "Open Sans 12: 2.2.3.92.6008 (3EEB) chat message")]
W, H = 1300, len(lines) * 62 + 40
out = Image.new("RGB", (W, H * 2), (62, 38, 24))
for k, root in enumerate((GAME, NEW)):
    d = ImageDraw.Draw(out)
    d.text((10, k * H + 6), "ORIGINAL" if k == 0 else "MOD", fill=(255, 255, 255))
    for n, (face, text) in enumerate(lines):
        m = re.match(r"([a-z]+)(\d+)", face)
        atlas = Image.open(root / f"data/hud/textures/font/{cp}/font.{m[1]}.{m[2]}.bmp").convert("L")
        draw(out, atlas, face, text, 30, k * H + 36 + n * 62, (240, 214, 170))
out.save(sys.argv[2])
