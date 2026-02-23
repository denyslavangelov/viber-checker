"""
Dump the full UIA control tree of the Viber window so you can see all controls.
Run with Viber open (and optionally a chat open):  python dump_viber_uia.py
Output: viber_uia_tree.txt (UTF-8) and printed to stdout.
"""
from __future__ import annotations

import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from pywinauto import Application
    from pywinauto import findwindows
except ImportError:
    print("pip install pywinauto", file=sys.stderr)
    sys.exit(1)


def main():
    handles = findwindows.find_windows(title_re=".*Viber.*") if findwindows else []
    if not handles:
        print("No Viber window found. Open Viber (and a chat) then run this again.")
        sys.exit(1)
    hwnd = handles[0]
    print("Viber hwnd:", hwnd)

    app_uia = Application(backend="uia").connect(handle=hwnd)
    dlg = app_uia.window(handle=hwnd)
    print("dlg = app_uia.window(handle=hwnd)  ->", dlg)
    print()

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viber_uia_tree.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        with redirect_stdout(f):
            dlg.print_control_identifiers(depth=None)
    print("Full tree written to:", out_path)
    with open(out_path, "r", encoding="utf-8") as f:
        print(f.read())


if __name__ == "__main__":
    main()
