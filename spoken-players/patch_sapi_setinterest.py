#!/usr/bin/env python3
"""Make a copy of Proton's sapi.dll that WoW can speak through: ISpVoice::SetInterest returns S_OK
instead of E_NOTIMPL, and ISpVoice::Speak treats SAPI XML as plain text (Wine can't parse it).

WoW calls SetInterest before Speak and gives up when it fails, so under Proton no Windows TTS voice
plays (see the README).

Usage: python3 -I patch_sapi_setinterest.py <original sapi.dll> <output sapi.dll>

The output also has Wine's "builtin DLL" marker cleared, so Wine loads it as a native DLL (needs the
DllOverride sapi=native in the prefix, otherwise Wine ignores the file and uses its own builtin).
"""
import re, shutil, subprocess, sys

src, dst = sys.argv[1], sys.argv[2]

# Image base and .text placement, from objdump.
hdr = subprocess.run(["objdump", "-p", "-h", src], capture_output=True, text=True, check=True).stdout
base = int(re.search(r"^ImageBase\s+([0-9a-f]+)", hdr, re.M).group(1), 16)
m = re.search(r"\.text\s+([0-9a-f]+)\s+([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)", hdr)
text_size, text_vma, text_off = (int(x, 16) for x in m.groups())

# Find spvoice_SetInterest and every "mov $0x80004001,%eax" (b8 01 40 00 80) inside it.
dis = subprocess.run(["objdump", "-d", src], capture_output=True, text=True, check=True).stdout
body = re.search(r"^([0-9a-f]+) <spvoice_SetInterest>:\n(.*?)\n\n", dis, re.M | re.S)
if not body:
    sys.exit("spvoice_SetInterest not found (did this Proton change sapi.dll a lot?)")
hits = re.findall(r"^\s*([0-9a-f]+):\s+b8 01 40 00 80\s", body.group(2), re.M)
if not hits:
    sys.exit("no E_NOTIMPL return found in spvoice_SetInterest: maybe it is implemented now")

data = bytearray(open(src, "rb").read())
for va in hits:
    off = int(va, 16) - text_vma + text_off
    assert data[off:off + 5] == b"\xb8\x01\x40\x00\x80", hex(off)
    data[off:off + 5] = b"\xb8\x00\x00\x00\x00"  # mov $0 (S_OK),%eax
    print("patched return at", va, "file offset", hex(off))

# 2) ISpVoice::Speak: Wine can't parse SAPI XML ("SAPI XML parsing is not implemented"), and WoW
#    sends every line as SAPI XML (<bookmark mark='Start'/>text<bookmark mark='End'/>). Make Speak
#    always take its plain-text path (the one for SPF_IS_NOT_XML). The Spoken engine ignores the
#    bookmark tags in plain text. Proton's own voices may read them aloud.
speak = re.search(r"^([0-9a-f]+) <spvoice_Speak>:\n(.*?)\n\n", dis, re.M | re.S)
if not speak:
    sys.exit("spvoice_Speak not found")
xml_test = re.search(r"^\s*([0-9a-f]+):\s+40 f6 c6 08\s+test\s+\$0x8,%sil\n\s*[0-9a-f]+:\s+0f 84 (?:[0-9a-f]{2} ){4}\s*je\s",
                     speak.group(2), re.M)
plain = re.search(r"test\s+\$0x10,%sil\n\s*[0-9a-f]+:\s+0f 85 (?:[0-9a-f]{2} ){4}\s*jne\s+([0-9a-f]+)", speak.group(2))
if not (xml_test and plain):
    sys.exit("spvoice_Speak's XML/plain-text branches not found (Proton changed it?): not patching")
at, to = int(xml_test.group(1), 16), int(plain.group(1), 16)
off = at - text_vma + text_off
assert data[off:off + 6] == b"\x40\xf6\xc6\x08\x0f\x84", hex(off)
data[off:off + 10] = b"\xe9" + (to - (at + 5)).to_bytes(4, "little", signed=True) + b"\x90" * 5
print("Speak: XML test at %x now jumps to the plain-text path at %x" % (at, to))

# 3) The Spoken engine reads tags aloud ("bookmark mark start", "pitch middle"...), and the plain-text
#    path hands it WoW's text with every tag in it. The memcpy that copies the text into the fragment
#    becomes a call to strip_tags (patches/strip_tags.s, assembled below), which leaves out <...> and
#    sets r13 (the fragment's length) to the new length. It goes in the unused space at the end of .text.
STRIP = bytes.fromhex(
    "4889c84989c94531d2440fb7024883c2024585c07428"
    "4183f83c740f4585d275126645890149"
    "83c102ebde41ba01000000ebd64183f83e75d04531d2ebcb"
    "6641c70100004d89cd4929c549d1edc3")
copy = re.search(r"^\s*([0-9a-f]+):\s+48 8d 48 60\s+lea\s+0x60\(%rax\),%rcx\n"
                 r"\s*[0-9a-f]+:\s+4d 8d 47 a0\s+lea\s+-0x60\(%r15\),%r8\n"
                 r"\s*([0-9a-f]+):\s+e8 (?:[0-9a-f]{2} ){4}\s*call\s+[0-9a-f]+ <memcpy>",
                 speak.group(2), re.M)
if not copy or "mov    %r13d,0x58(%r12)" not in speak.group(2):
    sys.exit("spvoice_Speak's text copy not found (Proton changed it?): not patching")
pe = int.from_bytes(data[0x3c:0x40], "little")
sec = pe + 24 + int.from_bytes(data[pe + 20:pe + 22], "little")  # first section header = .text
assert data[sec:sec + 5] == b".text"
vsize = int.from_bytes(data[sec + 8:sec + 12], "little")
rsize = int.from_bytes(data[sec + 16:sec + 20], "little")
cave_rva = (int.from_bytes(data[sec + 12:sec + 16], "little") + vsize + 15) & ~15
cave_off = cave_rva - (text_vma - base) + text_off
assert cave_rva + len(STRIP) <= text_vma - base + rsize and not any(data[cave_off:cave_off + len(STRIP)])
data[cave_off:cave_off + len(STRIP)] = STRIP
data[sec + 8:sec + 12] = (cave_rva + len(STRIP) - (text_vma - base)).to_bytes(4, "little")  # VirtualSize
call_at = int(copy.group(2), 16)
off = call_at - text_vma + text_off
data[off:off + 5] = b"\xe8" + (base + cave_rva - (call_at + 5)).to_bytes(4, "little", signed=True)
print("Speak: text copy at %x now calls strip_tags at %x" % (call_at, base + cave_rva))

marker = b"Wine builtin DLL"
i = data.find(marker, 0, 0x200)
if i >= 0:
    data[i:i + len(marker)] = b"\0" * len(marker)
    print("cleared Wine builtin marker")

open(dst, "wb").write(data)
print("wrote", dst)
