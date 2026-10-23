from __future__ import annotations

import struct

from .windows_process import WindowsProcessMemory


class Il2CppReader:
    def __init__(self, memory: WindowsProcessMemory) -> None:
        self._memory = memory

    def read_byte(self, address: int) -> int:
        return self._memory.read(address, 1)[0]

    def read_int32(self, address: int) -> int:
        return struct.unpack("<i", self._memory.read(address, 4))[0]

    def read_int64(self, address: int) -> int:
        return struct.unpack("<q", self._memory.read(address, 8))[0]

    def read_uint64(self, address: int) -> int:
        return struct.unpack("<Q", self._memory.read(address, 8))[0]

    def read_pointer(self, address: int) -> int:
        return self.read_uint64(address)

    def read_list_pointers(self, list_address: int, maximum_count: int) -> list[int]:
        return self._read_list(list_address, maximum_count, "Q", 8)

    def read_list_int32(self, list_address: int, maximum_count: int) -> list[int]:
        return self._read_list(list_address, maximum_count, "i", 4)

    def _read_list(self, list_address: int, maximum_count: int, item_format: str, item_size: int) -> list[int]:
        if list_address == 0:
            return []
        items = self.read_pointer(list_address + 0x10)
        size = self.read_int32(list_address + 0x18)
        if size < 0 or size > maximum_count:
            raise ValueError(f"Abnormal IL2CPP List size: {size} (limit {maximum_count}).")
        if size == 0:
            return []
        if items == 0:
            raise ValueError("The IL2CPP List items pointer is null.")
        capacity = self.read_uint64(items + 0x18)
        if capacity < size or capacity > maximum_count * 16:
            raise ValueError(f"Abnormal IL2CPP Array capacity: {capacity}, List size is {size}.")
        return list(struct.unpack(f"<{size}{item_format}", self._memory.read(items + 0x20, size * item_size)))

    def read_object_class_name(self, object_address: int) -> str:
        class_address = self.read_pointer(object_address)
        return "" if class_address == 0 else self.read_class_name(class_address)

    def read_class_name(self, class_address: int) -> str:
        return self._read_null_terminated_utf8(self.read_pointer(class_address + 0x10), 256)

    def read_managed_string(self, address: int) -> str | None:
        if address == 0:
            return None
        length = self.read_int32(address + 0x10)
        if length < 0 or length > 16_384:
            raise ValueError(f"Abnormal IL2CPP String length: {length}.")
        return "" if length == 0 else self._memory.read(address + 0x14, length * 2).decode("utf-16-le")

    def _read_null_terminated_utf8(self, address: int, maximum_bytes: int) -> str:
        if address == 0:
            return ""
        data = self._memory.read(address, maximum_bytes)
        return data.split(b"\0", 1)[0].decode("utf-8", errors="replace")
