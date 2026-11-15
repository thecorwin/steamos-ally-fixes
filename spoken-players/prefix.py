#!/usr/bin/env python3
"""Find the WoW Wine prefix, and the Wine that runs it, wherever it was installed.

Looks in Steam (every library, non-Steam shortcuts included), Heroic and Lutris
(normal and Flatpak installs). WoW itself is found through Battle.net's own install
list, so any folder or drive letter works. Optional overrides:
  PFX=<folder>      the prefix (the folder with drive_c in it, or its parent with pfx/ in it)
  WINE=<file>       the wine (or Proton "proton") binary that runs that prefix
  APPID=<n>         a Steam compatdata number
  WOW_DIR=<folder>  the World of Warcraft folder (the one with _retail_ in it)

  python3 -I prefix.py                 show what was found
  python3 -I prefix.py shell           print it as shell variables (used by apply_sapi_patch.sh)
  python3 -I prefix.py wine <args>     run wine in that prefix, then wait for the registry to save
"""
import glob, json, os, re, shlex, shutil, subprocess, sys

HOME = os.path.expanduser("~")
FLATPAK_PT = ["flatpak", "run", "com.github.Matoking.protontricks"]
SP_DEFAULT = "C:\\Program Files\\Spoken Players"

def _read(path, mode="r"):
    try:
        with open(path, mode) as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None

def _pfx_dir(p):
    """Accept either the prefix itself or a Proton-style parent with pfx/ inside."""
    if not p:
        return None
    p = os.path.expanduser(p)
    if os.path.isdir(os.path.join(p, "drive_c")):
        return p
    if os.path.isdir(os.path.join(p, "pfx", "drive_c")):
        return os.path.join(p, "pfx")
    return None

def wine_from(binpath):
    """wine binary from a wine binary, a Proton 'proton' script or a Proton/Wine folder."""
    if not binpath:
        return None
    b = os.path.expanduser(binpath)
    root = b if os.path.isdir(b) else os.path.dirname(b)
    if os.path.isfile(b) and os.path.basename(b) not in ("proton",):
        return b
    for c in ("files/bin/wine", "dist/bin/wine", "bin/wine", "bin/wine64"):
        if os.path.isfile(os.path.join(root, c)):
            return os.path.join(root, c)
    return None

# ---------------------------------------------------------------- Steam

def steam_roots():
    seen, out = set(), []
    for r in ("~/.local/share/Steam", "~/.steam/steam", "~/.steam/root",
              "~/.var/app/com.valvesoftware.Steam/.local/share/Steam"):
        r = os.path.realpath(os.path.expanduser(r))
        if os.path.isdir(os.path.join(r, "steamapps")) and r not in seen:
            seen.add(r); out.append(r)
    return out

def steam_libraries():
    libs = []
    for r in steam_roots():
        libs.append(r)
        vdf = _read(os.path.join(r, "steamapps/libraryfolders.vdf")) or ""
        libs += re.findall(r'"path"\s+"([^"]+)"', vdf)
    seen, out = set(), []
    for l in libs:
        l = os.path.realpath(l)
        if l not in seen and os.path.isdir(os.path.join(l, "steamapps")):
            seen.add(l); out.append(l)
    return out

def steam_wine(compat):
    """Proton's wine from <compatdata>/<appid>/config_info (written by Steam on each launch)."""
    for line in (_read(os.path.join(compat, "config_info")) or "").splitlines():
        m = re.match(r"(/.*?/(files|dist))/", line)
        if m and os.path.isfile(os.path.join(m.group(1), "bin/wine")):
            return os.path.join(m.group(1), "bin/wine")
    return None

def steam_prefixes():
    want = os.environ.get("APPID")
    for lib in steam_libraries():
        for compat in sorted(glob.glob(os.path.join(lib, "steamapps/compatdata/*"))):
            appid = os.path.basename(compat)
            if want and appid != want:
                continue
            pfx = _pfx_dir(os.path.join(compat, "pfx"))
            if pfx:
                yield {"pfx": pfx, "source": f"Steam (appid {appid})", "appid": appid,
                       "wine": steam_wine(compat)}

