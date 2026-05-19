# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\main.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=['app', 'app.app_controller', 'utils.folder_resolver', 'ezdxf', 'ezdxf.addons', 'ezdxf.tools', 'lxml', 'lxml.etree', 'pydantic', 'pydantic.fields', 'pydantic_core', 'openpyxl', 'tkinterdnd2', 'cryptography', 'msal', 'google.auth', 'google.auth.transport', 'google.auth.transport.requests', 'google.oauth2', 'google.oauth2.credentials', 'google_auth_oauthlib', 'google_auth_oauthlib.flow', 'googleapiclient', 'googleapiclient.discovery', 'googleapiclient.http', 'httplib2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'IPython', 'jupyter', 'pytest', 'PIL', 'zmq'],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [('O', None, 'OPTION'), ('O', None, 'OPTION')],
    name='DocumentManager_2026-05-04',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
