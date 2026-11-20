#!/usr/bin/env python3
"""One window per addon, one switch per fix. Each switch shows the fix's *current* state,
read from the system every time the window opens or a change finishes.
Flipping a switch asks first, then installs or reverts that one part.

  python3 -I ally_toggles.py decktation
  python3 -I ally_toggles.py spoken

The WoW prefix is found automatically (Steam, Heroic or Lutris). Optional overrides:
PFX=<prefix folder>, WINE=<its wine or proton>, APPID=<Steam compatdata number>,
WOW_DIR=<World of Warcraft folder>. See spoken-players/prefix.py.
"""
import glob, json, os, re, shutil, subprocess, sys, tempfile, threading, time
import tkinter as tk
from tkinter import messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HOME = os.path.expanduser("~")
SP = os.path.join(REPO, "spoken-players")
sys.path.insert(0, SP)
import prefix

# ---------------------------------------------------------------- helpers

def sh(cmd, log=None, env=None, check=True):
    """Run a command, streaming its output to the log. Returns the exit code."""
    if log:
        log("$ " + (cmd if isinstance(cmd, str) else " ".join(cmd)))
    p = subprocess.Popen(cmd, shell=isinstance(cmd, str), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, env={**os.environ, **(env or {})})
    for line in p.stdout:
        if log:
            log("  " + line.rstrip())
    p.wait()
    if check and p.returncode:
        raise RuntimeError(f"command failed (exit {p.returncode})")
    return p.returncode

def out(cmd):
    try:
        return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""

def read(path, mode="r"):
    try:
        with open(path, mode) as f:
            return f.read()
    except OSError:
        return None

def wow_running():
    return bool(P) and prefix.running(P)

def password_problem():
    """pkexec needs a password; SteamOS has none until you set one."""
    st = out(["passwd", "-S"]).split()
    if len(st) > 1 and st[1] in ("NP", "L", "LK"):
        return "Your user has no password yet, so the system can't ask for one. In Konsole, run: passwd"
    return ""

# ---------------------------------------------------------------- one fix = one Part

class Part:
    """status() -> (state, detail). state is 'on', 'off', 'partial' or 'na' (can't tell / not available)."""
    name = ""
    desc = ""
    can_revert = True
    needs_wow_closed = False
    after = ""          # shown after a change, e.g. "restart Decky"
    def status(self): return "na", ""
    def warn(self, turning_on): return ""   # extra text for the confirm dialog
    def apply(self, log): pass
    def revert(self, log): pass

# ---------------------------------------------------------------- Decktation

DECK_BIN = os.path.join(HOME, "homebrew/plugins/decktation/bin")
DECK_PROFILES = os.path.join(HOME, "homebrew/settings/decktation/profiles.json")
DECK_BUTTONS = os.path.join(HOME, "homebrew/settings/decktation/button_config.json")
PATCH = os.path.join(REPO, "decktation/decktation-inputplumber-12fd.patch")
MIC_DIR = os.path.join(REPO, "decktation/mic")
MIC_SCRIPT = os.path.join(HOME, ".local/bin/mic-levels.sh")
MIC_UNIT = os.path.join(HOME, ".config/systemd/user/mic-levels.service")
RNN_CONF = os.path.join(HOME, ".config/pipewire/pipewire.conf.d/60-mic-rnnoise.conf")
RNN_SOURCE = "effect_output.rnnoise"
KEYWORDS = ["guild", "guild chat"]

def restart_pipewire(log):
    sh(["systemctl", "--user", "restart", "pipewire", "wireplumber", "pipewire-pulse"], log)
    time.sleep(2)

def raw_mic():
    srcs = out(["pactl", "list", "short", "sources"]).splitlines()
    names = [l.split("\t")[1] for l in srcs if "\t" in l]
    return next((n for n in names if "alsa_input" in n and not n.endswith(".monitor")
                 and n != RNN_SOURCE), None)

def mic_card():
    """Sound card of the internal mic: the Realtek codec card, else any card with an Internal Mic Boost."""
    for p in sorted(glob.glob("/proc/asound/card*/codec#*")):
        if "ALC294" in (read(p) or ""):
            return re.search(r"card(\d+)", p).group(1)
    for d in sorted(glob.glob("/proc/asound/card[0-9]*")):
        n = d.rsplit("card", 1)[1]
        if "Internal Mic Boost" in out(["amixer", "-c", n, "scontrols"]):
            return n
    return "1"

