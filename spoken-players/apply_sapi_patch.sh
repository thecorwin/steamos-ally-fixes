#!/bin/bash
# Installs the patched sapi.dll into your WoW Proton prefix.
# Close WoW/Battle.net first. Set APPID to the compatdata folder number of your WoW shortcut.
#   APPID=<n> ./apply_sapi_patch.sh          install (rebuilds the patch from the current Proton's sapi.dll)
#   APPID=<n> ./apply_sapi_patch.sh undo     put Proton's original back
set -e
: "${APPID:?set APPID to your WoW shortcut appid (ls ~/.local/share/Steam/steamapps/compatdata/)}"
PFX=~/.local/share/Steam/steamapps/compatdata/$APPID/pfx
DLL="$PFX/drive_c/windows/system32/Speech/Common/sapi.dll"
HERE=$(cd "$(dirname "$0")" && pwd)
PROTON_SAPI="$(grep -o '/[^"]*Proton[^"]*' ~/.local/share/Steam/steamapps/compatdata/$APPID/config_info 2>/dev/null | head -1)"
[ -n "$PROTON_SAPI" ] || PROTON_SAPI=~/.local/share/Steam/steamapps/common/"Proton - Experimental"/files
PROTON_SAPI="${PROTON_SAPI%/}"; PROTON_SAPI="${PROTON_SAPI%/share/fonts}"; PROTON_SAPI="${PROTON_SAPI%/share/default_pfx}"
PROTON_SAPI="$PROTON_SAPI/lib/wine/x86_64-windows/sapi.dll"

if pgrep -x Wow.exe >/dev/null || pgrep -x wineserver >/dev/null; then
  echo "WoW / wineserver is still running. Close WoW and Battle.net, then try again."; exit 1
fi
[ -f "$PROTON_SAPI" ] || { echo "can't find Proton's sapi.dll at $PROTON_SAPI"; exit 1; }

# wineserver -w: wait for the registry to be saved, or the change can be lost.
reg() { flatpak run com.github.Matoking.protontricks -c "wine reg $*; wineserver -w" $APPID; }

if [ "$1" = undo ]; then
  rm -f "$DLL"; ln -s "$PROTON_SAPI" "$DLL"
  reg 'delete "HKCU\\Software\\Wine\\DllOverrides" /v sapi /f' || true
  echo "restored the original sapi.dll link and removed the override"; exit 0
fi

python3 -I "$HERE/patch_sapi_setinterest.py" "$PROTON_SAPI" "$HERE/sapi_setinterest_ok.dll"
rm -f "$DLL"; cp "$HERE/sapi_setinterest_ok.dll" "$DLL"
reg 'add "HKCU\\Software\\Wine\\DllOverrides" /v sapi /t REG_SZ /d native,builtin /f'
echo "installed. Original: $PROTON_SAPI"
