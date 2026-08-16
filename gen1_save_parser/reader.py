class SaveReader:
    def __init__(self, data: bytes):
        self.data = data
        self.length = len(data)

    def read_byte(self, offset: int) -> int:
        if offset >= self.length or offset < 0:
            raise IndexError(f"Offset {offset} out of bounds")
        return self.data[offset]

    def read_bytes(self, offset: int, size: int) -> bytes:
        if size < 0:
            raise ValueError(f"Size {size} cannot be negative")
        if offset + size > self.length or offset < 0:
            raise IndexError(f"Range {offset}-{offset+size} out of bounds")
        return self.data[offset:offset+size]

    def read_int(self, offset: int, size: int, byteorder: str = 'big') -> int:
        b = self.read_bytes(offset, size)
        return int.from_bytes(b, byteorder=byteorder)
