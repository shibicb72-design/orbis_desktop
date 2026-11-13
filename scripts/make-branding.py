# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Render the Orbis "Orbit" artwork from branding/orbis/source/*.svg into the branding overlay.

Writes every PNG, ICO, BMP and JPG image of overlay/browser/branding/orbis (same file names and pixel
sizes as before), plus content/about-logo.svg and content/document_pdf.svg, which are copies of their
sources. Re-run it after changing a source SVG; the output is overwritten.

Needs Microsoft Edge (headless, to draw the SVGs) and Pillow. Each SVG is drawn once at 1024 px and
scaled down with Lanczos. Images of 24 px and below use orbit-small.svg (thicker ring, no satellite).
Derived variants are made from the sources by text substitution:
  private: the teal #216969 becomes deep #1B3A4B (private-browsing icons);
  mark:    orbit.svg without its tile (Start tiles, which draw their own background).

Usage (Pillow is often a per-user install, so do not pass -I):
  python scripts/make-branding.py [--edge PATH] [--dest DIR] [--sheet FILE.png]

--sheet also writes a comparison sheet: the full icon at 256 and 48 px and the small variant at 24 and
16 px, on white and on #202020, with 8x enlargements of the small sizes.
"""

import argparse
import io
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "branding" / "orbis" / "source"
DEFAULT_DEST = REPO / "overlay" / "browser" / "branding" / "orbis"
RENDER = 1024

TEAL = "#216969"
DEEP = "#1B3A4B"

ICO_ICON = (16, 24, 32, 48, 64, 256)
ICO_SMALL_SET = (16, 24, 32)


def find_edge(given):
    if given:
        return Path(given)
    for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            p = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if p.is_file():
                return p
    sys.exit("Microsoft Edge not found; pass --edge PATH\\msedge.exe")


class Renderer:
    """Draws SVG text to a 1024 px RGBA image with headless Edge."""

    def __init__(self, edge, work):
        self.edge = edge
        self.work = work
        self.n = 0

    def render(self, svg_text):
        self.n += 1
        svg = self.work / f"in{self.n}.svg"
        html = self.work / f"in{self.n}.html"
        png = self.work / f"out{self.n}.png"
        svg.write_text(svg_text, encoding="utf-8")
        html.write_text(
            '<html><body style="margin:0;background:transparent">'
            f'<img src="{svg.as_uri()}" width="{RENDER}" height="{RENDER}" style="display:block">'
            "</body></html>",
            encoding="utf-8",
        )
        profile = self.work / "edge-profile"
        subprocess.run(
            [str(self.edge), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
             "--disable-extensions", f"--user-data-dir={profile}", "--default-background-color=00000000",
             f"--window-size={RENDER},{RENDER}", f"--screenshot={png}", html.as_uri()],
            check=True, capture_output=True, timeout=120,
        )
        # msedge.exe can return before the browser process has written the file and released its profile.
        deadline = time.time() + 60
        while not (png.is_file() and not (profile / "lockfile").exists()):
            if time.time() > deadline:
                sys.exit(f"Edge wrote no screenshot for {svg.name}")
            time.sleep(0.2)
        time.sleep(0.3)
        im = Image.open(png).convert("RGBA")
        im.load()
        if im.size != (RENDER, RENDER) or im.getpixel((0, 0))[3] != 0:
            sys.exit(f"unexpected render of {svg.name}: size {im.size}, corner {im.getpixel((0, 0))}")
        return im


def private(svg):
    return svg.replace(TEAL, DEEP)


def mark(svg):
    out, n = re.subn(r"\s*<rect [^>]*/>", "", svg, count=1)
    if n != 1:
        sys.exit("orbit.svg: no tile <rect> to remove")
    return out


def scaled(im, w, h=None):
    return im.resize((w, h or w), Image.LANCZOS)


def on_canvas(art, size, w, h, bg=None, dy=0):
    """art scaled to size x size, centred on a w x h canvas (transparent or bg colour)."""
    c = Image.new("RGBA", (w, h), bg or (0, 0, 0, 0))
    c.alpha_composite(scaled(art, size), ((w - size) // 2, (h - size) // 2 + dy))
    return c


def png_bytes(im):
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return b.getvalue()


def dib_bytes(im):
    """32-bit BMP icon image (BITMAPINFOHEADER, bottom-up BGRA, then the 1-bit AND mask)."""
    w, h = im.size
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    r, g, b, a = im.split()
    bgra = Image.merge("RGBA", (b, g, r, a)).transpose(Image.FLIP_TOP_BOTTOM).tobytes()
    row = ((w + 31) // 32) * 4
    mask = bytes(row * h)  # all zero: the alpha channel decides
    return header + bgra + mask


def write_ico(path, images):
    """images: {size: RGBA image}. 256 px is PNG-compressed; smaller sizes are 32-bit BMP."""
    sizes = sorted(images)
    blobs = [png_bytes(images[s]) if s >= 256 else dib_bytes(images[s]) for s in sizes]
    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(sizes)))
    offset = 6 + 16 * len(sizes)
    for s, blob in zip(sizes, blobs):
        d = 0 if s >= 256 else s
        out.write(struct.pack("<BBBBHHII", d, d, 0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
    for blob in blobs:
        out.write(blob)
    path.write_bytes(out.getvalue())


def icon_set(full, small, sizes):
    return {s: scaled(small if s <= 24 else full, s) for s in sizes}


def write_sheet(path, full, small):
    try:
        font = ImageFont.truetype(str(Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts" / "segoeui.ttf"), 18)
    except OSError:
        font = ImageFont.load_default()
    items = [("full 256", scaled(full, 256), 1), ("full 48", scaled(full, 48), 1),
             ("small 24", scaled(small, 24), 1), ("small 16", scaled(small, 16), 1),
             ("small 24 (8x)", scaled(small, 24), 8), ("small 16 (8x)", scaled(small, 16), 8),
             ("full 16 (8x, before)", scaled(full, 16), 8)]
    pad, row_h = 24, 256 + 3 * 24 + 24
    col = [max(im.width * k, int(font.getlength(label))) for label, im, k in items]
    width = pad + sum(c + pad for c in col)
    sheet = Image.new("RGBA", (width, row_h * 2))
    for r, (bg, fg) in enumerate((("#FFFFFF", "#202020"), ("#202020", "#FFFFFF"))):
        y0 = r * row_h
        sheet.paste(Image.new("RGBA", (width, row_h), bg), (0, y0))
        d = ImageDraw.Draw(sheet)
        x = pad
        for (label, im, k), c in zip(items, col):
            big = im.resize((im.width * k, im.height * k), Image.NEAREST) if k > 1 else im
            sheet.alpha_composite(big, (x, y0 + pad + 30 + (256 - big.height) // 2))
            d.text((x, y0 + pad), label, fill=fg, font=font)
            x += c + pad
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--edge", help="path to msedge.exe (default: the standard install folders)")
    ap.add_argument("--dest", default=str(DEFAULT_DEST), help="branding folder to write")
    ap.add_argument("--sheet", help="also write a comparison sheet PNG here")
    args = ap.parse_args()

    dest = Path(args.dest).resolve()
    if not str(dest).upper().startswith("C:\\"):
        sys.exit(f"REFUSED: destination must be on drive C: '{dest}'")
    if not (dest / "moz.build").is_file():
        sys.exit(f"REFUSED: '{dest}' is not a branding folder (no moz.build)")

    src = {p.stem: p.read_text(encoding="utf-8") for p in SOURCE.glob("*.svg")}
    need = ("orbit", "orbit-small", "document", "document-pdf", "newtab", "newwindow")
    missing = [n for n in need if n not in src]
    if missing:
        sys.exit(f"missing sources in {SOURCE}: {missing}")

    work = Path(tempfile.mkdtemp(prefix="orbis-branding-"))
    try:
        r = Renderer(find_edge(args.edge), work)
        art = {
            "full": r.render(src["orbit"]),
            "small": r.render(src["orbit-small"]),
            "pfull": r.render(private(src["orbit"])),
            "psmall": r.render(private(src["orbit-small"])),
            "mark": r.render(mark(src["orbit"])),
            "pmark": r.render(mark(private(src["orbit"]))),
            "doc": r.render(src["document"]),
            "pdf": r.render(src["document-pdf"]),
            "newtab": r.render(src["newtab"]),
            "newwindow": r.render(src["newwindow"]),
        }
    finally:
        for _ in range(20):
            shutil.rmtree(work, ignore_errors=True)
            if not work.exists():
                break
            time.sleep(0.5)
    full, small, mk = art["full"], art["small"], art["mark"]

    png = {}
    for s in (16, 22, 24, 32, 48, 64, 128, 256):
        png[f"default{s}.png"] = scaled(small if s <= 24 else full, s)
    png["VisualElements_150.png"] = on_canvas(mk, 200, 300, 300)
    png["VisualElements_70.png"] = on_canvas(mk, 110, 142, 142)
    png["PrivateBrowsing_150.png"] = on_canvas(art["pmark"], 200, 300, 300)
    png["PrivateBrowsing_70.png"] = on_canvas(art["pmark"], 110, 142, 142)
    png["background.png"] = on_canvas(full, 320, 1440, 880, DEEP)
    png["content/about.png"] = on_canvas(full, 220, 300, 236)
    png["content/about-logo.png"] = scaled(full, 192)
    png["content/about-logo@2x.png"] = scaled(full, 384)
    png["content/about-logo-private.png"] = scaled(art["pfull"], 192)
    png["content/about-logo-private@2x.png"] = scaled(art["pfull"], 384)
    a = "msix/Assets/"
    png[a + "Square150x150Logo.scale-200.png"] = on_canvas(mk, 200, 300, 300, TEAL)
    png[a + "MedTile.scale-200.png"] = on_canvas(mk, 200, 300, 300, TEAL)
    png[a + "SmallTile.scale-200.png"] = on_canvas(mk, 110, 142, 142, TEAL)
    png[a + "LargeTile.scale-200.png"] = on_canvas(mk, 400, 620, 620, TEAL)
    png[a + "Wide310x150Logo.scale-200.png"] = on_canvas(mk, 200, 620, 300, TEAL)
    png[a + "Square44x44Logo.scale-200.png"] = scaled(full, 88)
    # Windows scales the targetsize-256 images down for the taskbar, title bar and Start list
    # (16 to 48 px), and the template's Resources.pri lists no smaller target sizes: use the small variant.
    for n in ("Square44x44Logo.targetsize-256.png", "Square44x44Logo.altform-unplated_targetsize-256.png",
              "Square44x44Logo.altform-lightunplated_targetsize-256.png"):
        png[a + n] = scaled(small, 256)
    png[a + "StoreLogo.scale-200.png"] = scaled(full, 100)
    png[a + "Document44x44.png"] = scaled(art["doc"], 44)

    written = []
    for rel, im in png.items():
        p = dest / rel
        p.write_bytes(png_bytes(im))
        written.append(rel)

    icos = {
        "firefox.ico": icon_set(full, small, ICO_ICON),
        "firefox64.ico": icon_set(full, small, (16, 24, 32, 48, 64)),
        "pbmode.ico": icon_set(art["pfull"], art["psmall"], ICO_ICON),
        "document.ico": icon_set(art["doc"], art["doc"], ICO_ICON),
        "document_pdf.ico": icon_set(art["pdf"], art["pdf"], ICO_ICON),
        "newtab.ico": icon_set(art["newtab"], art["newtab"], ICO_SMALL_SET),
        "newwindow.ico": icon_set(art["newwindow"], art["newwindow"], ICO_SMALL_SET),
    }
    for rel, images in icos.items():
        write_ico(dest / rel, images)
        written.append(rel)

    # NSIS wizard bitmaps (24-bit) and the stub installer background (JPEG). No NSIS installer ships;
    # they are drawn so the folder holds no placeholder.
    header = Image.new("RGBA", (150, 57), "#FFFFFF")
    header.alpha_composite(scaled(full, 48), (150 - 48 - 6, 4))
    header.convert("RGB").save(dest / "wizHeader.bmp")
    header_rtl = Image.new("RGBA", (150, 57), "#FFFFFF")
    header_rtl.alpha_composite(scaled(full, 48), (6, 4))
    header_rtl.convert("RGB").save(dest / "wizHeaderRTL.bmp")
    on_canvas(mk, 140, 164, 314, TEAL, dy=-60).convert("RGB").save(dest / "wizWatermark.bmp")
    on_canvas(full, 300, 1344, 822, DEEP).convert("RGB").save(dest / "stubinstaller" / "bgstub.jpg", quality=92)
    written += ["wizHeader.bmp", "wizHeaderRTL.bmp", "wizWatermark.bmp", "stubinstaller/bgstub.jpg"]

    shutil.copyfile(SOURCE / "orbit.svg", dest / "content" / "about-logo.svg")
    shutil.copyfile(SOURCE / "document-pdf.svg", dest / "content" / "document_pdf.svg")
    written += ["content/about-logo.svg", "content/document_pdf.svg"]

    if args.sheet:
        write_sheet(Path(args.sheet), full, small)
        print(f"sheet: {args.sheet}")
    for rel in sorted(written):
        print(f"  {rel}")
    print(f"OK: {len(written)} files in {dest}")


if __name__ == "__main__":
    main()