def mic_node():
    """PipeWire name of the internal mic's own ALSA capture node (not SteamOS's loopback copy)."""
    try:
        objs = json.loads(out(["pw-dump"]) or "[]")
    except ValueError:
        objs = []
    card, nodes = mic_card(), []
    for o in objs:
        pr = (o.get("info") or {}).get("props") or {}
        if pr.get("media.class") == "Audio/Source" and pr.get("device.api") == "alsa":
            nodes.append((str(pr.get("api.alsa.pcm.card", pr.get("alsa.card", ""))) == card,
                          "analog" in pr.get("node.name", ""), pr.get("node.name")))
    if nodes:
        return max(nodes)[2]
    m = raw_mic()
    return m.replace("alsa_loopback_device.", "") if m else None

class DeckController(Part):
    name = "Ally buttons (controller profile)"
    desc = "Lets Decktation read the Ally's push-to-talk buttons through InputPlumber.\nWorks together with the Controller input = Legacy switch below."
    after = "Restart Decky (button below) for this to take effect."
    def status(self):
        f = read(os.path.join(DECK_BIN, "controller_profiles.py"))
        if f is None:
            return "na", "Decktation isn't installed"
        return ("on", "patch applied") if "0x12fd" in f else ("off", "not patched")
    def warn(self, turning_on):
        if not turning_on and backend() == "legacy":
            return "Controller input is Legacy, which can't see the Ally's buttons without this patch. Switch Legacy off too (back to SDL)."
        return password_problem()
    def _git(self, log, reverse):
        if password_problem(): raise RuntimeError(password_problem())
        cmd = f"cd '{DECK_BIN}' && git apply {'-R ' if reverse else ''}-p0 '{PATCH}'"
        log("Asking for your password (Decky's plugin folder belongs to root)...")
        sh(["pkexec", "sh", "-c", cmd], log)
    def apply(self, log): self._git(log, False)
    def revert(self, log): self._git(log, True)

def backend():
    try: return json.loads(read(DECK_BUTTONS) or "{}").get("controllerBackend", "sdl")
    except ValueError: return "?"

class DeckLegacy(Part):
    name = "Controller input = Legacy"
    desc = "Decktation's Controller input setting. Legacy reads the buttons directly (needs the patch above);\nOFF = SDL, Decktation's default."
    after = "Restart Decky (button below) for this to take effect."
    def status(self):
        if not os.path.exists(DECK_BUTTONS):
            return "na", "open Decktation's settings once first"
        b = backend()
        if b == "?": return "na", "button_config.json isn't valid JSON"
        return ("on", "Legacy") if b == "legacy" else ("off", b.upper())
    def warn(self, turning_on):
        patched = "0x12fd" in (read(os.path.join(DECK_BIN, "controller_profiles.py")) or "")
        if turning_on and not patched:
            return "The Ally buttons patch isn't applied, so Legacy won't see the Ally's buttons. Switch that on too."
        return ""
    def _set(self, value, log):
        d = json.loads(read(DECK_BUTTONS)); d["controllerBackend"] = value
        with open(DECK_BUTTONS + ".tmp", "w") as f: json.dump(d, f, indent=2)
        os.replace(DECK_BUTTONS + ".tmp", DECK_BUTTONS); log(f"Controller input set to {value.upper()}")
    def apply(self, log): self._set("legacy", log)
    def revert(self, log): self._set("sdl", log)

