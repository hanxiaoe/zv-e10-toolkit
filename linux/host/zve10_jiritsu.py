"""Jiritsu-backed persistent shell and bounded block reads (no boot persistence)."""
import hashlib
from pathlib import Path
import re
import struct
import time
import uuid

import zve10_common as common
from zve10_read_file_jiritsu import read_file

FIRMWARES = {'2.02': b'30110_05.2025031501', '2.03': b'30110_06.2026060501'}
REGIONS = {'/dev/nflasha': 1954545664, '/dev/nflashaB0': 4194304,
           '/dev/nflashaB1': 4194304, '/dev/nflasha5': 62914560}
PAYLOAD_SHA = 'c22deba2d43a6643c628a0dd5e7f524fa7b50dcc766fcee0eb37d667895c4b24'

class BackupCancelled(Exception):
    pass

def jcmd(camera, code, data=b''):
    response = camera._sendAdjustControlPacket(0x1001, code, data)
    if len(response) < 4 or struct.unpack_from('<I', response)[0]:
        raise RuntimeError('Jiritsu command failed: %d' % code)
    return response[4:]

def upload_verified(camera, path, data):
    """Small file upload, retaining firmware path normalization semantics."""
    if not path.startswith(('/tmp/jiritsu/', '/tmp_network/zve10-')) or '..' in path:
        raise ValueError('Unexpected temporary upload path')
    if not data or len(data) > 65536:
        raise ValueError('Only small helpers/commands may be uploaded')
    transport = '/tmp/jiritsu/../..' + path if path.startswith('/tmp_network/') else path
    jcmd(camera, 15, b'\0' + transport.encode('ascii') + b'\0')
    jcmd(camera, 16, b'\0\xff\0' + data)
    if read_file(camera, path, 65536) != data:
        raise RuntimeError('Upload readback mismatch; stop before execution')

