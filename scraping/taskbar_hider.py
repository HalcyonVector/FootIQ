"""
Keeps the scraper's Chrome windows out of the taskbar (Windows only).

The scraper runs a real, non-headless Chrome (a headless one gets blocked) and parks its window
off-screen at (-32000, -32000). It is invisible, but Windows still gives it a taskbar button that
flashes when the window opens or wants attention, which is distracting during a long run.

This watches for Chrome windows that sit far off-screen and gives them the "tool window" style,
which removes the taskbar button without hiding the window or changing how Chrome renders (so its
timers are not throttled the way a minimised or hidden window's would be). Only off-screen windows
are touched: a Chrome window you are actually using is never affected.

    py -3 scraping/taskbar_hider.py                      # until stopped
    py -3 scraping/taskbar_hider.py --parent-pid 1234    # exits when that process ends (auto_update does this)
"""
import argparse
import sys
import time

if sys.platform != "win32":
    sys.exit("Windows only")

import ctypes
import ctypes.wintypes as wt

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SW_HIDE, SW_SHOWNA = 0, 8
OFFSCREEN = -10000          # the scraper's windows sit at about -32000; anything past this is "off-screen"
PROCESS_QUERY_LIMITED = 0x1000

EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def _fix(hwnd, _lparam) -> bool:
    if not user32.IsWindowVisible(hwnd):
        return True
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, 64)
    if not cls.value.startswith("Chrome_WidgetWin"):
        return True
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    if rect.left > OFFSCREEN and rect.top > OFFSCREEN:
        return True                                     # a window on the real desktop: leave it alone
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW and not ex & WS_EX_APPWINDOW:
        return True                                     # already done
    # The style only takes effect on a window that is hidden and shown again; SW_SHOWNA shows it
    # without activating it, so nothing steals focus.
    user32.ShowWindow(hwnd, SW_HIDE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
    user32.ShowWindow(hwnd, SW_SHOWNA)
    return True


def _alive(pid: int) -> bool:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not h:
        return False
    code = wt.DWORD()
    kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    kernel32.CloseHandle(h)
    return code.value == 259                            # STILL_ACTIVE


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent-pid", type=int, default=0, help="exit when this process is no longer running")
    args = ap.parse_args()
    callback = EnumWindowsProc(_fix)
    while True:
        user32.EnumWindows(callback, 0)
        if args.parent_pid and not _alive(args.parent_pid):
            return
        time.sleep(0.4)


if __name__ == "__main__":
    main()