class DeckMicLevels(Part):
    name = "Mic level guard"
    desc = "Keeps the internal mic at Boost 1 / Capture 40% so it doesn't clip.\nSteam resets it on mode switches; this puts it back every 5 s."
    def status(self):
        active = out(["systemctl", "--user", "is-active", "mic-levels.service"]) == "active"
        enabled = out(["systemctl", "--user", "is-enabled", "mic-levels.service"]) == "enabled"
        if active and enabled: return "on", "running"
        if active or enabled: return "partial", f"{'running' if active else 'stopped'}, {'starts' if enabled else 'does not start'} at login"
        return "off", "not running"
    def apply(self, log):
        card = mic_card()
        log(f"internal mic is sound card {card}")
        os.makedirs(os.path.dirname(MIC_SCRIPT), exist_ok=True)
        os.makedirs(os.path.dirname(MIC_UNIT), exist_ok=True)
        if not os.path.exists(MIC_SCRIPT):
            src = read(os.path.join(MIC_DIR, "mic-levels.sh")).replace("-c 1 ", f"-c {card} ")
            with open(MIC_SCRIPT, "w") as f: f.write(src)
            os.chmod(MIC_SCRIPT, 0o755)
        if not os.path.exists(MIC_UNIT):
            shutil.copy(os.path.join(MIC_DIR, "mic-levels.service"), MIC_UNIT)
        sh(["systemctl", "--user", "daemon-reload"], log)
        sh(["systemctl", "--user", "enable", "--now", "mic-levels.service"], log)
    def revert(self, log):
        sh(["systemctl", "--user", "disable", "--now", "mic-levels.service"], log)
        log("The levels stay as they are until Steam next resets them. The files are kept, so you can switch it back on.")

class DeckNoise(Part):
    name = "Noise-cancelling mic (RNNoise)"
    desc = "Adds a \"Noise Canceling Mic\" that filters fan/room noise, and makes it the default input.\nAudio drops for a second while PipeWire restarts."
    def status(self):
        have = os.path.exists(RNN_CONF)
        default = out(["pactl", "get-default-source"]) == RNN_SOURCE
        if have and default: return "on", "default input"
        if have: return "partial", "installed, but another mic is the default"
        return "off", "not installed"
    def apply(self, log):
        if not os.path.exists("/usr/lib/ladspa/rnnoise_ladspa.so"):
            raise RuntimeError("SteamOS's RNNoise plugin (/usr/lib/ladspa/rnnoise_ladspa.so) is missing")
        if not os.path.exists(RNN_CONF):
            node = mic_node()
            if not node:
                raise RuntimeError("couldn't find the internal mic in PipeWire (pactl list short sources)")
            log(f"internal mic is {node}")
            conf = re.sub(r'target.object = "[^"]*"', f'target.object = "{node}"',
                          read(os.path.join(MIC_DIR, "60-mic-rnnoise.conf")))
            os.makedirs(os.path.dirname(RNN_CONF), exist_ok=True)
            with open(RNN_CONF, "w") as f: f.write(conf)
            restart_pipewire(log)
        for _ in range(10):
            if RNN_SOURCE in out(["pactl", "list", "short", "sources"]): break
            time.sleep(1)
        else:
            raise RuntimeError("the Noise Canceling Mic didn't appear (check target.object in the conf, see the guide)")
        sh(["pactl", "set-default-source", RNN_SOURCE], log)
    def revert(self, log):
        if os.path.exists(RNN_CONF):
            os.remove(RNN_CONF); log(f"removed {RNN_CONF}")
            restart_pipewire(log)
        mic = raw_mic()
        if mic: sh(["pactl", "set-default-source", mic], log)

class DeckKeywords(Part):
    name = "WoW recognition keywords"
    desc = "Hints \"guild\" and \"guild chat\" to the speech model (fixes \"Guild\" heard as \"Killed\")."
    after = "Restart Decky (button below) for this to take effect."
    def _load(self):
        t = read(DECK_PROFILES)
        return json.loads(t) if t else {}
    def status(self):
        if not os.path.isdir(os.path.dirname(DECK_PROFILES)):
            return "na", "Decktation isn't installed"
        try:
            have = set(self._load().get("wow", {}).get("hotwords", []))
        except ValueError:
            return "na", "profiles.json isn't valid JSON"
        n = len(set(KEYWORDS) & have)
        return ("on", "set") if n == len(KEYWORDS) else ("partial", "some set") if n else ("off", "not set")
    def _save(self, d, log):
        tmp = DECK_PROFILES + ".tmp"
        with open(tmp, "w") as f: json.dump(d, f, indent=2)
        os.replace(tmp, DECK_PROFILES); log(f"updated {DECK_PROFILES}")
    def apply(self, log):
        d = self._load(); hw = d.setdefault("wow", {}).setdefault("hotwords", [])
        hw += [k for k in KEYWORDS if k not in hw]; self._save(d, log)
    def revert(self, log):
        d = self._load(); w = d.get("wow", {})
        w["hotwords"] = [k for k in w.get("hotwords", []) if k not in KEYWORDS]
        if not w["hotwords"]: del w["hotwords"]
        if not w: d.pop("wow", None)
        self._save(d, log)