# ---------------------------------------------------------------- Heroic

def heroic_prefixes():
    for conf in ("~/.config/heroic", "~/.var/app/com.heroicgameslauncher.hgl/config/heroic"):
        conf = os.path.expanduser(conf)
        default_wine = None
        try:
            d = json.loads(_read(os.path.join(conf, "config.json")) or "{}").get("defaultSettings", {})
            default_wine = wine_from((d.get("wineVersion") or {}).get("bin"))
        except (ValueError, AttributeError):
            pass
        for f in sorted(glob.glob(os.path.join(conf, "GamesConfig/*.json"))):
            try:
                data = json.loads(_read(f) or "{}")
            except ValueError:
                continue
            for name, g in data.items():
                if not isinstance(g, dict):
                    continue
                pfx = _pfx_dir(g.get("winePrefix"))
                if pfx:
                    wine = wine_from((g.get("wineVersion") or {}).get("bin")) or default_wine
                    yield {"pfx": pfx, "source": f"Heroic ({name})", "appid": None, "wine": wine}

# ---------------------------------------------------------------- Lutris

def _yaml_value(text, section, key):
    """Tiny reader for Lutris' simple YAML: the value of '  key:' under 'section:'."""
    m = re.search(rf"^{section}:\s*\n((?:[ \t]+.*\n?)*)", text, re.M)
    if m:
        v = re.search(rf"^[ \t]+{key}:[ \t]*(.+)$", m.group(1), re.M)
        if v:
            return v.group(1).strip().strip("'\"")
    return None

def lutris_prefixes():
    for base, data in (("~/.config/lutris", "~/.local/share/lutris"),
                       ("~/.var/app/net.lutris.Lutris/config/lutris", "~/.var/app/net.lutris.Lutris/data/lutris")):
        base, data = os.path.expanduser(base), os.path.expanduser(data)
        runners = os.path.join(data, "runners/wine")
        default = _yaml_value(_read(os.path.join(base, "runners/wine.yml")) or "", "wine", "version")
        installed = sorted(glob.glob(os.path.join(runners, "*")), key=os.path.getmtime, reverse=True)
        for f in sorted(glob.glob(os.path.join(base, "games/*.yml")) + glob.glob(os.path.join(data, "games/*.yml"))):
            text = _read(f) or ""
            pfx = _pfx_dir(_yaml_value(text, "game", "prefix"))
            if not pfx:
                continue
            ver = _yaml_value(text, "wine", "version") or default
            wine = None
            if ver:
                wine = wine_from(os.path.join(runners, ver)) or (wine_from(ver) if ver.startswith("/") else None)
            if not wine and installed:
                wine = wine_from(installed[0])
            yield {"pfx": pfx, "source": f"Lutris ({os.path.basename(f)[:-4]})", "appid": None,
                   "wine": wine or shutil.which("wine")}

# ---------------------------------------------------------------- inside a prefix

def win_to_unix(pfx, winpath):
    m = re.match(r"^([A-Za-z]):[\\/]*(.*)$", winpath)
    if not m:
        return None
    drive = os.path.join(pfx, "dosdevices", m.group(1).lower() + ":")
    if not os.path.exists(drive):
        if m.group(1).lower() != "c":
            return None
        drive = os.path.join(pfx, "drive_c")
    rest = m.group(2).replace("\\", "/").rstrip("/")
    return os.path.join(os.path.realpath(drive), rest) if rest else os.path.realpath(drive)

def is_wow(d):
    return bool(d) and os.path.isdir(d) and any(
        re.fullmatch(r"_\w+_", f) and os.path.isdir(os.path.join(d, f)) for f in os.listdir(d))

