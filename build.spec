# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller ビルド設定 (pdf-redact)。

使い方:
    pyinstaller --clean --noconfirm build.spec

成果物:
    Windows: dist/pdf-redact.exe   (--onefile --windowed 相当)
    macOS:   dist/pdf-redact.app   (--windowed 相当、BUNDLE で .app 化)

ポイント:
    - console=False (--windowed): GUI アプリなのでコンソールを出さない
    - onefile: EXE に a.binaries / a.datas を直接含める (exclude_binaries は
      使わない。onedir 向け設定のため)
    - macOS は EXE + BUNDLE で .app を作る。libpython は PyInstaller が
      自動で Contents/Frameworks に配置する
    - PyMuPDF (pymupdf) はバイナリ拡張。PyInstaller の hook
      (pyinstaller-hooks-contrib の hook-pymupdf.py) が動的ライブラリを
      自動収集するが、環境による差を吸収するため保険で collect する。
"""

import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

APP_NAME = "pdf-redact"

datas = []
binaries = []
hiddenimports = []

# PyMuPDF の動的ライブラリ (.so / .dylib / .pyd) と付属データを収集。
# hook と重複しても PyInstaller 側で重複排除される。
try:
    datas += collect_data_files("pymupdf")
    binaries += collect_dynamic_libs("pymupdf")
except Exception:
    pass

a = Analysis(
    ["redact.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

# 単一 exe (--onefile --windowed)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name=APP_NAME + ".app",
        icon=None,
        bundle_identifier="local.pdf-redact",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": "PDF黒塗りツール",
            "NSHighResolutionCapable": True,
        },
    )
