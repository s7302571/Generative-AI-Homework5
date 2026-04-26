#!/usr/bin/env python3
"""
EIP-55 Ethereum address checker.

Modes:
  validate  - report format validity and checksum status (default)
  diff      - same as validate, plus a character-level diff vs. the canonical form
  normalize - print the canonical EIP-55 form of any-case input

Usage:
  python eip55.py <mode> <address>
  python eip55.py <address>              # defaults to validate

Notes:
  - Uses a real keccak-256 implementation. Tries pycryptodome first, then
    eth-utils, then a vendored pure-Python keccak-256 fallback. We do NOT
    fall back to hashlib.sha3_256: that is NIST SHA-3 (different padding)
    and produces different output, which would silently break EIP-55.
"""

from __future__ import annotations

import re
import sys
from typing import Callable, List, Tuple

HEX_RE = re.compile(r"^[0-9a-fA-F]{40}$")


# ---------------------------------------------------------------------------
# keccak-256 backend selection
# ---------------------------------------------------------------------------

def _load_keccak() -> Callable[[bytes], bytes]:
    """Return a function that computes keccak-256 of bytes -> 32 bytes."""
    try:
        from Crypto.Hash import keccak as _pyc_keccak  # pycryptodome

        def _hash(data: bytes) -> bytes:
            h = _pyc_keccak.new(digest_bits=256)
            h.update(data)
            return h.digest()

        return _hash
    except ImportError:
        pass

    try:
        from eth_utils import keccak as _eth_keccak  # eth-utils

        def _hash(data: bytes) -> bytes:
            return _eth_keccak(data)

        return _hash
    except ImportError:
        pass

    # Pure-Python fallback so the skill runs even without crypto libs installed.
    return _pure_python_keccak256


