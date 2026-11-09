# Disc Image Studio — Linux 图形前端（gui-port）

DiscImageStudio 官方 GUI 的 Linux 移植：功能对齐官方 WPF 版的操作面，
后端全部走官方 CLI（`disc-image-studio` v1.5.0），投影数学一行不在本
工程重写。只留本地使用，本地 git 管理，无远程仓库。

## 架构

- 壳：MyGo（github.com/egoist/mygo v0.8.3）原生绘制，暗色卡片式界面
- 后端：子进程调官方 CLI 的 `solve` / `simulate` / `selftest`，
  刻录走 `xorriso -as cdrecord -dao`（与定版刻录流程同一命令面），
  探盘走 `dvd+rw-mediainfo`，弹盘走 `eject`；校准子进程调
  disc-probe（`python3 -m discprobe`，目录见设置）
- 成像：图层合成与定版画布预处理在 Go 侧实现（x/image）；
  预处理为 PIL 管线（YCbCr 的 Y 通道 autocontrast cutoff=1 +
  UnsharpMask r6/80%/2）的复刻，与当晚定版产物的像素平均绝对差
  约 0.24（视觉等价、非字节级一致，残差来自 PIL 高斯模糊内部量化）

## 页面

- 首页：后端路径、几何预设、产物一览
- 设计：多图层（添加/删除/排序）、X/Y(mm)/高度/旋转滑杆+数字输入、
  居中/适合宽度/铺满高度、盘面画布实时预览、定版预处理开关
- 读回预览：对生成的 ISO 跑官方 simulate 并显示读回图
- 导出：几何预设与全部 solve 参数可编辑，生成 ISO 带进度与日志
- 刻录：探盘状态、速度选择（默认定版 8×）、刻前确认、弹盘
- 校准：驱动 disc-probe 做 timing（转速/CAV 判定）与 geo（几何拟合，
  带精度判定），disexport 把拟合导成求解预设存入设置，导出页可直接
  选用；打开页面自动载入 disc-probe 最近一次结果
- 设置：CLI 路径、工作目录、设备、速度、自检、disc-probe 目录、保存

设置存 `~/.config/dis-gui/settings.json`；产物默认落在
`~/muse/discimagestudio/work/`（canvas.png / disc.iso / simulate.png）。

## 构建与运行

```sh
./run.sh          # 构建并启动
go test ./...     # 单元与对齐测试（夹具对照需 DIS_FIXTURE_DIR）
```

依赖：Go ≥ 1.24、官方 CLI 二进制、xorriso、dvd+rw-tools、eject。

环境钩子：`DISGUI_OPEN=<图片路径>` 启动即载入该图为图层并落在设计页。

## 与官方 GUI 的差距（已知）

- 画布不支持鼠标拖拽定位，图层位置由滑杆/数字输入控制
  （官方 WPF 版同样以数值输入为主）。
- 仅覆盖 DVD 线（solve/simulate + xorriso 刻录 + disc-probe 校准）；
  官方 GUI 的 CD/Blu-ray 档位未复刻。标定页走 disc-probe
  （timing/geo/disexport），需要驱动器里有一张已刻过的盘。
- GUI 内首刻尚未实测：刻录按钮调用的 xorriso 命令与 2026-11-09
  两张定版盘的手工刻录命令一致，探盘与确认框已验。
