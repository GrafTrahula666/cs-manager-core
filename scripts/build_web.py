"""Assemble the browser prototype in web/dist: index.html, the csmcore sources as JSON and the
Pyodide runtime.

    python scripts/build_web.py path/to/pyodide/package

Pyodide (MPL-2.0) is not stored in the repo: download the npm tarball
(https://registry.npmjs.org/pyodide/-/pyodide-0.26.4.tgz), unpack it and pass the `package` dir.
The artifact host serves no archives, so the Python standard library ships as JSON of source
text and the page rebuilds python_stdlib.zip in memory before Pyodide asks for it.
"""
from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYODIDE_FILES = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "pyodide-lock.json"]
# stdlib parts the game never imports; dropping them keeps the page smaller
SKIP = ("unittest/", "pydoc", "doctest.py", "xmlrpc/", "idlelib/", "lib2to3/", "turtle", "ensurepip/",
        "wsgiref/", "pickletools.py", "tkinter/", "test/")


def main() -> None:
    dist = ROOT / "web" / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "web" / "index.html", dist / "index.html")
    src = ROOT / "src"
    core = {str(f.relative_to(src)): f.read_text(encoding="utf-8")
            for f in sorted((src / "csmcore").rglob("*")) if f.suffix in (".py", ".json")}
    (dist / "csmcore.json").write_text(json.dumps(core, ensure_ascii=False), encoding="utf-8")
    if len(sys.argv) > 1:
        pkg = Path(sys.argv[1])
        (dist / "py").mkdir(exist_ok=True)
        for name in PYODIDE_FILES:
            shutil.copy(pkg / name, dist / "py" / name)
        stdlib = {}
        with zipfile.ZipFile(pkg / "python_stdlib.zip") as z:
            for info in z.infolist():
                if info.is_dir() or info.filename.startswith(SKIP):
                    continue
                stdlib[info.filename] = z.read(info).decode("utf-8")
        (dist / "py" / "stdlib.json").write_text(json.dumps(stdlib, ensure_ascii=False), encoding="utf-8")
    print(f"built {dist}")


if __name__ == "__main__":
    main()
