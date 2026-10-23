from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MAX_PATH = 260
MAX_MODULE_NAME32 = 255
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(wintypes.BYTE)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * (MAX_MODULE_NAME32 + 1)),
        ("szExePath", wintypes.WCHAR * MAX_PATH),
    ]


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    path: Path
    base_address: int
    size: int


def _kernel32() -> ctypes.WinDLL:
    if os.name != "nt":
        raise OSError("Windows process reading is only supported on Windows.")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.Module32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
    kernel32.Module32FirstW.restype = wintypes.BOOL
    kernel32.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
    kernel32.Module32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.ReadProcessMemory.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.ReadProcessMemory.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def find_process_id(executable_name: str) -> int | None:
    kernel32 = _kernel32()
    handle = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(handle, ctypes.byref(entry)):
            raise ctypes.WinError(ctypes.get_last_error())
        while True:
            if entry.szExeFile.casefold() == executable_name.casefold():
                return int(entry.th32ProcessID)
            if not kernel32.Process32NextW(handle, ctypes.byref(entry)):
                return None
    finally:
        kernel32.CloseHandle(handle)


def find_module(process_id: int, module_name: str) -> ModuleInfo | None:
    kernel32 = _kernel32()
    handle = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, process_id)
    if handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Module32FirstW(handle, ctypes.byref(entry)):
            raise ctypes.WinError(ctypes.get_last_error())
        while True:
            if entry.szModule.casefold() == module_name.casefold():
                base_address = ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value or 0
                return ModuleInfo(entry.szModule, Path(entry.szExePath), base_address, int(entry.modBaseSize))
            if not kernel32.Module32NextW(handle, ctypes.byref(entry)):
                return None
    finally:
        kernel32.CloseHandle(handle)


class WindowsProcessMemory:
    def __init__(self, process_id: int) -> None:
        self._kernel32 = _kernel32()
        self._handle = self._kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, process_id)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def read(self, address: int, size: int) -> bytes:
        if address <= 0 or size < 0:
            raise ValueError(f"Invalid memory address or length: 0x{address:X}, {size}")
        buffer = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t()
        if not self._kernel32.ReadProcessMemory(
            self._handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(read)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if read.value != size:
            raise OSError(f"Memory read length mismatch at 0x{address:X}: requested {size}, got {read.value}")
        return buffer.raw

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> WindowsProcessMemory:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