# ---------------------------------------------------------------- Spoken Players

CLSID = "{055bf9e8-68b3-4cb2-8090-50895f4bcc68}"

P = prefix.find()          # {pfx, source, appid, wine, wow, flavors, sp_win, sp_dir} or None
PFX = P["pfx"] if P else None
WOW = P["wow"] if P else None
FLAVORS = P["flavors"] if P else []
VOICES = os.path.join((P or {}).get("sp_dir") or "", "voices")

def run_wine(args, log):
    for argv, env in prefix.wine_cmds(P, args):
        sh(argv, log, env=env, check=argv[-1] != "-w")

def voice_folders():
    try:
        return sorted(v for v in os.listdir(VOICES) if os.path.isfile(os.path.join(VOICES, v, "model.onnx")))
    except OSError:
        return []

def saved_vars():
    return [p for f in FLAVORS for p in glob.glob(os.path.join(WOW, f, "WTF/Account/*/SavedVariables/SpokenPlayers.lua"))]

class SpModels(Part):
    name = "Voice models (Hugging Face download)"
    desc = "Downloads the voices the official setup skips under Proton, checked by SHA-256.\nTo remove voices, uninstall the voicepack."
    can_revert = False
    after = "If \"Voices registered\" turns yellow, flip it to register the new voices."
    def status(self):
        if not FLAVORS: return "na", "install the SpokenPlayers addon first"
        if not os.path.isdir(VOICES): return "na", f"voicepack not installed in {P['sp_win']}: run the official setup first (guide step 2.1)"
        spk = read(os.path.join(WOW, FLAVORS[0], "Interface/AddOns/SpokenPlayers/Speakers.lua")) if FLAVORS else None
        known = len(set(re.findall(r'\["(Spoken Players [^"]+)"\]', spk or "")))
        good = 0
        for v in voice_folders():
            d = os.path.join(VOICES, v); note = (read(os.path.join(d, "model.onnx.sha256")) or "").split()
            if (len(note) == 2 and note[1] == str(os.path.getsize(os.path.join(d, "model.onnx")))
                    and all(os.path.isfile(os.path.join(d, f)) for f in ("tokens.txt", "voice.json"))):
                good += 1
        if known and good >= known: return "on", f"{good}/{known} voices"
        return ("partial" if good else "off"), f"{good}/{known or '?'} voices"
    def apply(self, log):
        sh([sys.executable, "-I", "-u", os.path.join(SP, "fetch_voices.py")], log, env=prefix.child_env(P))

class SpRegistry(Part):
    name = "Voices registered with Windows"
    desc = "Adds the voice entries the setup doesn't write under Proton (both voice lists + the engine)."
    needs_wow_closed = True
    def status(self):
        if not PFX: return "na", "WoW prefix not found"
        if not FLAVORS: return "na", "install the SpokenPlayers addon first"
        if prefix.runner_problem(P): return "na", prefix.runner_problem(P)
        reg = read(os.path.join(PFX, "system.reg")) or ""
        cl = set(re.findall(r"^\[Software\\\\Microsoft\\\\Speech\\\\Voices\\\\Tokens\\\\SpokenPlayers_([^\]\\\\]+)\]", reg, re.M))
        oc = set(re.findall(r"^\[Software\\\\Microsoft\\\\Speech_OneCore\\\\Voices\\\\Tokens\\\\SpokenPlayers_([^\]\\\\]+)\]", reg, re.M))
        eng = f"[Software\\\\Classes\\\\CLSID\\\\{CLSID}]" in reg
        want = set(voice_folders())
        note = "  (may be out of date while WoW runs)" if wow_running() else ""
        if not want: return "na", "no voices yet: switch on Voice models first"
        if want <= cl and want <= oc and eng: return "on", f"{len(want)}/{len(want)} in both lists{note}"
        if not (cl or oc or eng): return "off", f"not registered{note}"
        return "partial", f"{len(want & cl)}/{len(want)} classic, {len(want & oc)}/{len(want)} OneCore, engine {'yes' if eng else 'no'}{note}"
    def warn(self, turning_on):
        st, detail = SpModels().status()
        if turning_on and st != "on":
            return (f"Note: Voice models is not complete ({detail}). Only the voices that are there now get "
                    "registered. Switch on Voice models first, or flip this again afterwards.")
        return ""
    def _import(self, files, log):
        for f in files:
            shutil.copy(os.path.join(SP, f), os.path.join(PFX, "drive_c", f))
            run_wine(["reg", "import", f"C:\\{f}"], log)
    def apply(self, log):
        sh([sys.executable, "-I", os.path.join(SP, "make_spoken_reg.py")], log, env=prefix.child_env(P, FLAVORS[0]))
        self._import(["spoken_voices.reg", "spoken_voices_onecore.reg"], log)
    def revert(self, log):
        sh([sys.executable, "-I", os.path.join(SP, "make_spoken_reg.py")], log, env=prefix.child_env(P, FLAVORS[0]))
        self._import(["spoken_voices_remove.reg"], log)

