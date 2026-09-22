#!/usr/bin/env python3
"""Extract icon resources from a PE executable (.exe) as raw image bytes.

Pure stdlib — no icoutils, no pip. Useful in minimal environments.
The tool never opens files itself: it reads the executable from stdin and
writes the icon to stdout, so the caller controls all paths via shell
redirection and no path parsing exists here.

Usage:
    extract-icon.py --png < app.exe  > icon.png   # largest embedded PNG icon
    extract-icon.py --ico < app.exe  > icon.ico   # all icon images, ICO container

Exit status is nonzero (with a message on stderr) if the input is not a PE
file, has no icon resources, or has no PNG-compressed icon when --png is used.
"""
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


def parse_icons(buf):
    """Return (best_png, ico_bytes) where best_png is (w, h, bytes) or None."""
    pe = struct.unpack_from("<I", buf, 0x3C)[0]
    if buf[pe:pe + 4] != b"PE\0\0":
        sys.exit("input is not a PE executable")
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
        entries.append(struct.pack("<BBBBHHII", wid, hgt, colors, 0,
                                   planes, bpp, len(blob), offset))
        blobs.append(bytes(blob))
        offset += len(blob)
    ico = struct.pack("<HHH", 0, 1, count) + b"".join(entries) + b"".join(blobs)
    return best_png, ico


def main():
    want_png = "--png" in sys.argv[1:]
    want_ico = "--ico" in sys.argv[1:]
    if (want_png and want_ico) or not (want_png or want_ico):
        sys.exit("usage: extract-icon.py (--png | --ico) < app.exe > out.(png|ico)")
    if sys.stdin.isatty():
        sys.exit("usage: extract-icon.py (--png | --ico) < app.exe > out.(png|ico)")

    buf = sys.stdin.buffer.read()
    if len(buf) < 64:
        sys.exit("input too small to be a PE executable")
    best_png, ico = parse_icons(buf)

    if want_png:
        if best_png is None:
            sys.exit("no PNG-compressed icon found; try --ico instead")
        sys.stdout.buffer.write(best_png[2])
    else:
        sys.stdout.buffer.write(ico)


if __name__ == "__main__":
    main()
