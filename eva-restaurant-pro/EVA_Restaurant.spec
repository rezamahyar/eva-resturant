# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('templates', 'templates'), ('static', 'static')]
binaries = []
hiddenimports = ['flask', 'flask_cors', 'sqlalchemy', 'werkzeug']
tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        'eva_restaurant',
        'eva_restaurant.core',
        'eva_restaurant.core.database',
        'eva_restaurant.server',
        'eva_restaurant.i18n',
        'eva_restaurant.logging',
        'eva_restaurant.logging.error_logger',
        'eva_restaurant.ui',
        'eva_restaurant.ui.main_window',
        'eva_restaurant.ui.styles',
        'eva_restaurant.ui.pages',
        'eva_restaurant.ui.widgets',
    ],
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
    name='EVA_Restaurant',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EVA_Restaurant',
)
