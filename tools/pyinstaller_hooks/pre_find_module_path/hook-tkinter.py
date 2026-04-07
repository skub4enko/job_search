# Override PyInstaller's built-in pre-find-module-path hook for tkinter.
#
# The upstream hook may mark tkinter as "broken" and exclude it, which causes
# a runtime ModuleNotFoundError in frozen apps even when we provide Tcl/Tk data.
#
# By providing a no-op hook, we prevent exclusion and allow our standard hook
# (tools/pyinstaller_hooks/hook-tkinter.py) + hidden imports to pull tkinter in.

def pre_find_module_path(api):
    return
