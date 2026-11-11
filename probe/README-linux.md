# disc-probe 的 Linux 移植（SG_IO）

上游 disc-probe 的底层 SCSI pass-through 只在 Windows 上实现（SPTI）；macOS 已由
[NaiveTomcat/discprobe-macos](https://github.com/NaiveTomcat/discprobe-macos) 用 IOKit 移植。
本文件描述本仓库补充的 **Linux（SG_IO）** 后端。

## 改了什么

| 文件 | 改动 |
|---|---|
| `discprobe/sg.py` **新增** | Linux 后端：用 `SG_IO` ioctl（`0x2285`）发原始 CDB，等价于 Windows 的 SPTI |
| `discprobe/device.py` **新增** | 平台分发：Windows→`spti.py`，Linux→`sg.py`，统一导出 `Device` / `list_optical_drives` / `raise_priority`；不支持的平台在 import 时报错 |
| `discprobe/__main__.py` | 4 处 `from .spti import …` 改为 `from .device import …`；`--drive` 帮助与 `_open` 提示改为双平台 |
| `tools/geo_probe_points.py` | `spti`→`device`，`SptiDevice`→`Device` |
| `tools/cd_readcmd_compare.py` | 同上 |

其余全部未动：`mmc.py`、`scsi.py`、`timing.py`、`geo.py` 以及所有分析/生成代码照常工作。
两端共用同一个 `ScsiResult`（`status/data/sense/t_start_ns/t_end_ns`）契约。

## 原理

- **Windows**：`DeviceIoControl` + `IOCTL_SCSI_PASS_THROUGH_DIRECT`（SPTI）。
- **Linux**：`ioctl(SG_IO)`，用 `ctypes.CDLL(None)` 直接调 libc，**零第三方依赖**。请求头是
  `<scsi/sg.h>` 的 `struct sg_io_hdr` 按字段顺序/类型照搬成的 ctypes 结构。
- 计时方式与 Windows 完全一致：`time.perf_counter_ns()` 紧包住 ioctl 调用，Python 层不掺任何东西。
- 打开 `/dev/srN`（块设备）；若因挂载返回 `EBUSY`，自动回退到对应的 `/dev/sgN`（裸 sg 设备，
  少一层块层）。两者发同一套 CDB；`--drive` 也可直接传 `/dev/sg0`。
- 命令白名单复用 `scsi.check_allowed`：只放行只读命令 + `SET CD SPEED`，`DATA_OUT` 直接拒绝，
  与 Windows 行为一致；sense 复用 `scsi.parse_sense`。

## 用法

```bash
python -m discprobe list                      # 列出光驱（/dev/sr0 …）
python -m discprobe info   --drive /dev/sr0   # 只读，无需特权
python -m discprobe timing --drive /dev/sr0 --speed 5540
python -m discprobe geo    --drive /dev/sr0 --speed 5540
```

- `--drive` 接受 `/dev/sr0`、`/dev/sg0` 或 `sr0`/`sg0`。
- 权限：`/dev/sr*`、`/dev/sg*` 通常属于 `cdrom`/`disk` 组，或 root；多数桌面发行版已通过
  udev/ACL 授权登录用户。
- 计时建议用 `sudo` 跑：Linux 上 `raise_priority` 优先用 `SCHED_FIFO` 实时调度（最小优先级）+
  `sched_setaffinity` 绑单核，失败退回 `nice(-20)`；这些需要 `CAP_SYS_NICE`（root）。

## 实测与已知限制

已在两张盘、两台光驱上验证，`python -m discprobe selftest` 全绿：

| 光驱 | 接口 | 盘 | 结果 |
|---|---|---|---|
| PLDS DVD-RW DS8A8SH | USB 2.0 | RITEKF1 DVD-R | CAV + `fua`，相位与 Windows 一致；单次抖动 1.4–1.8°（同盘在 Windows 上 0.56–0.87°） |
| ASUS BW-16D1H-U | USB 3.0 | RITEKF1 DVD-R / BD-R | CAV + `fua`，但单次抖动 8–14°（Windows 上同样 ~8–14°，硬件噪声） |

**关键结论：**

1. **移植几何上是正确的**——同一张盘、同一光驱，Linux 与 Windows 测出的相位在噪声范围内一致
   （相差约 0.1–0.4°），只是噪声更高。
2. **USB 光驱在 Linux 上比 Windows 约噪 2 倍**（同一台 PLDS：Linux 1.4–1.8° vs Windows
   0.56–0.87° 单次）。已排除进程调度（`SCHED_FIFO`）和 `usb-storage` 内核线程调度（`chrt -f`
   后 zone 抖动 107–144µs → 98–109µs，只找回一点），根因是 Linux USB 存储栈完成路径更深
   （xHCI 软中断 → `usb-storage` 线程 → 块层），这是内核特性而非移植 bug。
3. 上面的 2 倍差距**只在 USB 外置光驱上体现**；SATA 内置光驱走 AHCI 直连、不经 `usb-storage`，
   这一层噪声应显著更小（本仓库未在 SATA 光驱上实测）。
4. 即便 2 倍，`geo` 仍完全可用：每级 sigma ~0.25–0.3°，与作者参考光驱（GH70N 单次 0.5°）同量级，
   只是比"同盘在 Windows 上"粗一点。纯计算步骤（`spokes`/`scan`/`image`/`disexport`）完全不受影响。

（补充：上游后来提交的 “geo accepts noisier drives” 放宽了相干性阈值，正是为了让上面那种 8–14° 的
噪声光驱也能跑 `geo`；本仓库已 fast-forward 到该上游版本，Linux 侧未对 `geo.py` 另作改动。）

## 给上游的建议

- 若集成：把这 5 个文件（2 新 + 3 改）合进去即可，接口契约与 SPTI 完全对齐，`spti.py` 无需动。
- 若只想用结果、不想维护 Linux 后端：建议把"测盘参数"这一环节在 Windows/macOS 上做，
  Linux 上跑纯计算步骤，也能得到同样的预设。
