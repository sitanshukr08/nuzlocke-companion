from .layout.gen1_charmap import CHARMAP

def decode_string(data: bytes) -> str:
    """
    Decode a Gen I proprietary string byte array into a Python string.
    Stops at the first 0x50 terminator byte.
    """
    result = []
    for byte in data:
        if byte == 0x50:
            break
        
        char = CHARMAP.get(byte)
        if char is not None:
            result.append(char)
        else:
            # For unknown characters, use a placeholder or hex representation
            result.append(f"\\x{byte:02x}")
            
    return "".join(result)