def _pure_python_keccak256(data: bytes) -> bytes:
    """Minimal keccak-256 (Keccak-f[1600], rate=1088, 0x01 padding byte).

    This is the original Keccak (pre-FIPS-202), which EIP-55 specifies.
    Do not confuse with hashlib.sha3_256, which uses 0x06 padding.
    """
    RATE = 136  # bytes (1088 bits)
    OUTPUT = 32  # bytes (256 bits)
    ROUNDS = 24

    RC = [
        0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
        0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
        0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
        0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
        0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
        0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
        0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
        0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
    ]
    R = [
        [0, 36, 3, 41, 18],
        [1, 44, 10, 45, 2],
        [62, 6, 43, 15, 61],
        [28, 55, 25, 21, 56],
        [27, 20, 39, 8, 14],
    ]

    def rol(x: int, n: int) -> int:
        n &= 63
        return ((x << n) | (x >> (64 - n))) & 0xFFFFFFFFFFFFFFFF

    def keccak_f(state: List[List[int]]) -> None:
        for rnd in range(ROUNDS):
            # Theta
            C = [state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4] for x in range(5)]
            D = [C[(x - 1) % 5] ^ rol(C[(x + 1) % 5], 1) for x in range(5)]
            for x in range(5):
                for y in range(5):
                    state[x][y] ^= D[x]
            # Rho + Pi
            B = [[0] * 5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    B[y][(2 * x + 3 * y) % 5] = rol(state[x][y], R[x][y])
            # Chi
            for x in range(5):
                for y in range(5):
                    state[x][y] = B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y]) & 0xFFFFFFFFFFFFFFFF
            # Iota
            state[0][0] ^= RC[rnd]

    # Padding (Keccak original, NOT FIPS-202): append 0x01 then 0x80 at end of block.
    pad_len = RATE - (len(data) % RATE)
    if pad_len == 1:
        padded = data + b"\x81"
    else:
        padded = data + b"\x01" + b"\x00" * (pad_len - 2) + b"\x80"

    state = [[0] * 5 for _ in range(5)]
    for offset in range(0, len(padded), RATE):
        block = padded[offset:offset + RATE]
        for i in range(RATE // 8):
            lane = int.from_bytes(block[i * 8:(i + 1) * 8], "little")
            x, y = i % 5, i // 5
            state[x][y] ^= lane
        keccak_f(state)

    out = bytearray()
    while len(out) < OUTPUT:
        for i in range(RATE // 8):
            x, y = i % 5, i // 5
            out += state[x][y].to_bytes(8, "little")
            if len(out) >= OUTPUT:
                break
        if len(out) < OUTPUT:
            keccak_f(state)
    return bytes(out[:OUTPUT])


keccak256 = _load_keccak()


# ---------------------------------------------------------------------------
# EIP-55 core
# ---------------------------------------------------------------------------

def to_eip55(addr_no_prefix_lower: str) -> str:
    """Compute the canonical EIP-55 form of a 40-char lowercase hex string."""
    digest = keccak256(addr_no_prefix_lower.encode("ascii"))
    hash_hex = digest.hex()  # 64 hex chars, one per address character's nibble
    out = []
    for i, ch in enumerate(addr_no_prefix_lower):
        if ch in "0123456789":
            out.append(ch)
        else:
            # Uppercase if the corresponding hash nibble is >= 8
            out.append(ch.upper() if int(hash_hex[i], 16) >= 8 else ch)
    return "".join(out)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def split_prefix(raw: str) -> Tuple[str, bool]:
    """Return (body, prefix_present)."""
    s = raw.strip()
    if s.startswith("0x") or s.startswith("0X"):
        return s[2:], True
    return s, False


def validate_format(body: str, prefix_present: bool) -> dict:
    """Return a dict describing format validity."""
    length_ok = len(body) == 40
    hex_ok = bool(HEX_RE.match(body)) if length_ok else all(c in "0123456789abcdefABCDEF" for c in body)
    bad_positions = [i for i, c in enumerate(body) if c not in "0123456789abcdefABCDEF"]
    return {
        "length": len(body),
        "length_ok": length_ok,
        "prefix_present": prefix_present,
        "hex_ok": hex_ok and length_ok,
        "bad_positions": bad_positions,
    }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _format_format_section(fmt: dict) -> List[str]:
    lines = ["Format:"]
    if fmt["length_ok"]:
        lines.append("  - Length: ok (40 hex chars)")
    else:
        lines.append(f"  - Length: wrong (got {fmt['length']}, expected 40)")
    lines.append(f"  - Prefix: {'0x present' if fmt['prefix_present'] else '0x missing'}")
    if fmt["hex_ok"]:
        lines.append("  - Hex characters: ok")
    else:
        if fmt["bad_positions"]:
            lines.append(f"  - Hex characters: invalid characters at positions {fmt['bad_positions']}")
        else:
            lines.append("  - Hex characters: invalid (length wrong, cannot fully verify)")
    return lines


def report_validate(raw: str, mode: str = "validate") -> str:
    body, prefix = split_prefix(raw)
    fmt = validate_format(body, prefix)
    lines = [f"Address: 0x{body}"]
    lines += _format_format_section(fmt)

    if not fmt["length_ok"] or not fmt["hex_ok"]:
        lines.append("Checksum:")
        lines.append("  - Status: not evaluated (format invalid)")
        return "\n".join(lines)

    canonical = to_eip55(body.lower())
    is_all_lower = body == body.lower()
    is_all_upper = body == body.upper()

    lines.append("Checksum:")
    if is_all_lower or is_all_upper:
        lines.append("  - Status: not applicable (all lowercase/uppercase has no checksum to verify)")
    elif body == canonical:
        lines.append("  - Status: valid")
    else:
        lines.append("  - Status: invalid")
    lines.append(f"  - Canonical EIP-55: 0x{canonical}")

    if mode == "diff":
        lines.append("")
        lines += _format_diff(body, canonical)

    return "\n".join(lines)


def _format_diff(body: str, canonical: str) -> List[str]:
    markers = []
    mismatches = []
    for i, (a, b) in enumerate(zip(body, canonical)):
        if a != b:
            markers.append("^")
            mismatches.append(i)
        else:
            markers.append(" ")
    lines = [
        "Diff (^ marks mismatched positions):",
        f"  input:    0x{body}",
        f"  expected: 0x{canonical}",
        f"            {''.join(markers)}",
        f"Mismatches: {len(mismatches)} character(s) at positions {mismatches}",
    ]
    return lines


def report_normalize(raw: str) -> str:
    body, _ = split_prefix(raw)
    fmt = validate_format(body, True)
    if not fmt["length_ok"] or not fmt["hex_ok"]:
        lines = [f"Address: 0x{body}"]
        lines += _format_format_section(fmt)
        lines.append("Canonical EIP-55: not computed (format invalid)")
        return "\n".join(lines)
    canonical = to_eip55(body.lower())
    return f"Address: 0x{body}\nCanonical EIP-55: 0x{canonical}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: List[str]) -> int:
    args = argv[1:]
    if not args:
        print("usage: eip55.py [validate|diff|normalize] <address>", file=sys.stderr)
        return 2

    valid_modes = {"validate", "diff", "normalize"}
    if args[0] in valid_modes:
        if len(args) < 2:
            print(f"error: mode '{args[0]}' requires an address argument", file=sys.stderr)
            return 2
        mode, address = args[0], args[1]
    else:
        mode, address = "validate", args[0]

    if mode == "normalize":
        print(report_normalize(address))
    else:
        print(report_validate(address, mode=mode))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
