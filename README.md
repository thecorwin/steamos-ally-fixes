**[ROG Ally / SteamOS] Getting Decktation (Decky voice dictation) and Spoken Players (WoW TTS addon) working: two SBARs**

Hardware: ROG Ally (Z1 Extreme) running SteamOS (not a Steam Deck). InputPlumber handles the controller. WoW runs as a non-Steam game under Proton 11. Sharing these in case anyone else hits the same problems.

---

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
3. Missing voices: download each model from the installer's own Hugging Face source (`model.onnx`, `tokens.txt`, `voice.json` per voice), check them against the SHA-256 list in the installer's `unins000.dat`, then re-register.
4. **Experimental sapi.dll patch** (the only way I found to get sound under current Proton): a copy of Proton's `sapi.dll` with
   - `SetInterest` returning S_OK,
   - `Speak`'s XML branch sent down the plain-text path,
   - a small routine that strips `<...>` tags from the text before it goes to the engine,
   
   installed in the prefix's `system32` in place of the symlink, with DllOverride `sapi=native,builtin`. Side effects: no program in that prefix gets XML/SSML parsing, and the addon's per-character pitch/rate shaping is lost (it only works through real SAPI XML). A Proton update replaces the symlink, so it has to be re-applied. The real fix belongs in Wine: implement `SetInterest`/events and SAPI XML.
5. In the SpokenPlayers settings, turn on **Guild** (and "guild in instance" if you want it in dungeons). The addon doesn't read General/Trade/custom channels at all.
6. Testing tip: quests and readables use pre-recorded audio, so they work even when TTS is broken. Test with a whisper or party line from someone else, or `/sp test`.

**Result:** Spoken Players voices now read party, guild and whisper chat in WoW under Proton, with no tags read aloud. No crashes so far.

---

Happy to answer questions. If the Decktation or Wine folks want details from the traces or disassembly, ask.

---

## Files in this repo

- `decktation/decktation-inputplumber-12fd.patch`: adds the InputPlumber (`28de:12fd`) controller profile to Decktation's `bin/controller_profiles.py`. From that folder, apply it with `git apply -p0 <patch>`. SteamOS has no `patch` command.
- `spoken-players/make_spoken_reg.py`: builds the SAPI voice `.reg` files from your installed voicepack. Run it as `APPID=<your WoW shortcut appid> python3 -I make_spoken_reg.py`. Use `WOW_FLAVOR=` if your client folder isn't `_retail_`.
- `spoken-players/apply_sapi_patch.sh`: builds the patched sapi.dll from **your own** Proton's sapi.dll and installs it into the prefix. Run it as `APPID=<n> ./apply_sapi_patch.sh`, and add `undo` to revert. It needs `objdump` and `as` (binutils), and WoW and Battle.net must be closed. It uses `patch_sapi_setinterest.py` and `strip_tags.s`.

No DLLs are included on purpose. The script patches the copy that's already on your machine, so you can read exactly what it changes.
Use at your own risk. The sapi.dll patch is a workaround until Wine's SAPI implements `SetInterest`/events and SAPI XML.
