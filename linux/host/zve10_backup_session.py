"""Slow raw backup action on the existing Jiritsu connection; no second USB open."""
import time
from pathlib import Path

import zve10_backup_raw as raw
import zve10_common as common
from zve10_jiritsu import BackupCancelled

def dispatch(camera, request, session, write_mode):
    backend = getattr(camera, '_jiritsu_backend', None)
    if backend is None:
        raise ValueError('Use the Jiritsu backend; the original fast backup CLI remains available on 2.02')
    passes = request.get('passes', 1)
    if type(passes) is not int or passes not in (1, 2):
        raise ValueError('passes must be 1 or 2')
    folder = Path(session) / time.strftime('raw-backup-%Y%m%d-%H%M%S')
    folder.mkdir(mode=0o700)
    common.restore_owner(folder)
    raw.OUT = folder
    raw.RESULT = {'scope': 'Linux user area plus B0/B1; Jiritsu tmpfs chunks; not RPMB/OTP',
                  'passes': passes, 'backend': 'jiritsu', 'system_version': backend.expected.decode(),
                  'temporary_camera_workspace_writes': True, 'reads': [], 'completed': False}
    marker = Path(session) / 'cancel-backup'
    # A pre-existing cancellation is honored; it is never silently discarded.
    backend.cancellable = True
    try:
        raw.RESULT['partitions'] = backend.run('cat /proc/partitions')
        raw.RESULT['mounts'] = backend.run('cat /proc/mounts')
        raw.RESULT['layout'] = backend.run('for p in /sys/class/block/nflasha*; do echo DEVICE:$p; for f in dev size start ro; do echo FIELD:$f; cat "$p/$f" 2>/dev/null; done; done')
        raw.save()
        for name in raw.REGIONS:
            rows = [raw.receive(camera, name, i) for i in range(1, passes+1)]
            if passes == 2:
                a, b = rows
                raw.RESULT.setdefault('comparisons', {})[name] = {
                    'identical': a['sha256'] == b['sha256'],
                    'differing_1MiB_chunks': [i for i,(x,y) in enumerate(zip(a['chunk_sha256_1MiB'],b['chunk_sha256_1MiB'])) if x != y]}
                if name != 'nflasha' and a['sha256'] != b['sha256']:
                    raise RuntimeError('Boot-area double read mismatch')
        raw.RESULT['completed'] = True
        (folder/'SHA256SUMS').write_text(''.join('%s  %s\n' % (r['sha256'], r['file']) for r in raw.RESULT['reads']))
    except BackupCancelled:
        raw.RESULT['cancelled'] = True
        raw.RESULT['reason'] = 'Owner cancelled at a completed data-block boundary'
    finally:
        backend.cancellable = False
        for row in raw.RESULT['reads']:
            if not row['complete']:
                row['partial_file'] = row['file'] + '.part'
        raw.save()
        common.restore_tree_owner(folder)
        if marker.is_file() and not marker.is_symlink():
            marker.unlink()
    return {'backup_dir': str(folder), 'completed': raw.RESULT['completed'],
            'cancelled': raw.RESULT.get('cancelled', False), 'passes': passes}
