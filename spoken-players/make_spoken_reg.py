#!/usr/bin/env python3
"""Regenerate the Spoken Players voice registry files from the installed voices/ folders.

Writes spoken_voices.reg (classic SAPI list + engine CLSID) and spoken_voices_onecore.reg
(OneCore list) next to this script, as UTF-16 .reg files ready for `wine reg import`.
Every voice name is checked against the addon's Speakers.lua.
Usage: APPID=<n> [WOW_FLAVOR=_retail_] python3 -I make_spoken_reg.py
"""
import os, re, sys

PFX = os.path.expanduser("~/.local/share/Steam/steamapps/compatdata/" + os.environ["APPID"] + "/pfx")
VOICES = os.path.join(PFX, "drive_c/Program Files/Spoken Players/voices")
SPEAKERS = os.path.join(PFX, "drive_c/Program Files (x86)/World of Warcraft/" + os.environ.get("WOW_FLAVOR", "_retail_") + "/Interface/AddOns/SpokenPlayers/Speakers.lua")
CLSID = "{055bf9e8-68b3-4cb2-8090-50895f4bcc68}"
SPECIAL = {"leaders": ("Leader Voices", "Male"), "murloc": ("Murlocs", "Male")}
RACES = {"bloodelf": "Blood Elf", "darkiron": "Dark Iron", "kultiran": "Kul Tiran",
         "nightelf": "Night Elf", "voidelf": "Void Elf"}

def display(folder):
    if folder in SPECIAL:
        return SPECIAL[folder]
    race, sex = folder.rsplit("_", 1)
    return f"{RACES.get(race, race.capitalize())} {sex.capitalize()}", sex.capitalize()

def tokens(root):
    out = []
    for folder in sorted(os.listdir(VOICES)):
        if not os.path.isfile(os.path.join(VOICES, folder, "model.onnx")):
            continue
        name, gender = display(folder)
        name = "Spoken Players " + name
        key = rf"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\{root}\Voices\Tokens\SpokenPlayers_{folder}"
        out.append(f'[{key}]\n@="{name}"\n"409"="{name}"\n"CLSID"="{CLSID}"\n'
                   f'"ModelDir"="C:\\\\Program Files\\\\Spoken Players\\\\voices\\\\{folder}"\n'
                   f'"DataDir"="C:\\\\Program Files\\\\Spoken Players\\\\espeak-ng-data"\n'
                   f'"SpeakerId"=dword:00000000\n"SpokenGroupVoice"=dword:00000001\n')
        out.append(f'[{key}\\Attributes]\n"Name"="{name}"\n"Gender"="{gender}"\n"Age"="Adult"\n'
                   f'"Language"="409"\n"Vendor"="Spoken Players"\n')
    return out, [o.split('"')[1] for o in out[::2]]

def write(path, blocks):
    text = "Windows Registry Editor Version 5.00\n\n" + "\n".join(blocks) + "\n"
    with open(path, "w", encoding="utf-16", newline="\r\n") as f:
        f.write(text)

here = os.path.dirname(os.path.abspath(__file__))
known = set(re.findall(r'\["(Spoken Players [^"]+)"\]', open(SPEAKERS, encoding="utf-8").read()))
engine = (f'[HKEY_LOCAL_MACHINE\\SOFTWARE\\Classes\\CLSID\\{CLSID}]\n@="Spoken Voice Engine"\n',
          f'[HKEY_LOCAL_MACHINE\\SOFTWARE\\Classes\\CLSID\\{CLSID}\\InprocServer32]\n'
          f'@="C:\\\\Program Files\\\\Spoken Players\\\\spoken_voice.dll"\n"ThreadingModel"="Both"\n')
classic, names = tokens("Speech")
onecore, _ = tokens("Speech_OneCore")
unknown = [n for n in names if n not in known]
if unknown:
    sys.exit(f"Names not in Speakers.lua (fix the mapping first): {unknown}")
write(os.path.join(here, "spoken_voices.reg"), list(engine) + classic)
write(os.path.join(here, "spoken_voices_onecore.reg"), onecore)
print(f"{len(names)} voices written; addon knows {len(known)}; not installed: {sorted(known - set(names))}")
