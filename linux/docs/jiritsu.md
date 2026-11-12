# Jiritsu shell and slow raw backup

**Complete single-pass hardware result:** A dedicated 8 MiB tmpfs and 4 MiB chunks read the entire user area plus B0/B1: 1,962,934,272 bytes. Camera/host chunk hashes and complete saved-file host rereads matched. The backup action took 940.956 seconds, averaging 1.989 MiB/s, including preflight, metadata, saved-file verification and RAM mount cleanup; USB-session setup/admin waiting are excluded. No disconnect occurred during the read; mount/helper cleanup and service close succeeded. This is one live-system pass, not double-pass or restore validation. Use `chunk_kib=4096` for an automatically managed dedicated RAM buffer; omission keeps the 512 KiB default.


This is a temporary execution backend on the camera's Linux system, not a boot modification. The demonstrated host is macOS. The packaged backend and backup action were exercised on hardware through a research wrapper through a research wrapper; the public large-buffer lifecycle is now integrated and separately failure-tested offline. Read the [agent workflow](agent-workflow.md) before connecting.

| System | Backend | Evidence |
|---|---|---|
| 2.02 `30110_05.2025031501` | existing terminal / FileControl | Full double raw backup previously tested, about 12 MiB/s |
| 2.03 `30110_06.2026060501` | Jiritsu | Persistent shell; complete user+B0/B1 single pass with 4 MiB chunks, 940.956 seconds / 1.989 MiB/s |
| 2.02 | optional Jiritsu | Not yet camera-tested as this backend |

The old terminal command path failed on the tested 2.03 device. FileControl returned `0x80` with zero data even after terminal enable. This is a result on that device/session, not proof of a universal firmware protocol removal.

## Start one connection

From `linux/`, after setup:

```sh
./scripts/run_terminal.sh --backend jiritsu --firmware 2.03 --owner-authorized-exec --idle-timeout 3600
.venv/bin/python -B host/zve10_terminal_client.py
```

Wait for `state.json` to say `ready`. Default command restrictions still apply. Add `--owner-authorized-write` to the server only for owner-approved write operations. Commands use one persistent shell; this is not a PTY. Replies are limited to 64 KiB. Do not terminate or replace the shell with `exit`, `exec`, `kill`, `trap` or `return`; the client's `exit` closes the service instead.

Starting this backend **temporarily writes our 440-byte loader and script to the camera service workspace**. The loader has assembly source and a reproducible build in `helpers/jiritsu-shell/`; its hash matches the camera-tested binary. Commands/results/chunks live in a unique verified `/tmp_network` tmpfs directory. There is no boot-time installation. This is not a zero-camera-write backup method.

## Slow raw backup

In a second terminal on the same session:

```sh
.venv/bin/python -B host/zve10_terminal_client.py --timeout 3600 --request-json '{"action":"raw-backup","passes":1}'
# Faster: dedicated 8 MiB RAM buffer, 4 MiB chunks.
.venv/bin/python -B host/zve10_terminal_client.py --timeout 3600 --request-json '{"action":"raw-backup","passes":1,"chunk_kib":4096}'
# Optional: passes=2 for two independent full reads; use client --timeout 7200.
```

Scope: entire Linux-visible `/dev/nflasha` (1,954,545,664 bytes, including gaps/tail) and `/dev/nflashaB0`, `/dev/nflashaB1` (4 MiB each). Each live capacity is checked. No RPMB, OTP/eFuse or hidden chip areas. This does not implement image restoration.

The default is 512 KiB chunks. With `chunk_kib=4096`, host disk and camera memory are checked, a dedicated 8 MiB tmpfs is mounted, and it is unmounted/removed on success or cancellation. Jiritsu transfers each chunk; camera and host SHA-256 must match. Saved files are independently reread on the host. Output and metadata stay under the private session's `raw-backup-*` directory. `.part` is renamed only after exact length and saved-file verification; incomplete output is never marked complete.

Measured about **1.3 MiB/s**: allow roughly **25 minutes for one user-area pass, 50 minutes for two**, plus metadata and host checks. These are estimates, not speed guarantees. An earlier 512 KiB experiment was stopped at 1,681,915,904 bytes. The subsequent dedicated-buffer run completed all regions; **an independent 2.03 double pass remains unvalidated**. Writable partitions can change while Linux runs; two passes need not be identical.

Cancel without killing the process:

```sh
.venv/bin/python -B host/zve10_terminal_client.py --cancel-backup
```

Cancellation is checked between completed blocks, preserves `.part` and a cancelled/incomplete manifest, and keeps USB available for cleanup. SIGINT/SIGTERM request the same boundary-safe stop. Short-read cancellation was hardware-tested: incomplete metadata and 8,912,896 bytes were retained, host reread matched, and the connection remained usable.

## Close and remove power

Use the client `exit` or a structured `close`. The backend removes and verifies removal of `run.sh`, `libJit.so` and `out.txt` **before** ending the service. Wait for `state: closed`, `service_returned: true`, `loader_files_removed: true`. Then switch off, unplug USB and remove the battery for about 30 seconds. The remaining RAM process ends with power removal.

Stopping the child shell before its service connection repeatedly caused GET_FILE timeouts on the tested camera. The cleanup-first/service-close/power-removal handoff succeeded. Its internal cause is not established; this release does not claim arbitrary child-process termination is reliable. A timeout may leave temporary files: preserve state and inspect, never blindly re-upload over existing loader files.

## Additional hardware validation: dedicated RAM buffer

The same root PID was reused with a separate 8 MiB tmpfs. The same 4 MiB boot area was read in ascending/descending chunk order; all chunk and whole-image hashes matched. Data-loop rates: 512 KiB 1.24–1.29 MiB/s; 1 MiB 1.57–1.60; 2 MiB 1.75–1.85; 4 MiB 1.95–2.01. These exclude capacity/directory preflight. Total per 4 MiB read was 5.30–5.39 seconds at 512 KiB and 6.36–6.41 at 4 MiB. That short comparison did not establish full-backup throughput; the subsequent complete single-pass result is given at the start of this page.

The separate tmpfs was unmounted and its mountpoint removed; the original 1 MiB `/tmp_network` limit was unchanged. The public CLI defaults to 512 KiB; `chunk_kib=4096` selects the dedicated buffer. Its lifecycle was extracted from the hardware-tested research procedure and failure-tested offline. This camera lacks id/df applets: identity is verified by shell reads of /proc, and larger chunks require dedicated mount/capacity/directory checks.

The default raw-backup action was hardware-tested with a short read and cancellation: 8,912,896 bytes retained, independent host hash matched, incomplete status preserved, and the connection remained usable. Cleanup and service close succeeded. This supplements the earlier offline cancellation checks, not full-image validation.
