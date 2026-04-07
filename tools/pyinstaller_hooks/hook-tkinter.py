# Custom PyInstaller hook to force-include tkinter even when the built-in hook
# decides the local Python's Tcl/Tk install is broken.

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('tkinter')
hiddenimports += ['_tkinter']
