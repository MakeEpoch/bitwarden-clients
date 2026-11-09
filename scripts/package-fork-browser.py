#!/usr/bin/env python3
"""Package the MakeEpoch Chrome build without debug maps or duplicate SDK binaries."""

from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from zipfile import ZIP_DEFLATED, ZipFile

build, output = map(Path, sys.argv[1:])
manifest = json.loads((build / "manifest.json").read_bytes())
if manifest["name"] != "MakeEpoch Vault" or manifest["manifest_version"] != 3:
    raise ValueError("Expected the MakeEpoch Chrome MV3 build")

wasm_groups = defaultdict(list)
for path in sorted(build.rglob("*.wasm")):
    if path.parent != build / "assets":
        raise ValueError("Expected WASM assets to use the shared URL pattern")
    wasm_groups[sha256(path.read_bytes()).digest()].append(path)
if not wasm_groups or any(not re.fullmatch(r"[a-f0-9]{20}", p.stem) for group in wasm_groups.values() for p in group):
    raise ValueError("Unexpected Webpack WASM asset names")

duplicates = {path: group[0] for group in wasm_groups.values() for path in group[1:]}
rewrites = {old.stem.encode(): new.stem.encode() for old, new in duplicates.items()}
used = set()
if rewrites:
    # Webpack embeds each WASM module hash in its async JS loader. Both
    # compilers emit the same relative URL pattern, so only the hash differs.
    pattern = re.compile(rb"""(["'])(%s)\1""" % b"|".join(rewrites))

    def replace(match):
        quote, name = match.groups()
        used.add(name)
        return quote + rewrites[name] + quote

output.parent.mkdir(parents=True, exist_ok=True)
try:
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as package:
        for path in sorted(build.rglob("*")):
            if not path.is_file() or path.suffix == ".map" or path in duplicates:
                continue
            name = path.relative_to(build).as_posix()
            data = path.read_bytes()
            if path.suffix == ".js":
                if rewrites:
                    data = pattern.sub(replace, data)
                    if any(old in data for old in rewrites):
                        raise ValueError(f"Unresolved WASM reference in {name}")
                data = re.sub(rb"(?m)^//[#@] sourceMappingURL=.*$", b"", data)
            elif path.suffix == ".css":
                data = re.sub(rb"/\*[#@] sourceMappingURL=[^*]+\*/", b"", data)
            package.writestr(name, data)
        if used != set(rewrites):
            raise ValueError("Duplicate WASM references did not match the Webpack loader")
        package.writestr("makeepoch-local.json", '{"channel":"local"}\n')
except Exception:
    output.unlink(missing_ok=True)
    raise

print(f"{output} ({output.stat().st_size / 2**20:.2f} MiB), {len(wasm_groups)} unique WASM files")
