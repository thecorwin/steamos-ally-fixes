# SteamOS ROG Ally fixes: Decktation + Spoken Players

Getting **Decktation** (Decky voice dictation) and **Spoken Players** (WoW text-to-speech addon) working on a ROG Ally running SteamOS. Written as two SBARs (Situation, Background, Assessment, Recommendation).

Hardware: ROG Ally (Z1 Extreme) running SteamOS (not a Steam Deck). InputPlumber handles the controller. WoW runs as a non-Steam game under Proton 11.

**TL;DR / easy mode**
- **[Step-by-step guide](GUIDE.md)** for doing it all by hand.
- **[On/off switches](GUIDE.md#the-easy-way-onoff-switches):** run `toggles/install-launchers.sh` to get two desktop/app-menu icons, **Decktation fixes** and **Spoken Players fixes**.
  - Each opens a window with a switch for every part of the fix.
  - Each switch shows what's actually installed right now (green on, grey off, yellow partly on, e.g. after a Proton update undid the patch).
  - Flipping one asks first, then installs or reverts just that part.
  - A switch whose prerequisite is missing shows what to do first instead of failing.
  - You can add them to Steam to use them in Game Mode.
- **Everything is reversible.** There's an [undo for each change](#how-to-undo-each-change), and the sapi.dll patch backs up the original first.
- Please read the **[disclaimer](#disclaimer)** first. These are workarounds tested on one device, and the sapi.dll patch is experimental.

---

## What this supports

The switches and scripts find these on their own. Run `python3 -I spoken-players/prefix.py` to see what they found for WoW.

| | Works with |
|---|---|
| **Device** | ROG Ally (Z1 / Z1 Extreme) on SteamOS. Only the Z1 Extreme has been tested. |
| **How WoW is installed** | Battle.net added to Steam as a non-Steam game (Proton), **Heroic** or **Lutris**, normal or Flatpak install. For anything else (Bottles, a plain Wine prefix), point the scripts at it with `PFX=` and `WINE=` ([guide](GUIDE.md#different-install-heroic-lutris-other-folders)). |
| **WoW folder** | Any folder on any drive letter, SD card included. It's read from Battle.net's own install list. Override: `WOW_DIR=`. |
| **WoW client** | Retail, Classic, Classic Era and so on: every client folder that has the SpokenPlayers addon. |
| **Steam library** | Any, SD card included. |
| **Proton / Wine** | Any Proton (Valve's, GE-Proton) or Wine build. The patched sapi.dll is always built from the copy that runs your prefix. |
| **protontricks** | Optional. Used for Steam prefixes when installed (Flatpak or not). Otherwise the prefix's own Wine is run directly. |
| **Voicepack folder** | Any; read from its uninstall entry. |
| **Mic** | The internal mic's sound card and PipeWire name are detected when you switch those fixes on. |

**Limits and untested setups**
- **Heroic and Lutris:** tested with their config files and a real Wine prefix, not yet with WoW actually installed through them. Reports welcome.
- **sapi.dll patch:** tested on Proton Experimental (Wine 11) only. If another build's sapi.dll is different, the patch script stops with "not found" and changes nothing.
- **Password:** the Ally buttons switch and Restart Decky need your password. SteamOS has none until you set one with `passwd` in Konsole. Use those two in Desktop Mode.
- **ROG Ally X and other handhelds:** untested. The Decktation controller patch is only for InputPlumber's `28de:12fd` device, and the mic level values were tuned on the Ally's ALC294.
- **Steam Deck:** not needed for Decktation's buttons (it already supports the Deck's controller). The Spoken Players part should work.
- **Other Linux distros:** the Spoken Players part should work (it needs `python3` with tkinter, plus `objdump` and `as` from binutils for the patch). The Decktation part assumes SteamOS: Decky in `~/homebrew` and SteamOS's RNNoise plugin.
- **Moving this folder** breaks the icons. Run `toggles/install-launchers.sh` again from the new place.

## 1. Decktation (Decky Loader dictation plugin, v0.3.23)

**Situation**
- The push-to-talk button combo did nothing on the Ally.
- Once that worked, dictation sometimes misheard words, mostly the first word of a sentence, and more often with fan or room noise.

**Background**
- On SteamOS, InputPlumber (0.78) takes over the Ally's pad and exposes it as a Deck-style hidraw device, `28de:12fd` "ROG Ally Controller", with an empty `HID_PHYS`.
- Decktation only reads hidraw from the real Deck controller (`28de:1205` with `HID_PHYS` ending in `/input2`). For anything else it falls back to Steam's virtual pad, which was unreliable here.
- The Ally's internal mic (ALC294) ships with very hot mixer levels (Internal Mic Boost 3, Capture 100%), so the input clipped. Steam/WirePlumber also reset those levels when you switch between Game and Desktop Mode, restart PipeWire, or boot.
- There was no noise suppression on the mic.

**Assessment**
- Controller: the plugin simply didn't have a profile for the InputPlumber device. Adding one fixed it.
- Mic levels: Boost 1 with Capture 40% puts speech peaks around -20 to -27 dBFS with no clipping. The levels have to be re-applied after every reset.
- Noise: an RNNoise filter source in PipeWire dropped the noise floor from about -53 dBFS to about -103 dBFS. In a side-by-side test with a real voice, the filtered mic gave the same or better transcripts than the raw one.
- Remaining errors were mostly the first word, plus a real confusion in the model: "Guild" vs "Killed" showed up even on clean audio. Clips are short, so if you start talking the instant you press the buttons, you clip the first sound.

**Recommendation / what worked**
1. **Controller profile:** add a `ControllerProfile` for product `0x12fd` (same layout as the Deck) in `~/homebrew/plugins/decktation/bin/controller_profiles.py`, and set Decktation's Controller input to **Legacy** (not SDL). Plugin updates overwrite this file, so keep the patch around. (SteamOS has no `patch` command; `git apply` works.) Worth adding upstream.
2. **Mic levels:** a small user systemd service (`~/.config/systemd/user/`) that sets Boost 1 / Capture 40% with `amixer` and re-checks every 5 s. It costs almost nothing and survives mode switches.
3. **Noise suppression:** a PipeWire filter-chain drop-in in `~/.config/pipewire/pipewire.conf.d/` using the RNNoise LADSPA plugin that SteamOS already ships (`/usr/lib/ladspa/rnnoise_ladspa.so`, label **`nt-filter`**, not `noise_suppressor_*`). Leave the VAD gate at 0 so quiet words aren't cut. Make it the default: `pactl set-default-source effect_output.rnnoise`.
4. **Recognition keywords:** in Decktation's *Edit game profile*, add `guild` and `guild chat` as Recognition keywords. Clips that came out "Killed" came out "guild" with these. They're saved in the plugin's settings folder, so they survive updates.
5. **Habits:** wait about half a second after pressing before you talk, and hold about half a second after the last word. If "remember last channel" is on, don't say the channel name at all. Also, "Say" at the start of a sentence is a channel trigger and will post to /say.

---

## 2. Spoken Players (WoW chat text-to-speech addon + voicepack)

**Situation**
- The addon found no Spoken Players voices. The TTS options showed only "en_US male / female".
- After a few fixes, chat lines popped up as subtitles but no voice played, and `/sp debug` showed "tts failed".
- After the next fix, voices played but read the XML tags out loud ("bookmark mark start...").

**Background**
- The voicepack installer is a Windows program with a custom SAPI engine. Under Proton it copies the files but **writes no SAPI voice tokens to the registry**. The current installer also silently downloaded **none** of the newer voice models.
- "en_US male / female" aren't Windows voices. They're Vivox's built-in Flite TTS, so WoW wasn't seeing any SAPI voices, not even Proton's own.
- Wine's `sapi.dll` (current Proton 10/11/Experimental) is incomplete in ways that matter here.

**Assessment** (found with `PROTON_LOG=1 WINEDEBUG=+sapi,+ole,+loaddll`)
1. **WoW turns off Windows TTS when it detects Wine.** Wow.exe never even loaded sapi.dll. There's a hidden CVar, `winePlatformTTS` ("Use Windows TTS on Wine. Disabled by default as it can cause crashes").
2. **Missing registry entries**: the installer skipped them under Proton. 64-bit WoW reads the classic `HKLM\SOFTWARE\Microsoft\Speech\Voices\Tokens` list.
3. **`ISpVoice::SetInterest` is a stub in Wine that returns E_NOTIMPL.** WoW treats that as failure and drops the voice before calling `Speak`. That's why Play Sample does nothing for *any* Windows voice, Proton's included.
4. **Wine's SAPI doesn't parse SAPI XML** (it only does SSML). WoW wraps every line in `<bookmark mark='Start'/>…<bookmark mark='End'/>`, so `Speak` fails. If you force plain text, the engine reads the tags aloud.
5. Separately, the addon's saved settings had `guild = false`, so guild chat was never read even once everything else worked.

**Recommendation / what worked** (close WoW and Battle.net before touching the prefix; the registry only saves when wineserver exits cleanly)
1. Add `SET winePlatformTTS "1"` to `WTF/Config.wtf` (or `/console winePlatformTTS 1` then `/reload`).
2. Register every installed voice under `Speech\Voices\Tokens` (I generated a .reg from the installed `voices/` folders) and import it with `protontricks -c 'wine reg import ...' <appid>`. `regedit /S` failed silently for me; `reg import` worked. Protontricks (Flatpak) can't see arbitrary home folders, so copy the .reg into the prefix's `drive_c` first.
3. Missing voices: download each model from the installer's own Hugging Face source and pinned revision (`model.onnx`, `tokens.txt`, `voice.json` per voice), check each against its SHA-256, then re-register. `fetch_voices.py` in the repo does this automatically and only grabs what's missing.
4. **Experimental sapi.dll patch** (the only way I found to get sound under current Proton): a copy of Proton's `sapi.dll` with
   - `SetInterest` returning S_OK,
   - `Speak`'s XML branch sent down the plain-text path,
   - a small routine that strips `<...>` tags from the text before it goes to the engine,
   
   installed in the prefix's `system32` in place of the symlink, with DllOverride `sapi=native,builtin`. Side effects: no program in that prefix gets XML/SSML parsing, and the addon's per-character pitch/rate shaping is lost (it only works through real SAPI XML). A Proton update replaces the symlink, so it has to be re-applied. The real fix belongs in Wine: implement `SetInterest`/events and SAPI XML.
5. In the SpokenPlayers settings, turn on **Guild** (and "guild in instance" if you want it in dungeons). The addon doesn't read General/Trade/custom channels at all.
6. Testing tip: quests and readables use pre-recorded audio, so they work even when TTS is broken. Test with a whisper or party line from someone else, or `/sp test`.

**Result:** Spoken Players voices now read party, guild and whisper chat in WoW under Proton, with no tags read aloud. No crashes so far.

---

Questions or problems? Open an issue. If the Decktation or Wine folks want details from the traces or disassembly, ask.

---

## Files in this repo

- `GUIDE.md`: the full step-by-step guide.
- `toggles/`: `ally_toggles.py` (the switch windows) and `install-launchers.sh` (adds them to the app menu and desktop).
- `decktation/decktation-inputplumber-12fd.patch`: adds the InputPlumber (`28de:12fd`) controller profile to Decktation's `bin/controller_profiles.py`. From that folder, apply it with `sudo git apply -p0 <patch>`. SteamOS has no `patch` command.
- `decktation/mic/`: the mic level service (`mic-levels.sh` + `mic-levels.service`) and the RNNoise PipeWire filter (`60-mic-rnnoise.conf`).
- `spoken-players/fetch_voices.py`: downloads the voices the setup skips under Proton, from the setup's own Hugging Face source and pinned revision, and checks each model's SHA-256. Run it as `python3 -I fetch_voices.py`, or add `--check` to only report.
- `spoken-players/make_spoken_reg.py`: builds the SAPI voice `.reg` files from your installed voicepack. Run it as `python3 -I make_spoken_reg.py`. Use `WOW_FLAVOR=` to pick a client folder.
- `spoken-players/apply_sapi_patch.sh`: builds the patched sapi.dll from **your own** Wine/Proton's sapi.dll and installs it into the prefix. Run it as `./apply_sapi_patch.sh`, and add `undo` to revert. It needs `objdump` and `as` (binutils), and WoW and Battle.net must be closed. It uses `patch_sapi_setinterest.py` and `strip_tags.s`.
- `spoken-players/prefix.py`: finds the WoW prefix, its Wine, the WoW folder and the voicepack (Steam, Heroic, Lutris), and runs Wine in it (`python3 -I prefix.py wine <command>`). All the scripts above use it, and it reads the `PFX=`, `WINE=`, `APPID=` and `WOW_DIR=` overrides.

No DLLs are included on purpose. The script patches the copy that's already on your machine, so you can read exactly what it changes.

## Before you start: back up

Close WoW and Battle.net, then copy the prefix's registry files. This one backup undoes every registry change below:
```
PFX=<the prefix: line from python3 -I spoken-players/prefix.py>
mkdir -p ~/wow-prefix-backup && cp -p "$PFX"/*.reg ~/wow-prefix-backup/
```
To restore it, close WoW and copy the three `.reg` files back into `$PFX`.

## How to undo each change

| Change | Undo |
|---|---|
| Decktation controller patch | In `~/homebrew/plugins/decktation/bin`, run `sudo git apply -R -p0 <patch>`. Reinstalling or updating the plugin from the Decky store also removes it. |
| Mic level service / RNNoise filter | `systemctl --user disable --now <service>`, delete the drop-in from `~/.config/pipewire/pipewire.conf.d/`, then `systemctl --user restart pipewire wireplumber pipewire-pulse`. |
| Decktation recognition keywords | Remove them in *Edit game profile*. |
| `winePlatformTTS` | `/console winePlatformTTS 0` then `/reload`, or delete the line from `WTF/Config.wtf`. |
| Downloaded voices | Uninstall the voicepack (`unins000.exe` in the prefix), or delete the voice folders under `C:\Program Files\Spoken Players\voices`. |
| Voice registry entries | `make_spoken_reg.py` also writes `spoken_voices_remove.reg`. Import it the same way (`wine reg import`) to delete every key the other two files add. Or restore the backup above. |
| Patched sapi.dll + DllOverride | `./apply_sapi_patch.sh undo`. The first install saves the original sapi.dll (or its symlink) and any existing `sapi` override to `<prefix>/sapi-patch-backup/`, and undo puts back exactly that. As a last resort, delete the prefix's `sapi.dll` and run the game once (Proton re-creates its link). |
| Addon settings (Guild on) | Turn the option back off in the SpokenPlayers settings. |

None of this modifies Proton's install, SteamOS system files or WoW's game files. Everything lives in the game's Wine/Proton prefix, your WoW settings, or your home folder.

## Disclaimer

- **Use at your own risk.** These are personal workarounds shared as-is, tested on one device: ROG Ally Z1 Extreme, SteamOS, Proton 11, as of Nov 2026. They may not work on other setups or future versions. Back up first.
- The sapi.dll patch is an **experimental binary patch** of Wine's speech library. It may cause crashes or stalls in anything that uses speech in that prefix. It turns off SAPI XML/SSML parsing there. WoW itself warns that `winePlatformTTS` "can cause crashes". If you see problems, run the undo.
- It's a workaround until Wine's SAPI implements `SetInterest`/events and SAPI XML. Once Proton fixes that, undo the patch.
- **Not affiliated with or endorsed by** Blizzard, Valve, ASUS, the Wine or Proton projects, InputPlumber, or the authors of Decktation or Spoken Players. All trademarks belong to their owners. Please don't send them bug reports caused by these patches without saying you're using them.
- Nothing here touches game files, memory or network traffic. It only changes the Windows speech library in your own Wine prefix and the in-game setting.

Scripts are under the MIT License (see `LICENSE`). The patched DLL you build from your own Proton install stays under Wine's license (LGPL-2.1+).
