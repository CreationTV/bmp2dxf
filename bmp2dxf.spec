# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-folder build for the bmp2dxf Windows portable release."""

from pathlib import Path

repo = Path(SPECPATH).resolve()

datas = [
    (str(repo / "bmp2dxf" / "web" / "static"), "bmp2dxf/web/static"),
    (str(repo / "bmp2dxf" / "web" / "legacy"), "bmp2dxf/web/legacy"),
    (str(repo / "samples"), "samples"),
]

a = Analysis(
    [str(repo / "packaging" / "portable_entry.py")],
    pathex=[str(repo)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "IPython", "pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="bmp2dxf",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(repo / "packaging" / "bmp2dxf.ico"),
    version=str(repo / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="bmp2dxf-portable",
)
