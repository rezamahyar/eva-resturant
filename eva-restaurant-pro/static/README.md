This folder is intentionally kept in the repo (not empty) because:

- server.py registers it as Flask's static_folder.
- EVA_Restaurant.spec bundles it via datas=[('static','static')].

PyInstaller's Analysis step fails if a datas source directory doesn't
exist on disk, so this folder must be present even while empty.