class SpWineTTS(Part):
    name = "Windows voices allowed under Wine"
    desc = "WoW's hidden setting winePlatformTTS (WoW warns it \"can cause crashes\")."
    needs_wow_closed = True
    def _files(self):
        return [os.path.join(WOW, f, "WTF/Config.wtf") for f in FLAVORS if os.path.exists(os.path.join(WOW, f, "WTF/Config.wtf"))]
    def status(self):
        fs = self._files()
        if not fs: return "na", "start WoW once first (no Config.wtf yet)"
        on = sum(bool(re.search(rb'^SET winePlatformTTS "1"', read(f, "rb"), re.M)) for f in fs)
        return ("on" if on == len(fs) else "partial" if on else "off"), ", ".join(FLAVORS)
    def _edit(self, value, log):
        for f in self._files():
            b = read(f, "rb"); nl = b"\r\n" if b"\r\n" in b else b"\n"
            lines = [l for l in b.split(nl) if not l.startswith(b"SET winePlatformTTS ")]
            if value:
                lines.insert(0, b'SET winePlatformTTS "1"')
            with open(f, "wb") as o: o.write(nl.join(lines))
            log(f"{'set' if value else 'removed'} winePlatformTTS in {os.path.relpath(f, WOW)}")
    def apply(self, log): self._edit(True, log)
    def revert(self, log): self._edit(False, log)

class SpSapi(Part):
    name = "Patched speech library (sapi.dll)"
    desc = "Experimental fix for Wine/Proton's sapi.dll so WoW can speak. Built from your own Wine/Proton's copy.\nWine/Proton updates undo it: switch it on again after updating."
    needs_wow_closed = True
    def status(self):
        if not PFX: return "na", "WoW prefix not found"
        dll = prefix.prefix_sapi(P)
        ov = re.search(r'^"sapi"="([^"]*)"', read(os.path.join(PFX, "user.reg")) or "", re.M)
        native = bool(ov and ov.group(1).startswith("native"))
        if prefix.runner_problem(P): return "na", prefix.runner_problem(P)
        patched = os.path.isfile(dll) and not os.path.islink(dll) and b"Wine builtin DLL" not in (read(dll, "rb") or b"")
        if patched and native: return "on", "installed"
        if not (shutil.which("objdump") and shutil.which("as")):
            return "na", "needs objdump and as (binutils) to build the patch"
        if not prefix.wine_sapi(P):
            return "na", "can't find this Wine/Proton's sapi.dll to build the patch from"
        if patched or native:
            return "partial", ("override set but the original dll is back (Wine/Proton updated?)" if native
                               else "patched dll without the native override")
        return "off", "Wine/Proton's original"
    def apply(self, log):
        sh([os.path.join(SP, "apply_sapi_patch.sh")], log, env=prefix.child_env(P))
    def revert(self, log):
        sh([os.path.join(SP, "apply_sapi_patch.sh"), "undo"], log, env=prefix.child_env(P))

