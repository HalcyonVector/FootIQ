"""
Keeps the scraper's Chrome windows out of the taskbar (Windows only).

The scraper runs a real, non-headless Chrome (a headless one gets blocked) and parks its window
off-screen at (-32000, -32000). It is invisible, but Windows still gives it a taskbar button that
flashes when the window opens or wants attention, which is distracting during a long run.

This gives those windows the "tool window" style, which means no taskbar button, without hiding the
window or changing how Chrome renders (so its timers are not throttled the way a minimised or hidden
window's would be).

Two layers:
  * A window-creation hook (SetWinEventHook) that reacts the moment Chrome creates or shows a window.
    Done before the window is first shown, the taskbar button is never created, so there is no flash.
  * A fast polling pass as a safety net for anything the hook missed.

Which windows: Chrome windows that belong to the scraper (a descendant of --parent-pid), or, if that
cannot be told, ones sitting far off-screen. A Chrome window you are using is never touched.

    py -3 scraping/taskbar_hider.py                      # until stopped
    py -3 scraping/taskbar_hider.py --parent-pid 1234    # exits when that process ends (auto_update does this)
    py -3 scraping/taskbar_hider.py --verbose            # print what it does
"""
import argparse
import sys
import threading
import time

if sys.platform != "win32":
    sys.exit("Windows only")

import ctypes
import ctypes.wintypes as wt

try:
    import psutil
except Exception:               # without it only the off-screen rule is available
    psutil = None

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SW_HIDE, SW_SHOWNA = 0, 8
OFFSCREEN = -10000          # the scraper's windows sit at about -32000; anything past this is "off-screen"
PROCESS_QUERY_LIMITED = 0x1000
EVENT_OBJECT_CREATE, EVENT_OBJECT_SHOW = 0x8000, 0x8002
OBJID_WINDOW = 0
WINEVENT_OUTOFCONTEXT = 0

WinEventProc = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.DWORD, wt.HWND, wt.LONG, wt.LONG, wt.DWORD, wt.DWORD)
EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

user32.GetWindowLongW.restype = wt.LONG
user32.SetWindowLongW.restype = wt.LONG
user32.SetWinEventHook.restype = wt.HANDLE

VERBOSE = False
PARENT = 0
_scraper_pids: dict = {}     # pid -> (belongs to the scraper?, checked at)


def _log(msg: str) -> None:
    if VERBOSE:
        print(f"[hider {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _is_scraper_pid(pid: int) -> bool:
    """True if `pid` is the parent or one of its descendants (the scraper's Chrome tree)."""
    if not PARENT or psutil is None:
        return False
    cached = _scraper_pids.get(pid)
    if cached and (cached[0] or time.time() - cached[1] < 2.0):
        return cached[0]
    try:
        ok = pid == PARENT or any(p.pid == PARENT for p in psutil.Process(pid).parents())
    except Exception:
        ok = False
    _scraper_pids[pid] = (ok, time.time())
    return ok


def _wanted(hwnd, check_position: bool) -> bool:
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(hwnd, cls, 64)
    if not cls.value.startswith("Chrome_WidgetWin"):
        return False
    if user32.GetWindow(hwnd, 4):                       # GW_OWNER: a child popup, never has its own taskbar button
        return False
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if _is_scraper_pid(pid.value):
        return True
    if not check_position:
        return False
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left <= OFFSCREEN or rect.top <= OFFSCREEN


def _style_it(hwnd, was_visible: bool) -> None:
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW and not ex & WS_EX_APPWINDOW:
        return
    new = (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
    if was_visible:
        # The style only takes effect on a window that is hidden and shown again; SW_SHOWNA shows
        # it without activating it, so nothing steals focus.
        user32.ShowWindow(hwnd, SW_HIDE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new)
        user32.ShowWindow(hwnd, SW_SHOWNA)
    else:
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new)   # not shown yet: no taskbar button was ever made
    _log(f"window {hwnd:#x}: taskbar button {'removed' if was_visible else 'prevented'}")


def _on_event(_hook, event, hwnd, id_object, id_child, _thread, _time) -> None:
    if id_object != OBJID_WINDOW or id_child != 0 or not hwnd:
        return
    try:
        if VERBOSE:
            c = ctypes.create_unicode_buffer(64); user32.GetClassNameW(hwnd, c, 64)
            if c.value.startswith("Chrome_WidgetWin"):
                ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                _log(f"event {'CREATE' if event == EVENT_OBJECT_CREATE else 'SHOW'} {hwnd:#x} visible={bool(user32.IsWindowVisible(hwnd))} "
                     f"tool={bool(ex & WS_EX_TOOLWINDOW)} app={bool(ex & WS_EX_APPWINDOW)} owner={bool(user32.GetWindow(hwnd, 4))}")
        if _wanted(hwnd, check_position=(event == EVENT_OBJECT_SHOW)):
            _style_it(hwnd, bool(user32.IsWindowVisible(hwnd)))
    except Exception as e:                              # a callback must never raise
        _log(f"event error: {e}")


def _sweep(hwnd, _lparam) -> bool:
    if user32.IsWindowVisible(hwnd) and _wanted(hwnd, check_position=True):
        _style_it(hwnd, True)
    return True


def _alive(pid: int) -> bool:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not h:
        return False
    code = wt.DWORD()
    kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    kernel32.CloseHandle(h)
    return code.value == 259                            # STILL_ACTIVE


def _watch_loop(stop: threading.Event) -> None:
    callback = EnumWindowsProc(_sweep)
    while not stop.is_set():
        user32.EnumWindows(callback, 0)
        if PARENT and not _alive(PARENT):
            stop.set()
            return
        stop.wait(0.15)


def main() -> None:
    global VERBOSE, PARENT
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent-pid", type=int, default=0, help="the scraper's process; exit when it ends")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    VERBOSE, PARENT = args.verbose, args.parent_pid

    stop = threading.Event()
    threading.Thread(target=_watch_loop, args=(stop,), daemon=True).start()

    proc = WinEventProc(_on_event)                      # keep a reference, or it is garbage collected
    hooks = [user32.SetWinEventHook(ev, ev, None, proc, 0, 0, WINEVENT_OUTOFCONTEXT)
             for ev in (EVENT_OBJECT_CREATE, EVENT_OBJECT_SHOW)]
    if not all(hooks):
        _log("could not install the window hook; falling back to polling only")
        while not stop.is_set():
            stop.wait(0.5)
        return
    msg = wt.MSG()
    while not stop.is_set():                            # the hook's callbacks are delivered through this message loop
        if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        else:
            stop.wait(0.01)
    for h in hooks:
        user32.UnhookWinEvent(h)


if __name__ == "__main__":
    main()
