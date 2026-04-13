# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for BimmerDaten (stable onedir build)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

project_dir = Path(globals().get("SPEC", Path.cwd())).resolve().parent

# ReportLab often needs explicit collection of package data/binaries.
r_datas, r_bins, r_hidden = collect_all("reportlab")

# Translation backend may import modules dynamically.
translation_hidden = collect_submodules("deep_translator")

hiddenimports = sorted(set(r_hidden + translation_hidden))

datas = [
    (str(project_dir / "seeds"), "seeds"),
    (str(project_dir / "bimmerdatenlogo.ico"), "."),
] + r_datas

binaries = r_bins


a = Analysis(
    [str(project_dir / "main_window.py")],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BimmerDaten",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / "bimmerdatenlogo.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BimmerDaten",
)
