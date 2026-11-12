# Jiritsu 持续会话与慢速原始备份

这是相机 Linux 内的临时执行后端，不修改开机启动流程。实测主机为 macOS。2026-11-12 的底层流程有 2.03 实机记录；此次整理后的集成新增部分仅经过离线测试。

| 系统 | 路线 | 实测范围 |
|---|---|---|
| 2.02 `30110_05.2025031501` | 原终端 / FileControl | 已有完整双遍备份，约 12 MiB/s |
| 2.03 `30110_06.2026060501` | Jiritsu | 同一 root shell 保留目录和变量；累计约 1.68 GB 分块读取并校验后由机主中止 |
| 2.02 | 可选 Jiritsu | 此后端尚未完成该版本实机验证 |

本机 2.03 的旧终端命令通道失败，启用终端前后 FileControl 都返回 `0x80`、0 字节。这是该设备/会话的结果，不能扩大成所有 2.03 都删除了该协议。

## 建立唯一连接

在 `linux/` 完成环境准备后：

```sh
./scripts/run_terminal.sh --backend jiritsu --firmware 2.03 --owner-authorized-exec
.venv/bin/python -B host/zve10_terminal_client.py
```

等待 `state.json` 为 `ready`。默认仍限制为只读命令；经机主授权的写操作还需给服务端加 `--owner-authorized-write`。命令在同一个 shell 执行，保留工作目录及变量，但不是完整 PTY，单条输出限 64 KiB。不要用结构化命令中的 `exit/exec/kill/trap/return` 结束或替换子 shell；客户端输入 `exit` 会关闭服务。

建立后端需要**临时向相机服务工作区上传自有的 440 字节载荷及脚本**，所以不能把整个流程称为“相机端零写入”。载荷在 `helpers/jiritsu-shell/` 有汇编源码和构建脚本，构建哈希与实测二进制一致。命令、结果及数据块放在唯一的、已验证为 tmpfs 的 `/tmp_network` 内存目录；不会安装开机自启 root。

## 慢速原始备份

另一终端复用同一会话：

```sh
.venv/bin/python -B host/zve10_terminal_client.py --timeout 3600 --request-json '{"action":"raw-backup","passes":1}'
# 可选 passes=2，执行独立双遍完整读取。
```

范围为 Linux 暴露的整个 `/dev/nflasha`（1,954,545,664 字节，含间隙及尾部），以及 B0/B1 启动区各 4 MiB；每个设备都核对实时容量。不含 RPMB、OTP/eFuse 或隐藏区域，不提供镜像恢复。

root 每次读取 512 KiB 到内存，通过 Jiritsu 回传，逐块核对相机与主机 SHA-256，保存后再从电脑磁盘独立重读校验。结果位于私密会话目录的 `raw-backup-*`。只有精确长度和保存文件验证通过后，`.part` 才改为正式文件；不把部分数据标成完整。

实测约 **1.3 MiB/s**，用户区单遍预计约 **25 分钟**，双遍约 **50 分钟**，另加元数据和主机校验。这是估算，不保证速度。2.03 实验在读取 1,681,915,904 字节后按机主要求中止；**完整用户区加启动区及独立双遍尚未实机验收**。Linux 在运行，可写分区两遍间可能变化，不能要求所有活动数据都相同。

取消时不要强杀进程：

```sh
.venv/bin/python -B host/zve10_terminal_client.py --cancel-backup
```

取消在完整数据块之间处理，保留 `.part` 和未完成/已取消清单，连接继续用于清理。SIGINT/SIGTERM 也请求在边界停止。新取消集成仅经离线测试，尚未再次实机验证。

## 结束和断电

客户端输入 `exit` 或提交 `close`。先删除并确认 `run.sh/libJit.so/out.txt` 不存在，再退出服务；等待 `state=closed`、`service_returned=true`、`loader_files_removed=true`。随后关机、拔 USB、取电池约 30 秒，结束剩余的内存进程。

实测先结束子 shell 再访问服务会导致 GET_FILE 超时；“先清理文件、关闭服务、再断电”的顺序成功。内部原因未确定，不能宣传任意子进程退出均可靠。发生超时可能留下临时文件，应保留状态并核查，不盲目覆盖旧载荷。
