# SPDX-License-Identifier: GPL-3.0-or-later
"""Cancel and exit if the API's owning application disappears."""

import os
import threading


def watch_parent(pid, state):
    if type(pid) is not int or pid <= 0:
        raise ValueError('Invalid parent process id.')
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x00100000, False, pid)
        def alive():
            return bool(handle) and kernel.WaitForSingleObject(handle, 0) == 258
        def release():
            if handle:
                kernel.CloseHandle(handle)
    else:
        def alive():
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False
        def release():
            pass

    def monitor():
        try:
            while not state.closing.wait(.2):
                if not alive():
                    state.close()
                    # Bound cleanup even if native model loading is stuck.
                    threading.Event().wait(2)
                    os._exit(0)
        finally:
            release()
    threading.Thread(target=monitor, name='speech-owner', daemon=True).start()
