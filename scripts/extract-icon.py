#!/usr/bin/env python3
"""Extract the embedded application icon from a PE executable (.exe).

Pure stdlib — no icoutils, no pip. Useful in minimal environments.

Usage:
    extract-icon.py <app.exe> <out-base> [--png-only]

Writes <out-base>.ico containing every icon image, and additionally
<out-base>.png when the largest icon image is PNG-compressed (desktop
environments consume PNG natively, and some ICO readers choke on
PNG-in-ICO entries).
"""
import os
import struct
import sys


def rva_to_off(rva, sections):
    for va, vsz, raw, rawsz in sections:
        if va <= rva < va + max(vsz, rawsz):
            return raw + (rva - va)
    return None


def walk(buf, base, off, depth, typ, rid, out):
    """Walk the resource directory tree: depth1 type, depth2 id, depth3 lang."""
    nname, nid = struct.unpack_from("<HH", buf, off + 12)
    for i in range(nname + nid):
        name_id, offset = struct.unpack_from("<II", buf, off + 16 + 8 * i)
        t = name_id if depth == 1 else typ
        r = name_id if depth == 2 else rid
        if offset & 0x80000000:
            walk(buf, base, base + (offset & 0x7FFFFFFF), depth + 1, t, r, out)
        else:
            drva, dsize, _ = struct.unpack_from("<III", buf, base + offset)
            out.setdefault(t, []).append((r, drva, dsize))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    exe, out_base = sys.argv[1], sys.argv[2]
    png_only = "--png-only" in sys.argv[3:]

    buf = open(exe, "rb").read()
    pe = struct.unpack_from("<I", buf, 0x3C)[0]
    assert buf[pe:pe + 4] == b"PE\0\0", "not a PE executable"
    nsec, = struct.unpack_from("<H", buf, pe + 6)
    optsz, = struct.unpack_from("<H", buf, pe + 20)
    opt = pe + 24
    magic, = struct.unpack_from("<H", buf, opt)
    ddoff = opt + (96 if magic == 0x10B else 112)
    res_rva, = struct.unpack_from("<I", buf, ddoff + 8 * 2)
    sect = []
    so = opt + optsz
    for i in range(nsec):
        vsz, va, rawsz, raw = struct.unpack_from("<IIII", buf, so + 40 * i + 8)
        sect.append((va, vsz, raw, rawsz))

    base = rva_to_off(res_rva, sect)
    if base is None:
        sys.exit("no resource section")
    out = {}
    walk(buf, base, base, 1, None, None, out)
    icons = {r: (rva, sz) for r, rva, sz in out.get(3, [])}  # RT_ICON
    groups = out.get(14, [])  # RT_GROUP_ICON
    if not icons or not groups:
        sys.exit("no icon resources found")

    goff = rva_to_off(groups[0][1], sect)
    count, = struct.unpack_from("<H", buf, goff + 4)
    entries, blobs, offset, best_png = [], [], 6 + 16, None
    for i in range(count):
        wid, hgt, colors, _, planes, bpp, dsz, rid = struct.unpack_from(
            "<BBBBHHIH", buf, goff + 6 + 14 * i)
        rva, _ = icons[rid]
        ioff = rva_to_off(rva, sect)
        blob = buf[ioff:ioff + dsz]
        is_png = blob[:4] == b"\x89PNG"
        if is_png:
            planes = bpp = 0
        w = 256 if wid == 0 else wid
        h = 256 if hgt == 0 else hgt
        if is_png and (best_png is None or w * h > (best_png[0] * best_png[1])):
            best_png = (w, h, blob)
        if not png_only:
            entries.append(struct.pack("<BBBBHHII", wid, hgt, colors, 0,
                                       planes, bpp, len(blob), offset))
            blobs.append(bytes(blob))
            offset += len(blob)

    if not png_only:
        with open(out_base + ".ico", "wb") as f:
            f.write(struct.pack("<HHH", 0, 1, count) + b"".join(entries) + b"".join(blobs))
        print(f"wrote {out_base}.ico: {count} image(s)")
    if best_png:
        with open(out_base + ".png", "wb") as f:
            f.write(best_png[2])
        print(f"wrote {out_base}.png: largest PNG icon ({best_png[0]}x{best_png[1]})")
    elif not png_only:
        print("no PNG-compressed icon; convert the .ico with your image tool")


if __name__ == "__main__":
    main()
