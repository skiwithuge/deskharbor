"""Verify an actual Codex/ChatGPT window in a disposable, unauthenticated home."""
import ctypes as c
import os
import signal
import subprocess
import time

x = c.CDLL("libX11.so.6")
x.XOpenDisplay.argtypes = [c.c_char_p]
x.XOpenDisplay.restype = c.c_void_p
x.XDefaultRootWindow.argtypes = [c.c_void_p]
x.XDefaultRootWindow.restype = c.c_ulong
x.XQueryTree.argtypes = [c.c_void_p, c.c_ulong, c.POINTER(c.c_ulong),
                        c.POINTER(c.c_ulong), c.POINTER(c.POINTER(c.c_ulong)), c.POINTER(c.c_uint)]
x.XFetchName.argtypes = [c.c_void_p, c.c_ulong, c.POINTER(c.c_void_p)]
x.XFree.argtypes = [c.c_void_p]
x.XCloseDisplay.argtypes = [c.c_void_p]
display = x.XOpenDisplay(None)
assert display, "Cannot open test desktop"

def titles(window, depth=0):
    name = c.c_void_p()
    if x.XFetchName(display, window, c.byref(name)) and name.value:
        yield c.string_at(name).decode(errors="replace")
        x.XFree(name)
    if depth >= 2:
        return
    root, parent, count = c.c_ulong(), c.c_ulong(), c.c_uint()
    children = c.POINTER(c.c_ulong)()
    if x.XQueryTree(display, window, c.byref(root), c.byref(parent), c.byref(children), c.byref(count)):
        try:
            for i in range(count.value):
                yield from titles(children[i], depth + 1)
        finally:
            if children:
                x.XFree(children)

with open("/tmp/codex-app-launch.log", "wb") as log:
    process = subprocess.Popen(["dbus-run-session", "--", "codex-app"],
                               stdout=log, stderr=log, start_new_session=True)
    try:
        for _ in range(40):
            if any("chatgpt" in title.lower() or "codex" in title.lower()
                   for title in titles(x.XDefaultRootWindow(display))):
                print("Codex desktop GUI window verified")
                break
            assert process.poll() is None, "Desktop app exited before opening a window"
            time.sleep(0.5)
        else:
            raise RuntimeError("Desktop app did not open a window within 20 seconds")
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)
        x.XCloseDisplay(display)