class SpSetting(Part):
    needs_wow_closed = True
    key = ""
    def status(self):
        fs = saved_vars()
        if not fs: return "na", "log in to WoW once with the addon enabled"
        vals = [re.search(rf'\["{self.key}"\] = (\w+)', read(f) or "") for f in fs]
        on = sum(bool(v and v.group(1) == "true") for v in vals)
        return ("on" if on == len(fs) else "partial" if on else "off"), f"{on}/{len(fs)} accounts"
    def _edit(self, value, log):
        v = "true" if value else "false"
        for f in saved_vars():
            b = read(f, "rb"); nl = b"\r\n" if b"\r\n" in b else b"\n"
            new, n = re.subn(rb'\["' + self.key.encode() + rb'"\] = \w+', b'["' + self.key.encode() + b'"] = ' + v.encode(), b)
            if not n:
                new = b.replace(b"SpokenPlayersDB = {" + nl, b"SpokenPlayersDB = {" + nl + b'["' + self.key.encode() + b'"] = ' + v.encode() + b"," + nl, 1)
            with open(f, "wb") as o: o.write(new)
            log(f'set {self.key} = {v} in {os.path.relpath(f, WOW).split("/WTF/")[0]} account settings')
    def apply(self, log): self._edit(True, log)
    def revert(self, log): self._edit(False, log)

class SpGuild(SpSetting):
    name = "Read guild chat aloud"
    desc = "SpokenPlayers addon setting (same as the Guild option in its settings)."
    key = "guild"

class SpGuildInst(SpSetting):
    name = "Guild chat in dungeons/raids/BGs"
    desc = "SpokenPlayers addon setting \"guild in instance\"."
    key = "guildInInstance"

MENU_ON = b"if false and Menu and Menu.ModifyMenu then"
MENU_OFF = b"if Menu and Menu.ModifyMenu then"
MENU_NOTE = b"-- steamos-ally-fixes: right-click menu entries disabled (they taint menus and block Trade/Invite/actions)"

class SpMenus(Part):
    """ON = the addon's Set Voice / Mute entries are kept out of player right-click menus.
    v0.21+ has its own setting for this ("Right-click menu entries", saved as playerMenu), so the switch
    flips that and it survives addon updates. Older versions have no setting: there the switch makes
    the old one-line edit in Overrides.lua instead (undone by updates)."""
    name = "Right-click menu entries off (fixes Trade/Invite)"
    desc = ("Keeps the addon's Set Voice / Mute entries out of player right-click menus. They can \"taint\" the menu,\n"
            "and then WoW blocks Trade, Invite, Add Friend and even action-bar buttons until /reload.\n"
            "Same as unticking \"Right-click menu entries\" in /sp (v0.21+). /sp voice <name> still works.")
    needs_wow_closed = True
    key = "playerMenu"
    def _files(self):
        return [p for f in FLAVORS for p in [os.path.join(WOW, f, "Interface/AddOns/SpokenPlayers/Overrides.lua")] if os.path.isfile(p)]
    def _lines(self, b):
        nl = b"\r\n" if b"\r\n" in b else b"\n"
        return b.split(nl), nl
    def _has_setting(self, f):
        return b"playerMenu" in (read(f, "rb") or b"")
    def _setting_off(self, f):
        return bool(re.search(rf'\["{self.key}"\] = false', read(f) or ""))
    def status(self):
        fs = self._files()
        if not fs: return "na", "install the SpokenPlayers addon first"
        sv = saved_vars()
        on = 0
        for f in fs:
            s = [l.strip() for l in self._lines(read(f, "rb"))[0]]
            if MENU_ON in s:
                on += 1
            elif self._has_setting(f):
                if not sv: return "na", "log in to WoW once with the addon enabled"
                on += all(self._setting_off(v) for v in sv)
            elif MENU_OFF not in s:
                return "na", "this addon version's menu code looks different; the switch doesn't know how to change it"
        return ("on" if on == len(fs) else "partial" if on else "off"), ("entries off" if on == len(fs) else
                "entries in menus" if not on else f"{on}/{len(fs)} clients")
    def _set(self, value, log):
        v = b"true" if value else b"false"; k = self.key.encode()
        for f in saved_vars():
            b = read(f, "rb"); nl = b"\r\n" if b"\r\n" in b else b"\n"
            new, n = re.subn(rb'\["' + k + rb'"\] = \w+', b'["' + k + b'"] = ' + v, b)
            if not n:
                new = b.replace(b"SpokenPlayersDB = {" + nl, b"SpokenPlayersDB = {" + nl + b'["' + k + b'"] = ' + v + b"," + nl, 1)
            with open(f, "wb") as o: o.write(new)
            log(f'set {self.key} = {v.decode()} in {os.path.relpath(f, WOW).split("/WTF/")[0]} account settings')
    def _edit(self, turning_on, log):
        for f in self._files():
            lines, nl = self._lines(read(f, "rb"))
            stripped = [l.strip() for l in lines]
            # old one-line edit: only made on versions without the setting; always taken out when turning off
            if turning_on and (self._has_setting(f) or MENU_OFF not in stripped): continue
            if not turning_on and MENU_ON not in stripped: continue
            new = []
            for l in lines:
                if not turning_on and l.strip().startswith(b"--") and b"right-click menu entries disabled" in l:
                    continue
                if turning_on and l.strip() == MENU_OFF:
                    new += [MENU_NOTE, l.replace(MENU_OFF, MENU_ON)]
                elif not turning_on and l.strip() == MENU_ON:
                    new.append(l.replace(MENU_ON, MENU_OFF))
                else:
                    new.append(l)
            with open(f, "wb") as o: o.write(nl.join(new))
            log(f"{'disabled' if turning_on else 'restored'} the menu entries in {os.path.relpath(f, WOW)}")
    def apply(self, log): self._edit(True, log); self._set(False, log)
    def revert(self, log): self._edit(False, log); self._set(True, log)

