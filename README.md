# discimagestudio-gui

A Linux GUI for DiscImageStudio: compose a picture, solve it with the
official CLI, and burn it onto a DVD — with a burn-safety pass that
makes any picture burnable.

DiscImageStudio 官方 GUI 的 Linux 前端：功能对齐官方 WPF 版的操作面，
后端全部走官方 CLI，投影与求解数学不在本工程重写。

## 架构

- 壳：MyGo（github.com/egoist/mygo）原生绘制，控件层用 Onevra 组件
  与亮色主题
- 后端：子进程调用官方 DiscImageStudio CLI（`solve` / `simulate` /
  `selftest`）；刻录走 `xorriso -as cdrecord -dao`；探盘
  `dvd+rw-mediainfo`；校准子进程调用 disc-probe
- 成像：图层合成在 Go 侧实现（golang.org/x/image）；画布预处理复刻
  定版 PIL 管线（YCbCr 的 Y 通道 autocontrast cutoff=1 +
  UnsharpMask r6/80%/2），与参考产物视觉等价

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

## 构建与运行

依赖：Go ≥ 1.24、官方 DiscImageStudio CLI 二进制（需自行准备，
在设置页指定路径）、xorriso、dvd+rw-tools（探盘）、eject（弹盘）。

```sh
./run.sh          # 构建并启动
go test ./...     # 测试（与参考产物的对照测试需 DIS_FIXTURE_DIR）
```

设置存于 `~/.config/dis-gui/settings.json`；产物（canvas.png /
disc.iso / simulate.png）落在设置里指定的工作目录。

环境钩子：`DISGUI_OPEN=<图片路径>` 启动即载入该图为图层并落在
设计页。

## 已知限制

- 仅覆盖 DVD 线；官方 GUI 的 CD / Blu-ray 档位未复刻
- 校准页的 timing/geo 需要驱动器里有一张已刻录的盘
- 本工程是前端：几何、求解与读回渲染都由官方 CLI 负责，其版本
  行为变化会直接影响产物

## 许可

GPL-3.0，见 LICENSE。与上游项目的关系见 NOTICE。
