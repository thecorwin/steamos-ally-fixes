#!/usr/bin/env python3
"""Download any Spoken Players voice models the voicepack installer skipped under Proton.

Under Proton the official voicepack setup copies its program files but silently downloads
none of the newer voices. This fetches them from the same Hugging Face repo the installer
uses, at the same pinned revision, and checks every model.onnx against the SHA-256 and size
Hugging Face publishes for it (and, when found, the checksum inside the installer's
unins000.dat). Voices that are already complete are left alone.

Usage (close WoW first; run the official voicepack setup once before this):
  APPID=<n> python3 -I fetch_voices.py              download missing / broken voices
  APPID=<n> python3 -I fetch_voices.py --check      only report, download nothing
  APPID=<n> python3 -I fetch_voices.py worgen_male  only these voices
Optional: REVISION=<40-hex commit> to override the revision read from unins000.dat.
Optional: VOICES_DIR=<path> to use a different voices folder (for testing).
"""
import hashlib, json, os, re, sys, tempfile, urllib.request

REPO = "sahnetee/spoken-players"
FILES = ("model.onnx", "tokens.txt", "voice.json")

base = os.environ.get("VOICES_DIR")
pfx = os.path.expanduser("~/.local/share/Steam/steamapps/compatdata/%s/pfx" % os.environ.get("APPID", ""))
install = os.path.join(pfx, "drive_c/Program Files/Spoken Players")
voices_dir = base or os.path.join(install, "voices")
if not base and not os.environ.get("APPID"):
    sys.exit("set APPID to your WoW shortcut appid (ls ~/.local/share/Steam/steamapps/compatdata/)")
if not os.path.isdir(voices_dir):
    sys.exit(f"no voices folder at {voices_dir}. Run the official voicepack setup in this prefix first.")

# The installer's own data: pinned revision + checksum list (UTF-16 text inside unins000.dat).
installer_text = ""
try:
    installer_text = open(os.path.join(install, "unins000.dat"), "rb").read().decode("utf-16-le", "ignore")
except OSError:
    pass
rev = os.environ.get("REVISION")
if not rev:
    m = re.search(r"huggingface\.co/" + re.escape(REPO) + r"/resolve/([0-9a-f]{40})/", installer_text)
    if not m:
        sys.exit("couldn't read the revision from unins000.dat; set REVISION=<commit> (see the README)")
    rev = m.group(1)
print(f"Hugging Face revision {rev}")

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "spoken-players-proton-fix"})
    return urllib.request.urlopen(req, timeout=60)

def api_tree(path=""):
    with get(f"https://huggingface.co/api/models/{REPO}/tree/{rev}/{path}") as r:
        return json.load(r)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

remote = sorted(x["path"] for x in api_tree() if x["type"] == "directory")
wanted = [a for a in sys.argv[1:] if not a.startswith("-")] or remote
check_only = "--check" in sys.argv
unknown = set(wanted) - set(remote)
if unknown:
    sys.exit(f"not in the voicepack: {sorted(unknown)}")

bad = 0
for voice in wanted:
    meta = {x["path"].split("/")[-1]: x for x in api_tree(voice)}
    lfs = meta["model.onnx"]["lfs"]
    want_sha, want_size = lfs["oid"], lfs["size"]
    in_installer = want_sha in installer_text.replace("\0", "")
    d = os.path.join(voices_dir, voice)
    model = os.path.join(d, "model.onnx")
    complete = (all(os.path.isfile(os.path.join(d, f)) for f in FILES)
                and os.path.getsize(model) == want_size)
    try:   # the installer's "<sha> <size>" note saves hashing 77 MB per voice
        noted = open(model + ".sha256").read().split()[0] == want_sha
    except (OSError, IndexError):
        noted = False
    if complete and (noted or check_only or sha256(model) == want_sha):
        print(f"  ok        {voice}")
        continue
    if check_only:
        print(f"  MISSING   {voice}"); bad += 1; continue
    print(f"  download  {voice} ({want_size / 1e6:.0f} MB){'' if in_installer else '  [checksum not found in installer data]'}")
    os.makedirs(d, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".dl-", dir=d)
    try:
        for f in FILES:
            with get(f"https://huggingface.co/{REPO}/resolve/{rev}/{voice}/{f}") as r, \
                 open(os.path.join(tmp, f), "wb") as out:
                while chunk := r.read(1 << 20):
                    out.write(chunk)
        got = sha256(os.path.join(tmp, "model.onnx"))
        if got != want_sha or os.path.getsize(os.path.join(tmp, "model.onnx")) != want_size:
            print(f"  FAILED    {voice}: checksum mismatch, nothing installed"); bad += 1; continue
        for f in FILES:
            os.replace(os.path.join(tmp, f), os.path.join(d, f))
        with open(model + ".sha256", "w") as out:   # same "<sha> <size>" file the installer writes
            out.write(f"{want_sha} {want_size}")
        print(f"  installed {voice}")
    finally:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)

print(f"{len(wanted) - bad}/{len(wanted)} voices OK" + ("" if not bad else "  (re-run to retry)"))
if not check_only:
    print("Next: run make_spoken_reg.py and import the .reg files so Windows/WoW can see the voices.")
sys.exit(1 if bad else 0)
