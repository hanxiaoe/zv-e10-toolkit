# Jiritsu shell and slow raw backup

This is a temporary execution backend on the camera's Linux system, not a boot modification. The demonstrated host is macOS. The packaged refactor has offline tests; its underlying 2.03 procedure was camera-tested on 2026-11-12.

| System | Backend | Evidence |
|---|---|---|
| 2.02 `30110_05.2025031501` | existing terminal / FileControl | Full double raw backup previously tested, about 12 MiB/s |
| 2.03 `30110_06.2026060501` | Jiritsu | Persistent shell, working directory/variables retained; about 1.68 GB received with camera/host hashes before owner cancellation |
| 2.02 | optional Jiritsu | Not yet camera-tested as this backend |

The old terminal command path failed on the tested 2.03 device. FileControl returned `0x80` with zero data even after terminal enable. This is a result on that device/session, not proof of a universal firmware protocol removal.

## Start one connection

From `linux/`, after setup:

```sh
./scripts/run_terminal.sh --backend jiritsu --firmware 2.03 --owner-authorized-exec
.venv/bin/python -B host/zve10_terminal_client.py
```

Wait for `state.json` to say `ready`. Default command restrictions still apply. Add `--owner-authorized-write` to the server only for owner-approved write operations. Commands use one persistent shell; this is not a PTY. Replies are limited to 64 KiB. Do not terminate or replace the shell with `exit`, `exec`, `kill`, `trap` or `return`; the client's `exit` closes the service instead.

Starting this backend **temporarily writes our 440-byte loader and script to the camera service workspace**. The loader has assembly source and a reproducible build in `helpers/jiritsu-shell/`; its hash matches the camera-tested binary. Commands/results/chunks live in a unique verified `/tmp_network` tmpfs directory. There is no boot-time installation. This is not a zero-camera-write backup method.

## Slow raw backup

In a second terminal on the same session:

```sh
.venv/bin/python -B host/zve10_terminal_client.py --timeout 3600 --request-json '{"action":"raw-backup","passes":1}'
# Optional: passes=2 for two independent full reads.
```

Scope: entire Linux-visible `/dev/nflasha` (1,954,545,664 bytes, including gaps/tail) and `/dev/nflashaB0`, `/dev/nflashaB1` (4 MiB each). Each live capacity is checked. No RPMB, OTP/eFuse or hidden chip areas. This does not implement image restoration.

The root shell reads 512 KiB chunks into tmpfs. Jiritsu transfers each chunk; camera and host SHA-256 must match. Saved files are independently reread on the host. Output and metadata stay under the private session's `raw-backup-*` directory. `.part` is renamed only after exact length and saved-file verification; incomplete output is never marked complete.

Measured about **1.3 MiB/s**: allow roughly **25 minutes for one user-area pass, 50 minutes for two**, plus metadata and host checks. These are estimates, not speed guarantees. The 2.03 experiment was stopped at 1,681,915,904 bytes; **a complete 2.03 user+boot backup and double pass have not been hardware-validated**. Writable partitions can change while Linux runs; two passes need not be identical.

Cancel without killing the process:

```sh
.venv/bin/python -B host/zve10_terminal_client.py --cancel-backup
```

Cancellation is checked between completed blocks, preserves `.part` and a cancelled/incomplete manifest, and keeps USB available for cleanup. SIGINT/SIGTERM request the same boundary-safe stop. The new cancellation integration is offline-tested, not yet repeated on hardware.

## Close and remove power

Use the client `exit` or a structured `close`. The backend removes and verifies removal of `run.sh`, `libJit.so` and `out.txt` **before** ending the service. Wait for `state: closed`, `service_returned: true`, `loader_files_removed: true`. Then switch off, unplug USB and remove the battery for about 30 seconds. The remaining RAM process ends with power removal.

Stopping the child shell before its service connection repeatedly caused GET_FILE timeouts on the tested camera. The cleanup-first/service-close/power-removal handoff succeeded. Its internal cause is not established; this release does not claim arbitrary child-process termination is reliable. A timeout may leave temporary files: preserve state and inspect, never blindly re-upload over existing loader files.
