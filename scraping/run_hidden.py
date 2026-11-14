"""
Run a command on a separate, invisible Windows desktop (Windows only).

The scraper needs a real, non-headless Chrome (a headless one gets blocked). Even parked off-screen,
that window gets a taskbar button which flashes when Chrome starts. A process started on its own
desktop has no taskbar, no windows on yours and no way to take focus, so nothing shows at all, while
Chrome still behaves like a normal visible browser.

    py -3 scraping/run_hidden.py -- py -3 scraping/auto_update.py
    py -3 scraping/run_hidden.py --log run.log -- py -3 scraping/scrape_whoscored.py --leagues ENG-Premier League

The command's output goes to --log (default: scraping/run_hidden.log). Exit code is the command's.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import uuid
from pathlib import Path

if sys.platform != "win32":
    sys.exit("Windows only")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GENERIC_ALL = 0x10000000
INFINITE = 0xFFFFFFFF
CREATE_NO_WINDOW = 0x08000000


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR), ("lpTitle", wt.LPWSTR),
                ("dwX", wt.DWORD), ("dwY", wt.DWORD), ("dwXSize", wt.DWORD), ("dwYSize", wt.DWORD),
                ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD), ("dwFillAttribute", wt.DWORD),
                ("dwFlags", wt.DWORD), ("wShowWindow", wt.WORD), ("cbReserved2", wt.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wt.HANDLE), ("hStdOutput", wt.HANDLE),
                ("hStdError", wt.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]


user32.CreateDesktopW.restype = wt.HANDLE
user32.CreateDesktopW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPVOID, wt.DWORD, wt.DWORD, wt.LPVOID]
kernel32.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.LPVOID, wt.LPVOID, wt.BOOL, wt.DWORD, wt.LPVOID,
                                    wt.LPCWSTR, ctypes.POINTER(STARTUPINFOW), ctypes.POINTER(PROCESS_INFORMATION)]


def run_on_hidden_desktop(command: list[str], log_path: Path, cwd: Path) -> int:
    name = f"footiq_{uuid.uuid4().hex[:8]}"
    desktop = user32.CreateDesktopW(name, None, None, 0, GENERIC_ALL, None)
    if not desktop:
        raise OSError(f"could not create a desktop: error {ctypes.get_last_error()}")
    try:
        # cmd does the redirection, so the child needs no inherited handles.
        inner = subprocess.list2cmdline(command)
        cmdline = f'cmd.exe /c "{inner} >> "{log_path}" 2>&1"'
        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(si)
        si.lpDesktop = f"WinSta0\\{name}"
        pi = PROCESS_INFORMATION()
        buf = ctypes.create_unicode_buffer(cmdline)
        if not kernel32.CreateProcessW(None, buf, None, None, False, CREATE_NO_WINDOW, None, str(cwd), ctypes.byref(si), ctypes.byref(pi)):
            raise OSError(f"CreateProcess failed: error {ctypes.get_last_error()}")
        kernel32.WaitForSingleObject(pi.hProcess, INFINITE)
        code = wt.DWORD()
        kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
        kernel32.CloseHandle(pi.hProcess)
        kernel32.CloseHandle(pi.hThread)
        return code.value
    finally:
        user32.CloseDesktop(desktop)


def main() -> None:
    ap = argparse.ArgumentParser(usage="run_hidden.py [--log FILE] -- COMMAND [ARGS...]")
    ap.add_argument("--log", default=str(Path(__file__).parent / "run_hidden.log"))
    ap.add_argument("command", nargs=argparse.REMAINDER)
    args = ap.parse_args()
    command = [c for c in args.command if c != "--"] if args.command[:1] == ["--"] else args.command
    if not command:
        ap.error("give a command after --")
    sys.exit(run_on_hidden_desktop(command, Path(args.log).resolve(), Path.cwd()))


if __name__ == "__main__":
    main()
