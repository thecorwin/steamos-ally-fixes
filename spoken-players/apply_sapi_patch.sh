#!/bin/bash
# Installs the patched sapi.dll into your WoW Proton prefix.
# Close WoW/Battle.net first. Set APPID to the compatdata folder number of your WoW shortcut.
#   APPID=<n> ./apply_sapi_patch.sh          install (rebuilds the patch from the current Proton's sapi.dll)
#   APPID=<n> ./apply_sapi_patch.sh undo     put back exactly what was there before the first install
#
# The first install saves the prefix's original sapi.dll (or its symlink) and any existing
# "sapi" DllOverride to <prefix>/sapi-patch-backup/. Undo restores them and deletes the backup.
# Proton's own files are never modified: the patch is built from a copy.
set -e
: "${APPID:?set APPID to your WoW shortcut appid (ls ~/.local/share/Steam/steamapps/compatdata/)}"
PFX=~/.local/share/Steam/steamapps/compatdata/$APPID/pfx
DLL="$PFX/drive_c/windows/system32/Speech/Common/sapi.dll"
BAK="$PFX/sapi-patch-backup"
HERE=$(cd "$(dirname "$0")" && pwd)
PROTON_SAPI="$(grep -o '/[^"]*Proton[^"]*' ~/.local/share/Steam/steamapps/compatdata/$APPID/config_info 2>/dev/null | head -1)"
[ -n "$PROTON_SAPI" ] || PROTON_SAPI=~/.local/share/Steam/steamapps/common/"Proton - Experimental"/files
PROTON_SAPI="${PROTON_SAPI%/}"; PROTON_SAPI="${PROTON_SAPI%/share/fonts}"; PROTON_SAPI="${PROTON_SAPI%/share/default_pfx}"
PROTON_SAPI="$PROTON_SAPI/lib/wine/x86_64-windows/sapi.dll"

[ -d "$PFX" ] || { echo "no prefix at $PFX (wrong APPID?)"; exit 1; }
if pgrep -x Wow.exe >/dev/null || pgrep -x wineserver >/dev/null; then
  echo "WoW / wineserver is still running. Close WoW and Battle.net, then try again."; exit 1
fi

# wineserver -w: wait for the registry to be saved, or the change can be lost.
reg() { flatpak run com.github.Matoking.protontricks -c "wine reg $*; wineserver -w" $APPID; }

if [ "$1" = undo ]; then
  if [ ! -d "$BAK" ]; then
    echo "no backup found in $BAK."
    echo "Fallback: relinking to the current Proton's sapi.dll and removing the sapi override."
    rm -f "$DLL"; ln -s "$PROTON_SAPI" "$DLL"
    reg 'delete "HKCU\\Software\\Wine\\DllOverrides" /v sapi /f' || true
    exit 0
  fi
  rm -f "$DLL"
  if [ -f "$BAK/symlink_target" ]; then ln -s "$(cat "$BAK/symlink_target")" "$DLL"
  elif [ -f "$BAK/sapi.dll" ]; then cp -p "$BAK/sapi.dll" "$DLL"
  fi
  if [ -f "$BAK/override" ]; then
    reg "add \"HKCU\\\\Software\\\\Wine\\\\DllOverrides\" /v sapi /t REG_SZ /d $(cat "$BAK/override") /f"
  else
    reg 'delete "HKCU\\Software\\Wine\\DllOverrides" /v sapi /f' || true
  fi
  rm -rf "$BAK"
  echo "restored the original sapi.dll and DllOverride; backup removed"; exit 0
fi

[ -f "$PROTON_SAPI" ] || { echo "can't find Proton's sapi.dll at $PROTON_SAPI"; exit 1; }

# Back up the original state once (a re-install after a Proton update keeps the first backup).
if [ ! -d "$BAK" ]; then
  mkdir -p "$BAK"
  if [ -L "$DLL" ]; then readlink "$DLL" > "$BAK/symlink_target"
  elif [ -f "$DLL" ]; then cp -p "$DLL" "$BAK/sapi.dll"
  fi
  # Existing "sapi" override, if any (value name only appears under DllOverrides).
  ov=$(grep -m1 '^"sapi"=' "$PFX/user.reg" 2>/dev/null | cut -d'"' -f4 || true)
  [ -n "$ov" ] && echo "$ov" > "$BAK/override"
  echo "saved the original state to $BAK"
fi

OUT="$BAK/sapi_patched.dll"
python3 -I "$HERE/patch_sapi_setinterest.py" "$PROTON_SAPI" "$OUT"
rm -f "$DLL"; cp "$OUT" "$DLL"
reg 'add "HKCU\\Software\\Wine\\DllOverrides" /v sapi /t REG_SZ /d native,builtin /f'
echo "installed. Original: $PROTON_SAPI   Undo: APPID=$APPID $0 undo"