class JiritsuBackend:
    def __init__(self, camera, session, firmware, cancelled=lambda: False):
        self.camera, self.session = camera, Path(session)
        self.expected = FIRMWARES[firmware]
        self.ram = '/tmp_network/zve10-' + uuid.uuid4().hex[:12]
        self.number = 0
        self.started = False
        self.cancellable = False
        self.cancelled = cancelled
        self.status = {'backend': 'jiritsu', 'requires_power_cycle': False}

    def start(self):
        versions = [read_file(self.camera, '/version.txt', 64) for _ in range(2)]
        if versions != [self.expected, self.expected]:
            raise RuntimeError('Two exact firmware-version reads required')
        self.status['system_version'] = self.expected.decode()
        for path in ('/tmp/jiritsu/run.sh', '/tmp/jiritsu/libJit.so', '/tmp/jiritsu/out.txt'):
            try:
                read_file(self.camera, path, 65536)
            except RuntimeError as exc:
                if '0x10000006' not in str(exc):
                    raise
            else:
                raise RuntimeError('Existing loader workspace: inspect it before starting; no overwrite')
        payload = (common.ROOT / 'helpers/jiritsu-shell/launch.so').read_bytes()
        if len(payload) != 440 or hashlib.sha256(payload).hexdigest() != PAYLOAD_SHA:
            raise RuntimeError('Unknown root loader; rebuild/check its source')
        r = self.ram
        script = f'''#!/bin/sh
grep ' /tmp_network tmpfs ' /proc/mounts >/dev/null || exit 31
mkdir '{r}' || exit 32
exec >'{r}/daemon.log' 2>&1
cat /proc/$$/status >'{r}/ready'
echo $$ >'{r}/pid'
while :; do
 if [ -f '{r}/input' ] && [ -f '{r}/go' ]; then
  mv '{r}/input' '{r}/current' || exit 33
  . '{r}/current' >'{r}/output.tmp' 2>&1
  zv_rc=$?
  printf '\\n__ZV_RC__:%s\\n' "$zv_rc" >>'{r}/output.tmp'
  mv '{r}/output.tmp' '{r}/output'
  rm '{r}/current'
 else
  sleep "${{ZV_POLL:-1}}"
 fi
done
'''.encode()
        (self.session / 'root-daemon.sh').write_bytes(script)
        common.restore_owner(self.session / 'root-daemon.sh')
        self.status['requires_power_cycle'] = True
        upload_verified(self.camera, '/tmp/jiritsu/run.sh', script)
        self.status['loader_upload_attempted'] = True
        # A failed response can still mean the constructor ran: never retry blindly.
        upload_verified(self.camera, '/tmp/jiritsu/libJit.so', payload)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                ready = read_file(self.camera, r + '/ready', 16384)
                if re.search(rb'^Uid:\s+0\s+0\s+0\s+0\s*$', ready, re.M):
                    break
                raise ValueError('Loaded process is not root')
            except RuntimeError as exc:
                if '0x10000006' not in str(exc):
                    raise
                time.sleep(.25)
        else:
            raise RuntimeError('No root-ready marker; do not re-upload')
        self.started = True
        self.status.update(root_uid=0, ram_workspace=r, requires_power_cycle=True)
        self.camera._session_read = self.read_path
        self.camera.dev._session_command = self.command
        self.camera._jiritsu_backend = self

    def command(self, label, command, timeout=60):
        if not self.started or not isinstance(command, str) or not command.isascii() or len(command) > 8192:
            raise ValueError('Invalid root command or inactive session')
        if re.search(r'\b(exit|exec|kill|trap|return)\b', command):
            raise ValueError('Do not terminate/replace the persistent shell; close service and power-cycle')
        self.number += 1
        marker = '__ZV_CMD_%d__' % self.number
        if self.number > 1:
            # Root removes the marker after output is safely read by the host.
            jcmd(self.camera, 15, b'\0' + ('/tmp/jiritsu/../..'+self.ram+'/go').encode() + b'\0')
            jcmd(self.camera, 18, b'\0\xff')
        upload_verified(self.camera, self.ram+'/input',
                        ("printf '%s\\n'\n" % marker + command + '\n').encode())
        upload_verified(self.camera, self.ram+'/go', b'go\n')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data = read_file(self.camera, self.ram+'/output', 65536)
                if data.startswith((marker+'\n').encode()):
                    end = re.search(rb'\n__ZV_RC__:(\d+)\n$', data)
                    if end:
                        return {'name': label, 'command': command, 'exit_code': int(end[1]),
                                'output': data[len(marker)+1:end.start()].decode('utf8', 'replace')}
            except RuntimeError as exc:
                if '0x10000006' not in str(exc):
                    raise
            time.sleep(.02)
        raise TimeoutError('Root command timed out; no automatic retry')

    def run(self, command):
        result = self.command('transport', command)
        if result['exit_code']:
            raise RuntimeError('Camera command failed: ' + str(result))
        return result['output']

    def read_path(self, path, sink=None):
        if not path.startswith('/dev/'):
            data = read_file(self.camera, path, 32*1048576)
            if sink is not None:
                sink.write(data)
                return 0, None
            return 0, data
        if path not in REGIONS:
            raise ValueError('Block reads restricted to known user/boot/WBI regions')
        name, size = path.split('/')[-1], REGIONS[path]
        if sink is None and size > 64*1048576:
            raise ValueError('Large block reads require a streaming sink')
        live = self.run('cat /sys/class/block/%s/size' % name).strip()
        if not live.isdecimal() or int(live)*512 != size:
            raise ValueError('Runtime block capacity mismatch')
        buffer = bytearray() if sink is None else None
        self.run('sleep 0.01 && ZV_POLL=0.01')
        try:
            for offset in range(0, size, 524288):
                if self.cancellable and self.cancelled():
                    raise BackupCancelled('Cancelled at completed block boundary')
                count = min(524288, size-offset)
                text = self.run('busybox dd if=%s of=%s/chunk bs=4096 skip=%d count=%d 2>/dev/null && busybox sha256sum %s/chunk' %
                                (path, self.ram, offset//4096, count//4096, self.ram))
                data = read_file(self.camera, self.ram+'/chunk', 524288)
                if len(data) != count or not re.fullmatch(r'[0-9a-f]{64}\s+\S+\s*', text) or hashlib.sha256(data).hexdigest() != text.split()[0]:
                    raise RuntimeError('Chunk length/camera-host hash mismatch')
                if sink is not None:
                    sink.write(data)
                else:
                    buffer.extend(data)
        finally:
            self.run('rm -f '+self.ram+'/chunk; ZV_POLL=1')
        return 0, bytes(buffer) if buffer is not None else None

    def close(self):
        if self.started:
            # Tested handoff: stop the service while the child still exists.
            # Exiting the child first reproducibly made GET_FILE time out.
            self.run('cd /; rm -f /tmp/jiritsu/run.sh /tmp/jiritsu/libJit.so /tmp/jiritsu/out.txt')
            for path in ('/tmp/jiritsu/run.sh', '/tmp/jiritsu/libJit.so', '/tmp/jiritsu/out.txt'):
                try:
                    read_file(self.camera, path, 65536)
                except RuntimeError as exc:
                    if '0x10000006' not in str(exc):
                        raise
                else:
                    raise RuntimeError('Temporary file cleanup not confirmed')
            self.status['loader_files_removed'] = True
            self.started = False
        for obj, key in ((self.camera, '_session_read'), (self.camera.dev, '_session_command')):
            if hasattr(obj, key):
                delattr(obj, key)
