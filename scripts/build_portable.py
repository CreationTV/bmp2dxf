"""Build the Windows portable release archive.

Usage (Windows, from the repository root)::

    .venv\\Scripts\\python -m pip install -e ".[build]"
    .venv\\Scripts\\python scripts\\build_portable.py

Outputs:
    dist/bmp2dxf-portable/                       one-folder application
    dist/bmp2dxf-portable-windows-x64-vX.Y.Z.zip release archive
    dist/SHA256SUMS.txt                         checksums for release assets
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP_DIR = DIST / "bmp2dxf-portable"
SPEC = ROOT / "bmp2dxf.spec"


def _version() -> str:
    sys.path.insert(0, str(ROOT))
    from bmp2dxf import __version__  # noqa: PLC0415

    return __version__


def _run_build() -> None:
    try:
        import PyInstaller  # noqa: F401, PLC0415
    except ImportError:
        print(
            'PyInstaller is not installed. Run: pip install -e ".[build]"',
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not SPEC.is_file():
        raise SystemExit(f"missing PyInstaller spec: {SPEC}")
    print(f"[build] PyInstaller: {SPEC.name}")
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC)],
        cwd=ROOT,
        check=True,
    )
    if not (APP_DIR / "bmp2dxf.exe").is_file():
        raise SystemExit(f"build finished but {APP_DIR / 'bmp2dxf.exe'} is missing")


def _copy_docs() -> None:
    """PyInstaller puts data files in _internal; keep user-facing docs at the root."""
    for name in ("README.md", "README.en.md", "LICENSE"):
        source = ROOT / name
        if not source.is_file():
            raise SystemExit(f"missing documentation file: {source}")
        shutil.copy2(source, APP_DIR / name)


def _check_layout() -> None:
    required = [
        APP_DIR / "bmp2dxf.exe",
        APP_DIR / "_internal" / "bmp2dxf" / "web" / "static" / "index.html",
        APP_DIR / "_internal" / "bmp2dxf" / "web" / "static" / "i18n.js",
        APP_DIR / "_internal" / "bmp2dxf" / "web" / "static" / "app.js",
        APP_DIR / "_internal" / "samples" / "mechanical.png",
        APP_DIR / "README.md",
        APP_DIR / "README.en.md",
        APP_DIR / "LICENSE",
    ]
    missing = [str(path.relative_to(APP_DIR)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("portable package is missing:\n  " + "\n  ".join(missing))


def _make_archive(version: str) -> Path:
    archive = DIST / f"bmp2dxf-portable-windows-x64-v{version}.zip"
    if archive.exists():
        archive.unlink()
    print(f"[zip] {archive.name}")
    with zipfile.ZipFile(
        archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as zf:
        for path in sorted(APP_DIR.rglob("*")):
            if path.is_file():
                zf.write(path, Path("bmp2dxf-portable") / path.relative_to(APP_DIR))
    return archive


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="reuse dist/bmp2dxf-portable and only create the zip",
    )
    parser.add_argument("--no-zip", action="store_true", help="only build the folder")
    args = parser.parse_args()

    version = _version()
    if not args.skip_build:
        _run_build()
    else:
        print("[build] --skip-build: reusing existing portable folder")
    _copy_docs()
    _check_layout()
    if args.no_zip:
        print(f"[done] {APP_DIR}")
        return 0
    archive = _make_archive(version)
    checksum = _sha256(archive)
    sums = DIST / "SHA256SUMS.txt"
    sums.write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    size_mb = archive.stat().st_size / (1024 * 1024)
    print(f"[done] {archive}  ({size_mb:.1f} MiB)")
    print(f"[done] {sums}")
    print(f"       sha256 {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
