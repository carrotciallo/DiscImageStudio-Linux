# Disc Image Studio for Linux

简体中文 | [English](README.en.md)

DiscImageStudio 的 Linux 移植：在 CD / DVD / 蓝光光盘的盘面上刻蚀出肉眼可见的图像（DiscT@2 式盘面绘图）。

基于上游 [JiaFeiMiao-K-Cat/DiscImageStudio](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio)（GPL-3.0）移植：核心算法跨平台化（图像解码改用 StbImageSharp，PNG 编码改用自带实现，引擎去除 WPF 依赖），并补上 Linux 的命令行宿主、刻录通道与 Avalonia 图形界面。Windows 的 WPF 界面不在本仓库范围内。

> **暂时未验证**：刻录与图形界面尚未经真实光驱实刻检验；验证完成后会更新此说明，并补上实机截图。

## 组成

- **跨平台核心**：Core 与 CD / DVD / 蓝光三个引擎，与上游同一套求解与编码算法，目标框架 .NET 10。
- **命令行**（`src/DiscImageStudio.Cli`）：生成、预览、刻录全流程。
- **图形界面**（`src/DiscImageStudio.App.Avalonia`）：生成 / 预览 / 刻录三页之外，另有简版设计页：单图层按毫米摆位（拖动移位、滚轮或滑杆缩放、旋转），盘面参考圈标示数据环范围，导出 4096×4096 合成图后直接送去生成；与命令行共用同一套命令目录与刻录实现。上游 WPF 的多图层 .discproj 工程与标定会话工作区未移植。
- **刻录**：外挂 `xorriso`（ISO 写入与介质擦除）与 `cdrdao`（CUE 音轨写入），不重造 MMC 协议层。

## 环境要求

- Linux（在 Arch 系发行版上开发与自测）
- .NET 10 SDK
- 刻录时另需命令行工具 `xorriso`、`cdrdao` 在 PATH 中

## 构建

```bash
dotnet build DiscImageStudio.slnx
```

## 命令行用法

```bash
dotnet run --project src/DiscImageStudio.Cli -- <命令> [参数]
```

命令一览（完整说明见 `--help`）：

| 模块 | 命令 |
| --- | --- |
| CD | `cd-generate`、`cd-preview-warp`、`cd-preview-track` |
| DVD | `solve`、`encode`、`calibrate`、`simulate`、`selftest` |
| 蓝光 | `bd-info`、`bd-probe`、`bd-encode`、`bd-generate` |
| 刻录 | `burn-devices`、`burn` |
| 辐条标定 | `calibrate-spoke`、`calibrate-fit`、`calibrate-selftest` |

示例：

```bash
# DVD：由图片求解生成 ISO
... -- solve --image art.png --iso-output out.iso --total-sectors 2297888

# DVD：把已生成的 ISO 渲染成盘面预览图
... -- simulate --iso out.iso --output preview.png --inner-radius-mm 24 --outer-radius-mm 58

# CD：生成 WAV+CUE
... -- cd-generate --input art.png --output track.wav

# 蓝光：生成 ISO（扇区数须为 32 的倍数）
... -- bd-generate --input art.png --output out.iso --total-sectors 32000
```

（示例中的 `...` 指代 `dotnet run --project src/DiscImageStudio.Cli`。）

## 图形界面

```bash
dotnet run --project src/DiscImageStudio.App.Avalonia
```

截图：待实机验证后补上。

## 刻录与安全设计

```bash
# 列出光驱与刻录工具
... -- burn-devices

# 刻录 ISO（先不带 --yes，只探测介质并打印计划）
... -- burn --device /dev/sr0 --image out.iso
# 确认后实刻，并刻后读回校验 SHA-256
... -- burn --device /dev/sr0 --image out.iso --verify --yes

# 辐条标定：生成标定图（辐条＋定标半径环），按标称几何刻出后量各环处辐条的转角偏差
... -- calibrate-spoke --output spoke.png
# 把量到的相位误差拟合成真实螺旋几何（轨距/总圈数）
... -- calibrate-fit --samples "25:-11.1,30:-51.8,35:-49.6,40:-20.7,45:24.0,50:87.9,55:158.2"
```

- 不带 `--yes` 时只探测介质、打印将要执行的命令，不写盘。
- 介质非空且未指定 `--blank` 时拒绝执行；介质状态探测不明时同样拒绝。
- `--verify`（仅 ISO）在刻录后按镜像长度读回设备并比对 SHA-256。
- 可擦写介质（RW）重画图像需要整盘擦除；一次写入介质上的图像不可更改。

## 验证状态

- 引擎自检 `selftest` 全过（含 PNG 编解码往返的逐像素断言）。
- 生成链路实测：DVD `solve` 两跑输出 SHA-256 一致；`simulate`、`cd-generate`、`bd-generate` 均有真实产物。
- 刻录的参数拼装与双闸门已用桩工具覆盖五种路径；**真实光驱实刻待验证**（见文首说明）。

## 许可证与上游

GPL-3.0-or-later，与上游一致。本仓库是独立维护的 Linux 移植；使用问题请先在本仓库提出，算法层面的问题可参照上游仓库。
