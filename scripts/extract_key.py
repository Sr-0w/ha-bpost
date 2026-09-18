#!/usr/bin/env python3
"""Re-derive the My bpost ``x-api-key`` from the official app's native library.

The key is NOT stored in this repository. Run this at build/deploy time:

    python3 scripts/extract_key.py <libcamera-util.so> <output const.py>

It reads the 8 obfuscated segments from the ``.so`` (offsets verified for
My bpost 3.45.1 arm64), applies the app's own decode, and writes a
deployment copy of ``const.py`` with the real key. The key is NEVER printed.

If bpost rotates the key or restructures the library, re-run the mapping
procedure (see report §8) and update OFFSETS below.
"""

import base64
import sys

# JNI call order in CU.sCP(): startCamera, isAnyCameraAvailable,
# isHardwareSupported, hasSurfaceRendered, isFlashSupported,
# startFlash, stopFlash, switchCameraPreview.
OFFSETS = [62077, 65157, 60358, 61248, 60446, 63954, 61259, 65483]


def _cstr(data: bytes, off: int, limit: int = 220) -> str:
    return data[off:data.index(b"\x00", off, off + limit)].decode()


def _gchi(cid: str) -> str:
    rounds = int(base64.b64decode(cid[:2] + "==").decode())
    decoded = base64.b64decode(cid[2:])
    for _ in range(rounds):
        decoded = base64.b64decode(decoded)
    return decoded.decode()


def extract(so_path: str) -> str:
    data = open(so_path, "rb").read()
    return "".join(_gchi(_cstr(data, off)) for off in OFFSETS)


def main() -> int:
    if len(sys.argv) != 4:
        print(f"usage: {sys.argv[0]} <libcamera-util.so> <const.py in> <const.py out>",
              file=sys.stderr)
        return 2
    so_path, const_in, const_out = sys.argv[1], sys.argv[2], sys.argv[3]
    key = extract(so_path)
    if len(key) != 40:
        print(f"unexpected key length: {len(key)}", file=sys.stderr)
        return 1
    template = open(const_in, encoding="utf-8").read()
    if "REPLACE_ME_AT_DEPLOY_TIME" not in template:
        print("placeholder missing from template", file=sys.stderr)
        return 1
    open(const_out, "w", encoding="utf-8").write(
        template.replace("REPLACE_ME_AT_DEPLOY_TIME", key))
    print(f"wrote {const_out} (key length {len(key)}, value not shown)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
