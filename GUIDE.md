# Step-by-step guide

Tested on a ROG Ally (Z1 Extreme) running SteamOS, with WoW added to Steam as a non-Steam game under Proton 11. WoW installed through Heroic or Lutris, or in a different folder, works too; see [What this supports](README.md#what-this-supports). Do everything in **Desktop Mode** using **Konsole**. Read the [disclaimer](README.md#disclaimer) first. Every step can be undone ([undo table](README.md#how-to-undo-each-change)).

Get the files first:
```
cd ~ && git clone https://github.com/thecorwin/steamos-ally-fixes.git
```

## The easy way: on/off switches

```
~/steamos-ally-fixes/toggles/install-launchers.sh
```
This adds **Decktation fixes** and **Spoken Players fixes** to your app menu and desktop. Each one opens a window with a switch for every part below:

- **The switches show what's installed right now.** Each one is checked live every time the window opens or a change finishes.
- **Flipping a switch asks first,** then installs or reverts just that part. Its output appears in the log at the bottom.
- **Green** means on, **grey** off, and **yellow (knob in the middle)** partly on, for example after a Proton update undid the sapi.dll patch. Flip a yellow switch to finish installing.
- **Spoken Players switches refuse to run while WoW or Battle.net is open.**
- **The Ally buttons switch and Restart Decky ask for your password,** because Decky's plugin folder belongs to root. SteamOS has no password until you set one. If you never did, run `passwd` in Konsole first. Use these two in Desktop Mode.
- **WoW is found automatically,** whether it's in Steam, Heroic or Lutris, in any folder or drive. The Spoken Players window shows which prefix it picked at the top. If it says "not found", see [Different install](#different-install-heroic-lutris-other-folders).

To use them in Game Mode, right-click the entry in the app menu in Desktop Mode and choose "Add to Steam".

**Order:** go top to bottom in each window. A switch whose prerequisite is missing shows **UNAVAILABLE** and says what to do first: install Decktation, the addon or the voicepack, or start WoW once. The one soft order is **Voice models before Voices registered**. Registering first only covers the voices present right now, so the window warns you. After a download, "Voices registered" turns yellow; flip it again to finish. The four speech switches can be turned on in any order, but WoW only speaks once all four are on. Turning switches off is safe in any order.

Some steps still need you, and the windows say so:
- Install Decktation and the SpokenPlayers addon.
- Run the official voicepack setup once (step 2.1).

To remove the icons, run `install-launchers.sh remove`.

### Different install (Heroic, Lutris, other folders)
To see what was found, run `python3 -I ~/steamos-ally-fixes/spoken-players/prefix.py`. It lists the prefix, the Wine it uses, the WoW folder and the voicepack folder. If it picked the wrong prefix or found none, tell it where things are and re-install the icons with the same settings (the icons remember them):
```
PFX=<prefix folder> WINE=<its wine or proton> ~/steamos-ally-fixes/toggles/install-launchers.sh
```
- `PFX`: the folder with `drive_c` in it. In Heroic, it's the **Wine prefix folder** in the game's settings. In Lutris, it's the **Wine prefix** under Configure → Game options.
- `WINE`: the Wine or Proton build that runs that prefix. Heroic shows it as **Wine version**. Point at its `proton` file or `bin/wine`. You only need this outside Steam, and only if it isn't found.
- `WOW_DIR=<World of Warcraft folder>` if WoW isn't found inside the prefix.
- `APPID=<n>` to pick one Steam prefix by its number.

The manual steps below do the same things by hand.

---

## Part 1: Decktation (Decky dictation plugin)

### 1.1 Make the Ally's buttons work
1. Install Decktation from the Decky store, if you haven't yet.
2. Apply the controller profile patch:
   ```
   cd ~/homebrew/plugins/decktation/bin
   sudo git apply -p0 ~/steamos-ally-fixes/decktation/decktation-inputplumber-12fd.patch
   ```
   (`sudo` is needed because Decky owns the plugins folder. If it says the patch doesn't apply, the plugin has changed. Open `controller_profiles.py`, find the `steam_deck` profile line, and add the two lines from the patch below it by hand.)
3. Restart Decky with `sudo systemctl restart plugin_loader`, or reboot.
4. In Game Mode, open Decktation's settings and set **Controller input** to **Legacy** (not SDL). Or use the "Controller input = Legacy" switch.
5. Test the push-to-talk combo.

### 1.2 Stop the mic clipping (recommended)
The Ally's internal mic is set far too loud from the factory, and Steam keeps resetting it. This small service puts it back every 5 seconds.
1. Check the mic's sound card number. Run `arecord -l` and look for the line with **ALC294**. The script assumes it's card **1**. If yours is different, edit `-c 1` in `mic-levels.sh` (5 places). (The switch finds the card for you.)
2. Install and start the service:
   ```
   mkdir -p ~/.local/bin ~/.config/systemd/user
   cp ~/steamos-ally-fixes/decktation/mic/mic-levels.sh ~/.local/bin/
   cp ~/steamos-ally-fixes/decktation/mic/mic-levels.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now mic-levels.service
   ```
3. Check it's working with `journalctl --user -u mic-levels`. Every time it fixes the levels, it logs "restored mic gain".
4. To change the levels, edit `BOOST` and `CAPTURE` at the top of `~/.local/bin/mic-levels.sh`, then run `systemctl --user restart mic-levels`.

### 1.3 Noise suppression (recommended)
1. Find your mic's PipeWire name with `pactl list short sources`. It's the `alsa_input...analog-stereo` line. On the Ally it's usually `alsa_input.pci-0000_09_00.6.analog-stereo`, the name already in the config. If yours differs, edit `target.object` in the file. (The switch fills in the right name for you. Use the `alsa_input...` name itself, not SteamOS's `alsa_loopback_device...` copy.)
2. Install it:
   ```
   mkdir -p ~/.config/pipewire/pipewire.conf.d
   cp ~/steamos-ally-fixes/decktation/mic/60-mic-rnnoise.conf ~/.config/pipewire/pipewire.conf.d/
   systemctl --user restart pipewire wireplumber pipewire-pulse
   pactl set-default-source effect_output.rnnoise
   ```
3. "Noise Canceling Mic" should now be the default input. Picking a different mic in Steam's audio settings switches you off it. Run the `pactl` line again to switch back.

### 1.4 Better recognition in WoW
1. In Decktation, open **Edit game profile** for WoW, then **Recognition keywords**. Add `guild` and `guild chat` (or the channel words you use).
2. Restart Decky (or reboot). The Decktation log should show `Hotwords: guild, guild chat`.
3. Habits that help:
   - Press the buttons, wait about half a second, then talk.
   - Hold the buttons about half a second after your last word.
   - With "remember last channel" on, don't say the channel name.
   - Don't start a sentence with "Say". It's a channel trigger and posts to /say.

---

## Part 2: Spoken Players (WoW text-to-speech)

**Close WoW and Battle.net before every step in this part.** Changes made while they run can be lost.

### 2.0 Find your WoW prefix and back up
1. Let the scripts find it (Steam, Heroic or Lutris; any folder or drive):
   ```
   python3 -I ~/steamos-ally-fixes/spoken-players/prefix.py
   ```
   It prints the prefix, the Wine it uses, the WoW folder and the voicepack folder. Save the prefix line:
   ```
   PFX=<the prefix: line>
   ```
   If it found the wrong one or none, `export PFX=<prefix folder>` (plus `export WINE=<its wine or proton>` outside Steam) and run it again. Every script below follows those settings. See [Different install](#different-install-heroic-lutris-other-folders). (`export` only lasts for this Konsole window.)
2. Back up the registry. This is your full undo for the registry steps:
   ```
   mkdir -p ~/wow-prefix-backup && cp -p "$PFX"/*.reg ~/wow-prefix-backup/
   ```
3. Optional: protontricks (`flatpak install flathub com.github.Matoking.protontricks`). For Steam prefixes the scripts use it when it's there. Without it, or for Heroic/Lutris, they run the prefix's own Wine directly.

### 2.1 Install the addon and voicepack
1. Install the **SpokenPlayers** addon as usual.
2. Download the official voicepack setup (`SpokenPlayersVoicepack-Setup.exe`) from the Spoken Players website and run it **inside the WoW prefix**. Copy the exe into the prefix first (protontricks from Flatpak can't see most of your home folder):
   ```
   cp ~/Downloads/SpokenPlayersVoicepack-Setup.exe "$PFX/drive_c/"
   python3 -I ~/steamos-ally-fixes/spoken-players/prefix.py wine 'C:\SpokenPlayersVoicepack-Setup.exe'
   ```
   (Heroic's and Lutris' own "Run EXE in prefix" work too.) Click through the setup. The default install folder (`C:\Program Files\Spoken Players`) is easiest, but any folder works.
3. The setup finishes without errors, but under Proton it **downloads none of the voices it doesn't already have** and **registers no voices**. The next steps fix both.

### 2.2 Download the missing voices (Hugging Face)
The setup gets its voices from a public Hugging Face repo, pinned to one revision. This script downloads the same files from the same revision. It reads the revision from the setup's own `unins000.dat`, and checks each model against the SHA-256 that Hugging Face publishes:
```
cd ~/steamos-ally-fixes/spoken-players
python3 -I fetch_voices.py --check     # see what's missing (downloads nothing)
python3 -I fetch_voices.py             # download the missing ones (about 77 MB each)
```
It skips voices that are already complete. If a download fails, run it again. If a newer setup changes the revision, run the new setup first; the script follows whatever `unins000.dat` says.

### 2.3 Register the voices with Windows (Wine)
```
cd ~/steamos-ally-fixes/spoken-players
python3 -I make_spoken_reg.py          # add WOW_FLAVOR=<folder> to pick a client folder
cp spoken_voices*.reg "$PFX/drive_c/"
python3 -I prefix.py wine reg import 'C:\spoken_voices.reg'
python3 -I prefix.py wine reg import 'C:\spoken_voices_onecore.reg'
```
Use `reg import`, not `regedit /S`, which can fail without any error. Keep `spoken_voices_remove.reg`: importing it the same way deletes all of these entries again.

### 2.4 Let WoW use Windows voices under Wine
WoW turns off Windows TTS when it detects Wine. Turn it back on with one of these:
- With WoW closed, add the line `SET winePlatformTTS "1"` to `World of Warcraft/<client>/WTF/Config.wtf`.
- Or in game, type `/console winePlatformTTS 1` then `/reload`.

### 2.5 Patch Proton's speech library (experimental)
Proton's `sapi.dll` is missing two things WoW needs (`SetInterest`, and handling of SAPI XML), so no Windows voice can play. This script builds a fixed copy from **your own** Wine/Proton's sapi.dll and installs it in the WoW prefix only. Before the first install, it saves the original so `undo` can put it back.
```
cd ~/steamos-ally-fixes/spoken-players
./apply_sapi_patch.sh          # needs objdump/as (binutils); undo: ./apply_sapi_patch.sh undo
```
**Run it again after every Proton update**, because Proton puts its own sapi.dll back. If it says "not found ... Proton changed it?", Proton's code changed. Try WoW without the patch first, in case Proton fixed it.

### 2.6 Addon settings
In the SpokenPlayers options, turn on the channels you want read aloud, for example **Guild**, which was off for me, and "Guild in instance". General, Trade and custom channels aren't supported by the addon.

### 2.7 Test it
1. Start WoW. Run `/sp voicepack`; it should say the voicepack is installed.
2. Under Options → Accessibility → Text to Speech, the Spoken Players voices should be listed.
3. Run `/sp test`, or have someone whisper you or send a party/guild line. Quests and books use recorded audio, so they don't show whether TTS works.
4. Still silent? Run `/sp debug`. `C:\users\steamuser\AppData\Local\SpokenVoice\engine.log` in the prefix shows whether the voice engine loaded into Wow.exe.

### If something breaks
See the [undo table](README.md#how-to-undo-each-change). The quickest full reset is `./apply_sapi_patch.sh undo`, then remove the `winePlatformTTS` line, then copy the three `.reg` files from `~/wow-prefix-backup/` back into `$PFX` with WoW closed.