def find_wow_dir(pfx):
    cands = []
    db = _read(os.path.join(pfx, "drive_c/ProgramData/Battle.net/Agent/product.db"), "rb") or b""
    for m in re.findall(rb"[A-Za-z]:/[ -~]+", db):   # protobuf strings: the field byte after may be printable
        s = m.decode()
        cands += [s[:len(s) - k] for k in range(min(4, len(s) - 3))]
    cands += ["C:\\Program Files (x86)\\World of Warcraft", "C:\\Program Files\\World of Warcraft"]
    for c in cands:
        d = win_to_unix(pfx, c)
        if d and os.path.basename(d) and is_wow(d) and os.path.exists(os.path.join(d, ".build.info")):
            return d
    # Last resort, only where Battle.net is installed: look a few folders deep on each drive.
    if not os.path.isdir(os.path.join(pfx, "drive_c/ProgramData/Battle.net")):
        return None
    for drive in sorted(glob.glob(os.path.join(pfx, "dosdevices/[a-y]:"))):
        root = os.path.realpath(drive)
        for depth in ("*", "*/*", "*/*/*"):
            for b in glob.glob(os.path.join(root, depth, ".build.info")):
                d = os.path.dirname(b)
                if "windows" not in d.lower().split(os.sep) and is_wow(d):
                    return d
    return None

def flavors(wow):
    try:
        return sorted(f for f in os.listdir(wow) if re.fullmatch(r"_\w+_", f)
                      and os.path.isdir(os.path.join(wow, f, "Interface/AddOns/SpokenPlayers")))
    except OSError:
        return []

def spoken_dir(pfx):
    """(Windows path, unix path) of the Spoken Players voicepack, from its uninstall entry."""
    reg = _read(os.path.join(pfx, "system.reg")) or ""
    m = re.search(r'^"Inno Setup: App Path"="([^"]*Spoken Players[^"]*)"', reg, re.M)
    win = m.group(1).replace("\\\\", "\\").rstrip("\\") if m else SP_DEFAULT
    return win, win_to_unix(pfx, win)

def complete(p):
    """Fill in the WoW folder, client folders and voicepack folder for a prefix."""
    p["wow"] = os.path.realpath(os.path.expanduser(os.environ["WOW_DIR"])) if os.environ.get("WOW_DIR") else find_wow_dir(p["pfx"])
    p["flavors"] = flavors(p["wow"]) if p["wow"] else []
    p["sp_win"], p["sp_dir"] = spoken_dir(p["pfx"])
    return p

def candidates():
    if os.environ.get("PFX"):
        pfx = _pfx_dir(os.environ["PFX"])
        if not pfx:
            return []
        appid = None
        m = re.search(r"/steamapps/compatdata/(\d+)/pfx$", pfx)
        if m: appid = m.group(1)
        compat = os.path.dirname(pfx) if appid else None
        wine = wine_from(os.environ.get("WINE")) or (steam_wine(compat) if compat else None) or shutil.which("wine")
        return [{"pfx": pfx, "source": "PFX=" + pfx, "appid": appid, "wine": wine}]
    out, seen = [], set()
    for gen in (steam_prefixes, heroic_prefixes, lutris_prefixes):
        for p in gen():
            key = os.path.realpath(p["pfx"])
            if key not in seen:
                seen.add(key); out.append(p)
    if os.environ.get("WINE"):
        for p in out: p["wine"] = wine_from(os.environ["WINE"])
    return out

def find():
    """The prefix with WoW (most clients with the addon wins), or None."""
    best = None
    for p in candidates():
        complete(p)
        if p["wow"]:
            score = (len(p["flavors"]), 1)
            if not best or score > best[0]:
                best = (score, p)
    return best[1] if best else None

# ---------------------------------------------------------------- running wine

def protontricks():
    if shutil.which("protontricks"):
        return ["protontricks"]
    if shutil.which("flatpak") and subprocess.run(FLATPAK_PT[:1] + ["info", FLATPAK_PT[2]],
                                                  capture_output=True).returncode == 0:
        return FLATPAK_PT
    return None

def runner_problem(p):
    """None if wine commands can run in this prefix, else what to do."""
    if p.get("appid") and protontricks():
        return None
    if p.get("wine") and os.path.isfile(p["wine"]):
        return None
    if p.get("appid"):
        return "install protontricks, or start WoW from Steam once so Steam records its Proton"
    return "couldn't find the Wine/Proton this prefix uses: set WINE=<path to its wine or proton>"

