import sys

def hexdump(data, base_offset):
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_str = " ".join([f"{b:02X}" for b in chunk])
        ascii_str = "".join([chr(b) if 32 <= b <= 126 else "." for b in chunk])
        print(f"{base_offset + i:04X}  {hex_str:<47}  {ascii_str}")

with open("tests/fixtures/pokemon_blue.sav", "rb") as f:
    data = f.read()

print("Party Count and Species List:")
hexdump(data[0x2F2C:0x2F34], 0x2F2C)

print("\nPokemon 1 Struct:")
hexdump(data[0x2F34:0x2F34+44], 0x2F34)

print("\nPokemon 2 Struct:")
hexdump(data[0x2F34+44:0x2F34+88], 0x2F34+44)

print("\nPokemon 3 Struct:")
hexdump(data[0x2F34+88:0x2F34+132], 0x2F34+88)

print("\nOT Names:")
hexdump(data[0x2F2C+0x110:0x2F2C+0x152], 0x2F2C+0x110)

print("\nNicknames:")
hexdump(data[0x2F2C+0x152:0x2F2C+0x194], 0x2F2C+0x152)

print("\nBox Count and Species:")
hexdump(data[0x30C0:0x30D6], 0x30C0)
