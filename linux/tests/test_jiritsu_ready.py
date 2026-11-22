"""Offline regressions for an absent, partial, or non-root startup marker."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'host'))
import zve10_jiritsu as jit

ROOT = b'Name:\tsh\nUid:\t0\t0\t0\t0\nGid:\t0\t0\t0\t0\n'


class ReadyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backend = jit.JiritsuBackend(Mock(), self.temp.name, '2.03')
        self.now = 0

    def sleep(self, seconds):
        self.now += seconds

    def wait(self, responses, timeout=1):
        with patch.object(jit, 'read_file', side_effect=responses) as read, \
             patch.object(jit.time, 'monotonic', side_effect=lambda: self.now), \
             patch.object(jit.time, 'sleep', side_effect=self.sleep), \
             patch.object(jit.common, 'restore_owner'), \
             patch.object(jit, 'upload_verified') as upload:
            try:
                self.backend._wait_root_ready(timeout)
            finally:
                upload.assert_not_called()
                self.reads = read.call_count

    def saved(self):
        return (Path(self.temp.name) / 'root-ready-last.txt').read_bytes()

    def test_missing_empty_partial_then_root(self):
        self.wait([RuntimeError('GET_FILE status 0x10000006'), b'',
                   b'Name:\tsh\nUid:\t0\t0', ROOT])
        self.assertEqual(self.reads, 4)
        self.assertEqual(self.saved(), ROOT)
        self.assertEqual(self.backend.status['root_ready_state'], 'root-confirmed')
        # Polling alone must not mark the backend active or attach command hooks.
        self.assertFalse(self.backend.started)

    def test_complete_nonroot_stops_immediately(self):
        with self.assertRaisesRegex(ValueError, 'not root'):
            self.wait([b'Uid:\t0\t1000\t0\t0\n', ROOT])
        self.assertEqual(self.reads, 1)
        self.assertEqual(self.backend.status['root_ready_state'], 'non-root')
        self.assertIn(b'1000', self.saved())

    def test_persistent_partial_times_out_with_evidence(self):
        partial = b'Name:\tsh\nUid:\t0\t0'
        with self.assertRaisesRegex(RuntimeError, 'timeout; do not re-upload'):
            self.wait([partial, partial], timeout=.5)
        self.assertEqual(self.reads, 2)
        self.assertEqual(self.saved(), partial)
        self.assertFalse(self.backend.started)

    def test_missing_marker_times_out_without_fabricated_identity(self):
        missing = RuntimeError('GET_FILE status 0x10000006')
        with self.assertRaisesRegex(RuntimeError, 'No complete root-ready'):
            self.wait([missing, missing], timeout=.5)
        self.assertEqual(self.backend.status['root_ready_state'], 'timeout')
        self.assertFalse((Path(self.temp.name) / 'root-ready-last.txt').exists())

    def test_other_read_error_is_not_retried(self):
        partial = b'Name:\tsh\n'
        with self.assertRaisesRegex(RuntimeError, '0x1000000a'):
            self.wait([partial, RuntimeError('GET_FILE status 0x1000000a'), ROOT])
        self.assertEqual(self.reads, 2)
        self.assertEqual(self.backend.status['root_ready_state'], 'read-error')
        self.assertEqual(self.saved(), partial)

    def test_usb_error_is_not_retried(self):
        with self.assertRaisesRegex(OSError, 'USB disconnected'):
            self.wait([OSError('USB disconnected'), ROOT])
        self.assertEqual(self.reads, 1)
        self.assertFalse(self.backend.started)
        self.assertEqual(self.backend.status['root_ready_state'], 'read-error')

    def test_multiline_digits_do_not_make_a_uid_record(self):
        with self.assertRaisesRegex(RuntimeError, 'No complete root-ready'):
            self.wait([b'Uid:\t0\n0\n0\n0\n'], timeout=.25)
        self.assertNotIn('root_uid', self.backend.status)


if __name__ == '__main__':
    unittest.main()