ADDONS = {
    "decktation": ("Decktation fixes", "ROG Ally + SteamOS", [DeckController(), DeckLegacy(), DeckMicLevels(), DeckNoise(), DeckKeywords()]),
    "spoken": ("Spoken Players fixes", None, [SpModels(), SpRegistry(), SpWineTTS(), SpSapi(), SpGuild(), SpGuildInst(), SpMenus()]),
}

# ---------------------------------------------------------------- UI

BG, CARD, FG, DIM, ON, OFF, PART, NA = "#1e2127", "#2a2e36", "#e8e8e8", "#9aa0a8", "#3fb27f", "#5b616b", "#d9a43c", "#444a54"
F = ("Noto Sans", 13); FB = ("Noto Sans", 14, "bold"); FS = ("Noto Sans", 11); FT = ("Noto Sans", 18, "bold")

class Switch(tk.Canvas):
    W, H = 74, 38
    def __init__(self, master, command):
        super().__init__(master, width=self.W, height=self.H, bg=CARD, highlightthickness=0, cursor="hand2")
        self.command, self.state, self.enabled = command, "na", False
        self.bind("<Button-1>", lambda e: self.enabled and self.command())
    def show(self, state, enabled):
        self.state, self.enabled = state, enabled
        self.delete("all"); w, h, r = self.W, self.H, self.H / 2
        col = {"on": ON, "off": OFF, "partial": PART}.get(state, NA)
        self.create_oval(0, 0, h, h, fill=col, outline=col); self.create_oval(w - h, 0, w, h, fill=col, outline=col)
        self.create_rectangle(r, 0, w - r, h, fill=col, outline=col)
        x = w - r if state == "on" else w / 2 if state == "partial" else r
        knob = "#ffffff" if enabled else "#9a9a9a"
        self.create_oval(x - r + 4, 4, x + r - 4, h - 4, fill=knob, outline=knob)

