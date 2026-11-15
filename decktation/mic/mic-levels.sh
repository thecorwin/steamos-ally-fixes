#!/bin/sh
# Keep ROG Ally internal mic gain (card 1, ALC294) at sane levels.
# Steam/WirePlumber reset Boost to 3 and Capture to 100% (clips badly) on
# audio profile switches, so re-apply whenever the mixer drifts.
BOOST=1
CAPTURE=40%

apply() {
  b=$(amixer -c 1 sget 'Internal Mic Boost' | sed -n 's/.*Front Left: \([0-9]*\).*/\1/p')
  c=$(amixer -c 1 sget 'Capture' | sed -n 's/.*Front Left: Capture [0-9]* \[\([0-9]*%\)\].*/\1/p')
  if [ "$b" != "$BOOST" ] || [ "$c" != "$CAPTURE" ]; then
    amixer -c 1 sset 'Internal Mic Boost' $BOOST >/dev/null
    amixer -c 1 sset 'Capture' $CAPTURE >/dev/null
    echo "restored mic gain (was boost=$b capture=$c)"
  fi
}

for i in $(seq 1 30); do amixer -c 1 sget Capture >/dev/null 2>&1 && break; sleep 1; done
sleep 3
apply
# Poll rather than parse mixer events: cheap, and immune to event storms.
while :; do sleep 5; apply; done
