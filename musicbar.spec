# -*- mode: python ; coding: utf-8 -*-
import tomllib

# Single source of truth for the bundle version shown in Finder's Get Info.
with open('pyproject.toml', 'rb') as f:
    VERSION = tomllib.load(f)['project']['version']

a = Analysis(
    ['src/run.py'],
    pathex=['.',
    '.venv/lib/python3.13/site-packages'],
    binaries=[],
    datas=[('src/assets/*.svg', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
info_plist={
        'LSUIElement': 'True'
}
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MusicBar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name='Music Bar.app',
    icon='src/assets/music.icns',
    bundle_identifier='com.nickstuer.musicbar',  # macOS tracks the login item by this ID
    version=VERSION,
    info_plist={
        # Menu bar app: no Dock icon. Don't mark it background-only - that forbids activation, so dialogs can't take
        # keyboard input.
        'LSUIElement': True,
    },
)
