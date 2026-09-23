#!/usr/bin/env python3
"""Build a plugin ZIP with only the Decky runtime files."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "package.json").read_text())["version"]
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
FILES = ["plugin.json", "package.json", "main.py", "README.md", "UPSTREAM_REFERENCE.md", "LICENSE", "dist/index.js", "system/tailscale-decky-bridge.py", "system/tailscale-decky-bridge.service"]


def main():
    missing = [file for file in FILES if not (ROOT / file).is_file()]
    if missing:
        raise SystemExit("Missing build files: " + ", ".join(missing))
    destination = OUT / f"DeckyTailscaleControl-{VERSION}.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in FILES + ["py_modules/tailscale_control/__init__.py", "py_modules/tailscale_control/service.py"]:
            file = ROOT / relative
            archive.write(file, f"DeckyTailscaleControl/{relative}")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    (OUT / "SHA256SUMS.txt").write_text(f"{digest}  {destination.name}\n")
    print(destination)


if __name__ == "__main__":
    main()
