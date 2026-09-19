#!/usr/bin/env python3
"""Send WM_DELETE_WINDOW (graceful X close, same as clicking X) to windows.

Usage:
    x-graceful-close.py [--display :1] (--class SUBSTR | WINDOWID [WINDOWID...])

--class matches windows whose WM_CLASS res_class or res_name contains SUBSTR
(case-insensitive). Returns 0 if at least one close event was sent.
Tolerates windows vanishing mid-enumeration (BadWindow).
"""
import ctypes
import ctypes.util
import struct
import sys


def main():
    args = sys.argv[1:]
    display = ":1"
    cls = None
    wins = []
    i = 0
    while i < len(args):
        if args[i] == "--display" and i + 1 < len(args):
            display = args[i + 1]
            i += 2
        elif args[i] == "--class" and i + 1 < len(args):
            cls = args[i + 1].lower()
            i += 2
        else:
            wins.append(int(args[i], 16))
            i += 1

    X = ctypes.CDLL(ctypes.util.find_library("X11"))
    X.XOpenDisplay.restype = ctypes.c_void_p
    dpy = X.XOpenDisplay(display.encode())
    if not dpy:
        sys.exit(f"cannot open display {display}")

    ignorer = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
    # Keep a module-lifetime reference: libX11 stores this pointer, and a
    # garbage-collected trampoline segfaults on the first X error (BadWindow
    # is guaranteed when windows vanish mid-enumeration).
    global _ERR_HANDLER
    _ERR_HANDLER = ignorer(lambda *a: 0)
    X.XSetErrorHandler(_ERR_HANDLER)

    class XClassHint(ctypes.Structure):
        _fields_ = [("res_name", ctypes.c_char_p), ("res_class", ctypes.c_char_p)]

    wm_protocols = X.XInternAtom(dpy, b"WM_PROTOCOLS", 0)
    wm_delete = X.XInternAtom(dpy, b"WM_DELETE_WINDOW", 0)

    if cls:
        root = X.XDefaultRootWindow(dpy)
        stack = (ctypes.c_ulong * 8192)()
        n = ctypes.c_uint()
        d1, d2 = ctypes.c_ulong(), ctypes.c_ulong()
        X.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                 ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                                 ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_uint)]
        X.XQueryTree(dpy, root, ctypes.byref(d1), ctypes.byref(d2), stack, ctypes.byref(n))
        X.XGetClassHint.restype = ctypes.c_int
        X.XGetClassHint.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(XClassHint)]
        for k in range(n.value):
            w = stack[k]
            hint = XClassHint()
            if X.XGetClassHint(dpy, w, ctypes.byref(hint)):
                hay = b""
                if hint.res_class:
                    hay += hint.res_class.lower()
                if hint.res_name:
                    hay += b" " + hint.res_name.lower()
                if hay and cls.encode() in hay:
                    wins.append(w)
                if hint.res_name:
                    X.XFree(hint.res_name)
                if hint.res_class:
                    X.XFree(hint.res_class)

    class CME(ctypes.Structure):
        _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong),
                    ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                    ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
                    ("format", ctypes.c_int), ("data", ctypes.c_byte * 20)]

    class Ev(ctypes.Union):
        _fields_ = [("c", CME), ("pad", ctypes.c_byte * 192)]

    sent = 0
    for w in wins:
        ev = Ev()
        ev.c.type = 33  # ClientMessage
        ev.c.window = w
        ev.c.message_type = wm_protocols
        ev.c.format = 32
        ctypes.memmove(ev.c.data, struct.pack("Q", wm_delete), 8)
        X.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                 ctypes.c_ulong, ctypes.c_void_p]
        X.XSendEvent(dpy, X.XDefaultRootWindow(dpy), 0, 0x400000 | 0x20000, ctypes.byref(ev))
        sent += 1
    X.XFlush(dpy)
    X.XCloseDisplay(dpy)
    print(f"sent WM_DELETE_WINDOW to {sent} window(s)")
    sys.exit(0 if sent else 1)


if __name__ == "__main__":
    main()
