# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src/run.py'],
    pathex=['.',
    '.venv/lib/python3.13/site-packages'],
    binaries=[],
    datas=[('src/assets/*.svg', 'assets')],
    hiddenimports=[''],
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
    bundle_identifier=None,
    info_plist={
        'LSUIElement': True,
        'LSBackgroundOnly': True,
        'NSUIElement': True
    },
)
