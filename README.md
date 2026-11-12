# discimagestudio-linux

简体中文 | [English](README.en.md)

A Linux GUI for DiscImageStudio: compose a picture, solve it with the
official CLI, and burn it onto a DVD — with a burn-safety pass that
makes any picture burnable.

DiscImageStudio 官方 GUI 的 Linux 前端：功能对齐官方 WPF 版的操作面，
后端全部走官方 CLI，投影与求解数学不在本工程重写。官方 CLI 与
disc-probe 均随仓自带（见下「自带后端」），clone 下来即完整。

## 架构

- 壳：MyGo（github.com/egoist/mygo）原生绘制，控件层用 Onevra 组件
  与亮色主题
- 后端：子进程调用官方 DiscImageStudio CLI（`solve` / `simulate` /
  `selftest`）；刻录走 `xorriso -as cdrecord -dao`；探盘
  `dvd+rw-mediainfo`；校准子进程调用 disc-probe
- 成像：图层合成在 Go 侧实现（golang.org/x/image）；画布预处理复刻
  定版 PIL 管线（YCbCr 的 Y 通道 autocontrast cutoff=1 +
  UnsharpMask r6/80%/2），与参考产物视觉等价

## 自带后端

- `official/`：官方 CLI v1.5.0（linux-x64）原版二进制，含其
  LICENSE 与 THIRD-PARTY-NOTICES；版本与 sha256 钉在
  `official/VERSION.json`（与上游发布的 SHA256SUMS 核对一致）。
  GUI 默认使用仓内副本；设置里改指外部 CLI 时，若其 sha256 与
  钉版不一致，首页会给出提示（只提示，不拦截）。
- `probe/`：disc-probe（bczhc 的移植，GPL-3.0），校准页以
  `python3 -m discprobe` 在此目录运行；同目录附本工程的拟合
  脚本与预设 JSON。来源与取舍见 NOTICE。

## 页面

- 首页：流程状态、几何预设与当前参数总览
- 设计：多图层合成（位置/高度/旋转，滑杆＋数字输入＋画布拖动与
  滚轮缩放），固定视图场，所见即所得
- 校准：驱动 disc-probe 做 timing（转速/CAV 判定）与 geo（几何
  拟合），拟合结果可导出为求解预设
- 导出：几何与全部 solve 参数可编辑，生成 ISO 并可读回预览
  （官方 simulate 渲染）
- 刻录：探盘状态、速度选择、刻录与弹盘
- 设置：CLI 路径、工作目录、刻录设备与速度

## 画布预处理（清晰度）

盘面图像最终由坑型疏密呈现，细节要先经过求解器的色调处理与抖动
量化，细对比在这个过程里最容易被吃掉。合成管线因此有一道固定的
亮度预处理（`imaging.go` 的 `PreprocessImage`，复刻定版参考管线）：

- 图像转到 YCbCr，只处理亮度（Y）通道，色度通道原样不动——盘面
  细节由亮度承载，动色度没有收益
- Y 通道先做 autocontrast（cutoff=1：两端各掐掉 1% 极值后拉满
  量程），把中间调的层次拉开
- 再做 UnsharpMask 锐化（半径 6、强度 80%、阈值 2），预先抬高边缘
  对比，抵消色调处理与抖动对细线条的平滑

参数为实盘标定的定版值，Go 复刻与参考产物视觉等价。它与下面的
刻录安全一样是固定工序、没有开关：预处理管清晰度，安全构造管
可刻性。

## 刻录安全（burn safety）

大面积平坦暗场是刻录杀手：经求解器色调处理后，它们变成 ECC 块
尺度的大片单一坑型板块，会让刻录机在盘面中途以介质写错误停机；
平坦亮场（稀疏坑型）则天然安全。本工程在导出管线里内置一道固定
的单遍构造（`burnsafe.go`），让任何图片都可刻：

- 画布未被图片覆盖的区域默认为白（稀疏坑型），不再是黑
- 导出合成的最后一步逐格扫描画布：局部平均亮度过低、且几乎没有
  阈上白像素的格子（平坦暗场在类别层面的确切形态），在同一遍里
  按精确配额把像素以分散点序翻白，把格均值抬到安全地板——标定
  实验表明求解器实现的暗类占比只由局部平均亮度决定，地板值对
  应该占比约 0.75，低于 0.80 的危险线
- 一遍完成：没有事后检查、没有重解、没有需要用户操心的开关，
  亮度等参数回归纯观感用途；带真实细节（有阈上高光）的区域一
  像素不碰

实测驱动器与介质的笔记见 [附录](APPENDIX.md)：Apple USB SuperDrive A1379（GX40N 机芯）＋ CMC MAG. AM3 的唤醒与供电、标定值，以及这台驱动器对数据形态的兼容性边界。

## 构建与运行

依赖：Go ≥ 1.24、xorriso、dvd+rw-tools（探盘）、eject（弹盘）。
后端已随仓自带，无需另备。

```sh
./run.sh          # 构建并启动
go test ./...     # 测试（与参考产物的对照测试需 DIS_FIXTURE_DIR）
```

设置存于 `~/.config/dis-gui/settings.json`；产物（canvas.png /
disc.iso / simulate.png）落在设置里指定的工作目录。设置里的
CLI/probe 路径留空（用默认）时优先解析到仓内副本。

环境钩子：`DISGUI_OPEN=<图片路径>` 启动即载入该图为图层并落在
设计页。

## 已知限制

- 仅覆盖 DVD 线；官方 GUI 的 CD / Blu-ray 档位未复刻
- 自带 CLI 为 linux-x64 版；其他平台请在设置里改指本平台的
  官方 CLI（版本不一致会有提示）
- 校准页的 timing/geo 需要驱动器里有一张已刻录的盘
- 本工程是前端：几何、求解与读回渲染都由官方 CLI 负责，其版本
  行为变化会直接影响产物

## 许可

GPL-3.0，见 LICENSE。与上游项目的关系见 NOTICE。
