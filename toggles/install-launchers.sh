#!/bin/bash
# Adds "Decktation fixes" and "Spoken Players fixes" to the app menu and the desktop.
#   ./install-launchers.sh          add them
#   ./install-launchers.sh remove   take them away again
# To use them in Game Mode: in Desktop Mode, right-click the entry in the app menu > "Add to Steam".
# If you needed PFX=, WINE=, APPID= or WOW_DIR= to find WoW, set them when you run this and the
# icons remember them, e.g.  PFX=~/Games/Heroic/Prefixes/default/Battlenet ./install-launchers.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
APPS=~/.local/share/applications
DESK=$(xdg-user-dir DESKTOP 2>/dev/null || echo ~/Desktop)

if [ "$1" = remove ]; then
  rm -f "$APPS"/ally-fixes-{decktation,spoken}.desktop "$DESK"/ally-fixes-{decktation,spoken}.desktop
  echo "launchers removed"; exit 0
fi

mkdir -p "$APPS" "$DESK"
ENVS=""
for v in PFX WINE APPID WOW_DIR; do
  val="${!v}"
  [ -n "$val" ] || continue
  val=$(realpath -m -- "${val/#\~/$HOME}" 2>/dev/null || echo "$val")
  [ "$v" = APPID ] && val="${!v}"
  val=${val//\\/\\\\}; val=${val//\"/\\\"}; val=${val//\$/\\\$}; val=${val//\`/\\\`}
  ENVS="$ENVS \"$v=$val\""
  echo "icons will use $v=${!v}"
done
make() { # make <id> <name> <comment> <icon>
  cat > "$APPS/ally-fixes-$1.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$2
Comment=$3
Exec=${ENVS:+env$ENVS }python3 -I "$HERE/ally_toggles.py" $1
Icon=$4
Terminal=false
Categories=Utility;
EOF
  chmod +x "$APPS/ally-fixes-$1.desktop"
  cp "$APPS/ally-fixes-$1.desktop" "$DESK/"
}
make decktation "Decktation fixes" "Switch the Ally fixes for Decktation on or off" audio-input-microphone
make spoken "Spoken Players fixes" "Switch the WoW text-to-speech fixes on or off" audio-speakers
echo "added to the app menu and $DESK"