class App:
    def __init__(self, key):
        title, sub, self.parts = ADDONS[key]
        if key == "spoken":
            sub = (f"WoW prefix: {P['source']}  ·  client {', '.join(FLAVORS) or '?'}" if P
                   else "WoW prefix not found (set PFX= / WOW_DIR=, see the guide)")
        self.busy = False
        self.root = r = tk.Tk(); r.title(title); r.configure(bg=BG); r.minsize(820, 0)
        tk.Label(r, text=title, font=FT, bg=BG, fg=FG).pack(anchor="w", padx=20, pady=(16, 0))
        tk.Label(r, text=sub + "   ·   switches show what is installed right now", font=FS, bg=BG, fg=DIM).pack(anchor="w", padx=20)
        box = tk.Frame(r, bg=BG); box.pack(fill="x", padx=14, pady=8)
        self.rows = []
        for p in self.parts:
            c = tk.Frame(box, bg=CARD); c.pack(fill="x", pady=3)
            sw = Switch(c, lambda p=p: self.flip(p)); sw.pack(side="right", padx=16, pady=8)
            t = tk.Frame(c, bg=CARD); t.pack(side="left", fill="x", expand=True, padx=14, pady=6)
            tk.Label(t, text=p.name, font=FB, bg=CARD, fg=FG).pack(anchor="w")
            st = tk.Label(t, text="", font=F, bg=CARD, fg=DIM); st.pack(anchor="w")
            tk.Label(t, text=p.desc, font=FS, bg=CARD, fg=DIM, justify="left").pack(anchor="w")
            self.rows.append((p, sw, st))
        bar = tk.Frame(r, bg=BG); bar.pack(fill="x", padx=14)
        self.btn(bar, "Refresh", self.refresh).pack(side="left", padx=4)
        if key == "decktation":
            self.btn(bar, "Restart Decky", self.restart_decky).pack(side="left", padx=4)
        self.btn(bar, "Close", r.destroy).pack(side="right", padx=4)
        self.logw = tk.Text(r, height=6, width=10, bg="#15171b", fg=DIM, font=("Noto Mono", 10), relief="flat", wrap="word", highlightthickness=0, bd=0, padx=8, pady=6)
        self.logw.pack(fill="both", expand=True, padx=14, pady=(8, 14))
        self.refresh()

    def btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, font=F, bg=CARD, fg=FG, activebackground=OFF,
                         activeforeground=FG, relief="flat", padx=18, pady=8, cursor="hand2", highlightthickness=0, bd=0)

    def log(self, msg):
        self.root.after(0, lambda: (self.logw.insert("end", msg + "\n"), self.logw.see("end")))

    def refresh(self):
        for p, sw, st in self.rows:
            try:
                state, detail = p.status()
            except Exception as e:
                state, detail = "na", f"couldn't check: {e}"
            label = {"on": "ON", "off": "OFF", "partial": "PARTLY ON", "na": "UNAVAILABLE"}[state]
            if state == "on" and not p.can_revert: detail += "  (can't be switched off here)"
            st.config(text=f"{label}  ·  {detail}", fg={"on": ON, "partial": PART}.get(state, DIM))
            sw.show(state, not self.busy and state != "na" and (p.can_revert or state != "on"))

    def flip(self, p):
        state, _ = p.status()
        turning_on = state != "on"     # off or partial -> finish installing
        if not turning_on and not p.can_revert:
            return
        if p.needs_wow_closed and wow_running():
            messagebox.showwarning(p.name, "Close WoW and Battle.net first, then try again."); return
        verb = ("Finish installing" if state == "partial" else "Turn on") if turning_on else "Turn off (revert)"
        w = p.warn(turning_on)
        if not messagebox.askyesno(p.name, f"{verb}: {p.name}?\n\n{p.desc}" + (f"\n\n{w}" if w else "")):
            return
        self.busy = True; self.refresh()
        self.log(f"--- {verb}: {p.name}")
        def work():
            try:
                (p.apply if turning_on else p.revert)(self.log)
                self.log("done." + (f" {p.after}" if p.after else ""))
            except Exception as e:
                self.log(f"FAILED: {e}")
            finally:
                self.busy = False
                self.root.after(0, self.refresh)
        threading.Thread(target=work, daemon=True).start()

    def restart_decky(self):
        if password_problem():
            messagebox.showwarning("Restart Decky", password_problem()); return
        if messagebox.askyesno("Restart Decky", "Restart Decky Loader now? Plugins reload in a few seconds."):
            threading.Thread(target=lambda: self._try(["pkexec", "systemctl", "restart", "plugin_loader"]), daemon=True).start()

    def _try(self, cmd):
        try: sh(cmd, self.log); self.log("done.")
        except Exception as e: self.log(f"FAILED: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ADDONS:
        sys.exit("usage: ally_toggles.py decktation|spoken")
    App(sys.argv[1]).root.mainloop()
