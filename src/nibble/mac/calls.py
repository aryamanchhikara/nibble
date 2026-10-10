"""Is a camera in use? That catches video calls in any app, browsers included.

Reads CoreMediaIO's "device is running somewhere" flag for each camera. That's
a device-state query, not capture, so it needs no camera permission. Checked
on a background thread every few seconds because the first call can take
tens of milliseconds.
"""

from __future__ import annotations

import ctypes
import logging
import threading

log = logging.getLogger(__name__)

CHECK_EVERY = 4.0

_SYSTEM_OBJECT = 1


def _fourcc(code: str) -> int:
    return int.from_bytes(code.encode("ascii"), "big")


class _Address(ctypes.Structure):
    _fields_ = [("selector", ctypes.c_uint32), ("scope", ctypes.c_uint32), ("element", ctypes.c_uint32)]


_DEVICES = _fourcc("dev#")  # kCMIOHardwarePropertyDevices
_RUNNING_SOMEWHERE = _fourcc("gone")  # kCMIODevicePropertyDeviceIsRunningSomewhere
_GLOBAL = _fourcc("glob")  # kCMIOObjectPropertyScopeGlobal


class CameraWatcher:
    def __init__(self) -> None:
        self.in_use = False
        self._stop = threading.Event()
        self._cmio = self._load()
        self._thread: threading.Thread | None = None

    def _load(self):
        try:
            lib = ctypes.CDLL("/System/Library/Frameworks/CoreMediaIO.framework/CoreMediaIO")
        except OSError:
            log.warning("CoreMediaIO unavailable; camera-based call detection is off")
            return None
        u32p = ctypes.POINTER(ctypes.c_uint32)
        lib.CMIOObjectGetPropertyDataSize.argtypes = [ctypes.c_uint32, ctypes.POINTER(_Address), ctypes.c_uint32, ctypes.c_void_p, u32p]
        lib.CMIOObjectGetPropertyData.argtypes = [
            ctypes.c_uint32, ctypes.POINTER(_Address), ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, u32p, ctypes.c_void_p,
        ]
        return lib

    def start(self) -> None:
        if self._cmio is None or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="nibble-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.in_use = self.check()
            except Exception:
                log.exception("camera check failed")
            self._stop.wait(CHECK_EVERY)

    def check(self) -> bool:
        lib = self._cmio
        if lib is None:
            return False
        addr = _Address(_DEVICES, _GLOBAL, 0)
        size = ctypes.c_uint32(0)
        if lib.CMIOObjectGetPropertyDataSize(_SYSTEM_OBJECT, ctypes.byref(addr), 0, None, ctypes.byref(size)) != 0:
            return False
        count = size.value // 4
        if count == 0:
            return False
        devices = (ctypes.c_uint32 * count)()
        used = ctypes.c_uint32(0)
        if lib.CMIOObjectGetPropertyData(_SYSTEM_OBJECT, ctypes.byref(addr), 0, None, size, ctypes.byref(used), devices) != 0:
            return False
        running = _Address(_RUNNING_SOMEWHERE, _GLOBAL, 0)
        for device in devices:
            flag = ctypes.c_uint32(0)
            status = lib.CMIOObjectGetPropertyData(device, ctypes.byref(running), 0, None, 4, ctypes.byref(used), ctypes.byref(flag))
            if status == 0 and flag.value:
                return True
        return False