def wine_cmds(p, args):
    """[(argv, env)] that run `wine <args>` in the prefix and wait for wineserver to finish."""
    pt = protontricks() if p.get("appid") else None
    if pt:
        return [(pt + ["-c", shlex.join(["wine"] + args) + "; wineserver -w", p["appid"]], {})]
    wine = p["wine"]
    env = {"WINEPREFIX": p["pfx"], "WINEDEBUG": "-all"}
    server = os.path.join(os.path.dirname(wine), "wineserver")
    cmds = [([wine] + args, env)]
    if os.path.isfile(server):
        cmds.append(([server, "-w"], env))
    return cmds

def wine_sapi(p):
    """The sapi.dll that ships with the Wine/Proton running this prefix (the patch is built from it)."""
    wine = p.get("wine")
    if not wine:
        return None
    root = os.path.dirname(os.path.dirname(wine))
    for c in ("lib/wine/x86_64-windows/sapi.dll", "lib64/wine/x86_64-windows/sapi.dll"):
        if os.path.isfile(os.path.join(root, c)):
            return os.path.join(root, c)
    return None

def prefix_sapi(p):
    d = os.path.join(p["pfx"], "drive_c/windows/system32")
    common = os.path.join(d, "Speech/Common/sapi.dll")
    return common if os.path.lexists(common) or not os.path.lexists(os.path.join(d, "sapi.dll")) else os.path.join(d, "sapi.dll")

def uses_links(p):
    """Proton prefixes link their system dlls to Proton's files; plain Wine copies them."""
    return os.path.islink(os.path.join(p["pfx"], "drive_c/windows/system32/kernel32.dll"))

def running(p):
    """WoW or Battle.net running, or this prefix's wineserver still up (other games don't count)."""
    for name in ("Wow.exe", "WowClassic.exe", "Battle.net.exe", "Agent.exe"):
        if subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0:
            return True
    try:
        st = os.stat(p["pfx"])
    except OSError:
        return False
    return os.path.exists(f"/tmp/.wine-{os.getuid()}/server-{st.st_dev:x}-{st.st_ino:x}/socket")

def child_env(p, flavor=None):
    """Environment that makes the other scripts use exactly this prefix."""
    env = {"PFX": p["pfx"], "WOW_DIR": p["wow"] or ""}
    if p.get("wine"): env["WINE"] = p["wine"]
    if p.get("appid"): env["APPID"] = p["appid"]
    if flavor: env["WOW_FLAVOR"] = flavor
    return env

# ---------------------------------------------------------------- command line

if __name__ == "__main__":
    p = find()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if not p:
        sys.exit("WoW prefix not found. Set PFX=<prefix folder> (and WINE=<its wine> outside Steam), "
                 "or WOW_DIR=<World of Warcraft folder> if WoW is somewhere unusual.")
    if cmd == "shell":
        vals = {"PFX": p["pfx"], "WOW": p["wow"], "APPID": p.get("appid") or "", "WINE": p.get("wine") or "",
                "WINE_SAPI": wine_sapi(p) or "", "PFX_SAPI": prefix_sapi(p),
                "USES_LINKS": "1" if uses_links(p) else "", "RUNNING": "1" if running(p) else "",
                "RUNNER_PROBLEM": runner_problem(p) or "", "SOURCE": p["source"]}
        for k, v in vals.items():
            print(f"{k}={shlex.quote(v)}")
    elif cmd == "wine":
        if runner_problem(p):
            sys.exit(runner_problem(p))
        for argv, env in wine_cmds(p, sys.argv[2:]):
            r = subprocess.run(argv, env={**os.environ, **env}).returncode
            if r and argv[-1] != "-w":
                sys.exit(r)
    else:
        print(f"prefix:    {p['pfx']}\nfound via: {p['source']}\nwine:      {p.get('wine') or '-'}"
              f"\nWoW:       {p['wow']}\nclients:   {', '.join(p['flavors']) or 'none with the SpokenPlayers addon'}"
              f"\nvoicepack: {p['sp_win']} -> {p['sp_dir']}\nrunner:    {runner_problem(p) or 'ok'}")
