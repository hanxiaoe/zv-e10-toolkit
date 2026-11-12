"""Build our sectionless ARM ELF using clang; never executes ARM code."""
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as temp:
    obj = Path(temp) / 'launch.o'
    subprocess.run(['clang', '-target', 'armv7-none-eabi', '-c',
                    str(HERE / 'launch.S'), '-o', str(obj)], check=True)
    data = obj.read_bytes()
    shoff = struct.unpack_from('<I', data, 32)[0]
    entsize, count, names = struct.unpack_from('<HHH', data, 46)
    sections = [struct.unpack_from('<10I', data, shoff+i*entsize) for i in range(count)]
    strings = sections[names]
    strings = data[strings[4]:strings[4]+strings[5]]
    text = next(s for s in sections if strings[s[0]:].split(b'\0')[0] == b'.text')
    code = data[text[4]:text[4]+text[5]]
ident = b'\x7fELF\x01\x01\x01' + bytes(9)
header = struct.pack('<16sHHIIIIIHHHHHH', ident, 3, 40, 1, 0, 52, 0,
                     0x5000200, 52, 32, 3, 40, 0, 0)
code_end = 184 + len(code)
segments = b''.join(struct.pack('<8I', *s) for s in (
    (1, 0, 0, 0, code_end, code_end, 5, 4096),
    (1, code_end, code_end+4096, code_end+4096, 56, 56, 6, 4096),
    (2, code_end, code_end+4096, code_end+4096, 56, 56, 6, 4)))
tables = struct.pack('<4I', 1, 1, 0, 0) + bytes(20)
dynamic = b''.join(struct.pack('<II', *p) for p in (
    (12, 185), (4, 148), (5, 180), (6, 164), (10, 1), (11, 16), (0, 0)))
payload = header + segments + tables + code + dynamic
expected = 'c22deba2d43a6643c628a0dd5e7f524fa7b50dcc766fcee0eb37d667895c4b24'
if hashlib.sha256(payload).hexdigest() != expected:
    raise SystemExit('Build differs from camera-tested payload; no output written')
(HERE / 'launch.so').write_bytes(payload)
print(len(payload), hashlib.sha256(payload).hexdigest())
