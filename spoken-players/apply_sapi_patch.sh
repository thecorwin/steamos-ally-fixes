#!/bin/bash
# Installs the patched sapi.dll into your WoW Wine/Proton prefix.
# Close WoW/Battle.net first. The prefix is found automatically (Steam, Heroic or Lutris);
# see prefix.py for the overrides (PFX=, WINE=, APPID=).
#   ./apply_sapi_patch.sh          install (rebuilds the patch from the current Wine/Proton's sapi.dll)
#   ./apply_sapi_patch.sh undo     put back exactly what was there before the first install
#
# The first install saves the prefix's original sapi.dll (or its symlink) and any existing
# "sapi" DllOverride to <prefix>/sapi-patch-backup/. Undo restores them and deletes the backup.
# Wine/Proton's own files are never modified: the patch is built from a copy.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
INFO=$(python3 -I "$HERE/prefix.py" shell) || exit 1
eval "$INFO"
DLL="$PFX_SAPI"
BAK="$PFX/sapi-patch-backup"
echo "WoW prefix: $PFX ($SOURCE)"

[ -z "$RUNNER_PROBLEM" ] || { echo "$RUNNER_PROBLEM"; exit 1; }
if [ -n "$RUNNING" ]; then
  echo "WoW / Battle.net (or this prefix's wineserver) is still running. Close them, then try again."; exit 1
fi

# prefix.py waits for wineserver after each command, or the registry change can be lost.
reg() { python3 -I "$HERE/prefix.py" wine reg "$@"; }
OVR='HKCU\Software\Wine\DllOverrides'

if [ "$1" = undo ]; then
  if [ ! -d "$BAK" ]; then
    echo "no backup found in $BAK."
    [ -f "$WINE_SAPI" ] || { echo "and can't find this Wine/Proton's own sapi.dll; nothing changed"; exit 1; }
    echo "Fallback: putting back the current Wine/Proton's sapi.dll and removing the sapi override."
    rm -f "$DLL"
    if [ -n "$USES_LINKS" ]; then ln -s "$WINE_SAPI" "$DLL"; else cp "$WINE_SAPI" "$DLL"; fi
    reg delete "$OVR" /v sapi /f || true
    exit 0
  fi
  rm -f "$DLL"
  if [ -f "$BAK/symlink_target" ]; then ln -s "$(cat "$BAK/symlink_target")" "$DLL"
  elif [ -f "$BAK/sapi.dll" ]; then cp -p "$BAK/sapi.dll" "$DLL"
  fi
  if [ -f "$BAK/override" ]; then
    reg add "$OVR" /v sapi /t REG_SZ /d "$(cat "$BAK/override")" /f
  else
    reg delete "$OVR" /v sapi /f || true
  fi
  rm -rf "$BAK"
  echo "restored the original sapi.dll and DllOverride; backup removed"; exit 0
fi

[ -f "$WINE_SAPI" ] || { echo "can't find the sapi.dll of the Wine/Proton running this prefix (wine: ${WINE:-not found})"; exit 1; }

# Back up the original state once (a re-install after a Proton update keeps the first backup).
if [ ! -d "$BAK" ]; then
  mkdir -p "$BAK"
  if [ -L "$DLL" ]; then readlink "$DLL" > "$BAK/symlink_target"
  elif [ -f "$DLL" ] && ! grep -aq "Wine builtin DLL" "$DLL" && grep -aq "spvoice" "$DLL"; then
    # Already a patched Wine sapi.dll (from an earlier version of this script): the original was Proton's link.
    echo "$WINE_SAPI" > "$BAK/symlink_target"; OURS=1
  elif [ -f "$DLL" ]; then cp -p "$DLL" "$BAK/sapi.dll"
  fi
  # Existing "sapi" override, if any (value name only appears under DllOverrides).
  # (Skipped when the dll was already ours: then the override is ours too.)
  ov=$(grep -m1 '^"sapi"=' "$PFX/user.reg" 2>/dev/null | cut -d'"' -f4 || true)
  if [ -n "$ov" ] && [ -z "$OURS" ]; then echo "$ov" > "$BAK/override"; fi
  echo "saved the original state to $BAK"
fi

OUT="$BAK/sapi_patched.dll"
python3 -I "$HERE/patch_sapi_setinterest.py" "$WINE_SAPI" "$OUT"
mkdir -p "$(dirname "$DLL")"
rm -f "$DLL"; cp "$OUT" "$DLL"
reg add "$OVR" /v sapi /t REG_SZ /d native,builtin /f
echo "installed. Built from: $WINE_SAPI   Undo: $0 undo"
