# disc-probe

[English](README.en.md) | 简体中文

让普通光驱自己测出一张盘的螺旋几何，再把图片刻到 DVD-R 或 CD-R 的数据面上。整个过程不用拍照描点。

<p>
<img src="docs/showcase/qingming_title.jpg" width="42%" alt="刻在 DVD-R 数据面上的《清明上河图》题字和局部">
<img src="docs/showcase/qingming_full.jpg" width="55%" alt="整张盘上的《清明上河图》，排成内外两圈">
</p>

《清明上河图》，刻在 Ritek F1 DVD-R 上，这是直出的结果：几何全部来自读取计时，这张盘只刻了一次，没有试刻、拍照标定或扫描修正。照片是手机拍的，只裁到盘面、缩小并模糊了背景。

## 原理

往数据面刻图，要知道第 N 个扇区落在盘上的哪个角度。每批盘的轨距和位长都有极小的差别，绕几万圈累积下来，图就会扭成漩涡。常见的办法是刻一张标定图，拍照描点，再反复修正。

disc-probe 让光驱来量。盘匀速转动时，一个扇区读完的时刻，就是它转到读取头下的时刻。所以轮流读两个扇区，把完成时间的差换算成角度，就知道它们在盘上隔了多远。一次只能测出 360° 以内的余数，所以从近到远逐级测，每一级都用前面的结果预测整圈数，DVD 测 22 级、CD 测 36 级就能覆盖全盘。

<picture>
<source media="(prefers-color-scheme: dark)" srcset="docs/showcase/how_it_works_zh_dark.svg">
<img src="docs/showcase/how_it_works_zh_light.svg" width="100%" alt="示意图：轮流读两个扇区，把时间差换成角度，再由近到远逐级测">
</picture>

这套测量只发读取类命令。测完可以直接生成 ISO，也可以导出 [DiscImageStudio](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio) 预设。

## 效果

### 几何精度

<img src="docs/showcase/grid_lines_zoom.jpg" width="60%" alt="网格盘扫描的局部，线条笔直">

这是网格测试盘的局部，600 dpi 平板扫描，高通处理后约 38 mm 见方。这张盘同样只用计时结果、只刻一次（HL-DT-ST GH70N，Ritek F1 DVD-R）。8 张扫描量得 25–54 mm 内的转角峰峰值 0.11°，rms 0.03°。在 50 mm 半径处，0.03° 大约是 0.03 mm。

<img src="evidence/figures/bending_before_after.png" width="75%" alt="三张网格盘的转角随半径的变化">

图中绿线是这张盘。测量方案是[刻录前预先登记](docs/PREREG_remeasure.md)的。

### 细节

<img src="docs/showcase/dense_motifs.jpg" width="75%" alt="微距照片：不可能三角形、小人和最上方的三线组">

密铺盘的微距照片，也是只刻一次。不可能三角形宽 4.2 mm，小人高 6.8 mm，最上方是测线宽用的三线组。肉眼能看清最小的 1 mm 三角形，它每条边约 0.15 mm 宽。600 dpi 扫描能分开 0.12 mm 的线，0.08 mm 勉强，再细就到扫描仪的极限了。

### 颜色（实验中）

反复写同一段数据，这一小块盘面就像一块光栅，把白光分开。重复的间距不同，同一个方向上看到的颜色就不同，换个角度颜色也会变。这部分还在实验，进展在 [#108](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108)。

<img src="docs/showcase/roses_source.jpg" width="42%" alt="GPT Image 生成的玫瑰原图"> <img src="docs/showcase/roses_7185.jpg" width="42%" alt="刻好的玫瑰 DVD-R 数据面的照片，部分花瓣显紫色">

左边是 GPT Image 生成的原图，右边是刻好的 DVD-R 的照片，背景已遮掉。这张盘按紫色设计，找对角度时，部分花瓣接近原图的紫色，只是暗一些。它只在一个角度看起来对，手机一动花瓣就变色，也不能任意指定颜色，目前只做过紫色。详情见 [#168](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/168)。同一张盘还存了 1.38 GB 数据，整盘读回零错误，见 [#170](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/170)。这些都是一张盘的早期结果，玫瑰盘的工具还没公开。

<img src="docs/showcase/rosettes_closeup.jpg" width="75%" alt="闪光灯下同一朵花上显出多种颜色的花瓣">

能自己刻的是这张花盘，同一朵花上有 3 到 4 种颜色，我们只在 RITEKF1 DVD-R 上刻过。先按[快速开始](#快速开始)测盘，再生成图案。这一步不碰光驱：

```bash
python tools/compose_rosettes.py
```

它会打印下一条命令，填好就能生成镜像：

```bash
python -m discprobe image --geo latest --design-npy iso/rosettes_design.npy --textures "MIX:92,87,83,8D,60" A5 92 66 ED00 2AE304 --r-max 57.6 --output iso/rosettes.iso
```

预览图的颜色只用来区分纹理，和盘上的颜色对不上是正常的。拍的时候关灯，只开手机闪光灯，手机往旁边偏开一点，步骤见 [#108](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108)。

### 其他光驱和盘

- 同一种 RITEKF1 盘上，我们的计时结果和 bczhc 独立的拍照标定（[DiscImageStudio #53](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/53)）相差约 ±0.05°。
- 一台约 15 年前的笔记本光驱（PLDS DS8A8SH，SATA 转 USB）测出的几何，和我们的 GH70N 相差约 0.05° rms。
- CMC CD-R 需要多做一步：计时测不出数据沿轨道的绝对位置，要刻一张网格盘来定这个常数。在 GH70N 上它约为 206 帧，用第二张盘验证后只剩 +0.6 帧。这批盘的轨距还有波浪，第二张盘残余 0.16° rms。

## 快速开始

> 如果你在 2026-11-06 之前用 `--correction` 导出过预设，修正可能没有生效。更新后重新导出就行，不用重新测盘。

要准备同一批的空盘：DVD 至少 2 张（测量、刻图），CD 至少 3 张（测量、标定、刻图）。测量盘刻好后不能再刻图，但可以留着，同一批的盘以后不用再刻一张。另外需要 Windows、Python 3.10 以上和一台能刻录的光驱。Linux 和 macOS 见[实践报告表](#有实践报告的光驱)下方的移植版本。下面以 DVD 为例，CD 见后面的 [CD 路线](#cd-路线)。

用管理员身份打开终端，安装依赖，并用模拟驱动器确认环境正常。不方便用管理员身份时，在读盘的命令后加 `--transport imapi`：它经 Windows 自带的 IMAPI2 刻录接口（`IDiscRecorder2Ex`）发同样的命令，普通用户即可；默认的 `auto` 在 SPTI 被拒时会自动改用它。

```bash
git clone https://github.com/Ashley-QwQ/disc-probe
```

```bash
cd disc-probe
```

```bash
python -m pip install numpy pillow scipy
```

```bash
python -m discprobe selftest
```

不确定下一步跑什么，就运行 `guide`。它读 `results` 文件夹，列出哪些步骤做过了，并打印下一条命令，不碰光驱：

```bash
python -m discprobe guide
```

在终端里，`timing` 和 `geo` 跑完会给一句结论，每条命令跑完也会打印下一步可以直接复制的命令。系统是中文时，帮助、提示和测量输出都显示中文，也可以用 `--lang zh` 或 `--lang en` 指定；脚本和管道仍是英文，也没有这些结论和提示。其他用法见[手动使用](#手动使用)。

<img src="docs/showcase/cli_demo_zh.gif" width="100%" alt="终端动图：开屏光盘、下一步提示、测量进度行和贪吃蛇">

*这是在模拟光驱上录的，不是真实测量。贪吃蛇的按键由脚本代按；测量时按 `g` 才会打开。*

### 第 1 步：刻一张随机数据盘

测量盘必须是普通数据，刻了图案的盘读不出来。用 Windows 自带的光盘映像刻录机刻 `iso/random.iso`。

```bash
python -m discprobe random --output iso/random.iso
```

### 第 2 步：看这台光驱能不能用

约 1 到 3 分钟。刻完托盘可能会弹出，先推回去，等几秒再跑。结果要是 `CAV`，抖动越小越好。只有一台光驱时，在终端里可以不写 `--drive`。

```bash
python -m discprobe timing --drive H:
```

### 第 3 步：测几何

约 5 分钟。DVD 测 22 级，终端的进度行会显示走到第几级。

```bash
python -m discprobe geo --drive H:
```

有些盘的轨距会缓慢变化。比如 RITEKF1 恒定轨距就够，`CMC MAG. AM3` 和一种 RITEK DVD+RW 则要二次修正（残差从 0.38°、0.61° 降到约 0.08°）。

残差偏大时，`geo` 跑完会自动比较这两种模型，不用再测盘。二次模型明显更好，它就让你先写修正文件，并把 `--correction` 写进后面的命令，照着复制就行。否则它会告诉你多半是读取噪声，可以继续。写修正文件的命令是这样的：

```bash
python tools/geo_polyfit.py results/geo-H-... --write-correction correction.json --order quadratic
```

### 第 4 步：生成图片 ISO，刻到同一批的空盘上

`--geo latest` 用最近一次完整的真实测量，会打印选中的是哪一次；也可以填结果文件夹或 `summary.json` 的路径。有修正文件的话再加 `--correction correction.json`。图片长边铺满 116 mm（可用 `--diameter-mm` 改）并保持比例，不足的地方留白。生成后程序会抽查扇区，和设计逐字节核对。

```bash
python -m discprobe image --geo latest --picture my_picture.png --output iso/picture.iso
```

想继续用 DiscImageStudio 的话，可以导出预设。`--sectors` 填你这张盘的扇区数（对空白盘运行 `info` 会打印，DiscImageStudio 里也填这个数；填多了可能封盘失败），半径范围填 `geo` 实际测到的范围，有修正文件的话同样加 `--correction correction.json`。`geo` 跑完打印的命令已经填好这些值。程序会打印和测量结果的转换误差，先看一眼再刻。目前预设要手动填进 DiscImageStudio：新建工程，填内外半径、扇区数和一二三次项：

```bash
python -m discprobe disexport --geo latest --sectors 你的扇区数 --r-min 25.8 --r-max 54.5 --output dis_preset.json
```

### 第 5 步：看盘和拍照

盘面像一面镜子，拍到的主要是它映出来的东西。屋里的灯和亮的墙会把图盖住，所以刻好的图不一定一眼看得到。彩虹"披萨片"是出厂导槽的衍射，不是刻上去的。小而亮的光源紧挨着眼睛或相机时，图像整盘可见。

<img src="docs/showcase/lighting_setup_zh.png" width="80%" alt="两种打光对比：开着灯直接拍，盘面发白；关灯只用一盏小灯，盘稍微歪一点，图才显出来">

1. 关掉屋里的灯，只留一盏小灯。手机手电筒也行，或者把显示器调成黑底，中间开一个小白方块。
2. 灯放在手机旁边，都离盘远一点。约 1 米最好，放不下就尽量远。
3. 盘稍微歪一点，让它映出的是暗处，不是灯。在屏幕上慢慢转动，盘面一暗，图就会显出来。
4. 手机对焦后，把曝光往下拉一点。
5. 盘后面和手机后面尽量是暗的，手也别离盘太近。

这是我们在 DVD 上试过的方法。手边有平板扫描仪的话扫一张也行，扫描不受屋里反光的影响。

### CD 路线

CD 还有一个计时测不到的常数，所以要多刻一张标定盘。下面是推荐的做法：测完导出预设，交给 [DiscImageStudio](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio) 精细标定。网格盘、纹理环等其他做法见[使用手册](docs/MANUAL.md#cd-r纹理计时与刻图)。

1. 刻测量盘，用第 1 张空盘。在 GH70N 上 8x 约 11 分钟。刻完托盘会弹出，`-Reload` 只是再把它收回来，不会提前打开托盘；超薄光驱要自己推回去。

   ```bash
   python -m discprobe random --media cd --output iso/cd-random.iso
   ```

   ```bash
   powershell -ExecutionPolicy Bypass -File tools/burn_imapi.ps1 -Drive H: -Iso iso/cd-random.iso -Speed 8 -Burn -Reload
   ```

2. 测量，`timing` 约 1 到 3 分钟，`geo` 约 5 分钟，共 36 级。`timing` 说不是 CAV 时，按它的提示换速度，`geo` 也用同一个速度。`timing` 跑完打印的 `geo` 命令更短，用默认的测量范围，也能用；这里写全是为了测到更大的半径。

   ```bash
   python -m discprobe timing --media cd --drive H: --speed 1411
   ```

   ```bash
   python -m discprobe geo --media cd --drive H: --speed 1411 --host-delay-ms 35 --ranges 2000-356000
   ```

3. 导出预设。`geo` 跑完打印的 `disexport` 命令已经填好数值，直接复制。其中 `--sectors` 可能只是测量盘刻了多少，所以放一张空盘跑 `info`，不一样就改成 `info` 的数，DiscImageStudio 里也填这个数。有用户[报告](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19442161)它的“从光盘读取”给的数偏大，照它填封盘失败，所以不要用那个数。
4. 精细标定，用第 2 张空盘。在 DiscImageStudio 里填入预设，到辅助标定页选精细标定，新建标靶，刻盘，拍照矫正，描点，反推并应用，再保存为预设。步骤见它的[辅助标定说明](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/blob/main/docs/CALIBRATION.md)。
5. 用这组参数在 DiscImageStudio 里刻图，用第 3 张空盘。

<a name="光驱兼容表"></a>

## 有实践报告的光驱

这里只列已经有人测过的光驱，没列出的也可能能用，先跑一次 `timing` 就知道。数据大多来自 `timing`。欢迎在 [DiscImageStudio discussion #107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) 补充。

### 已刻图成功

这些多半是用户反馈，看的是成品，大多没有量化图像误差。

| 光驱 | 盘 | 结论 | 来源 |
|---|---|---|---|
| HL-DT-ST GH70N（NYA2） | Ritek F1 DVD-R | 测量和刻图都已验证，首刻约 0.1° | 本仓库 |
| HL-DT-ST GH70N（NYA2） | CMC CD-R | 用 `--speed 1411`；沿轨道常数已用两张网格盘验证 | 本仓库 |
| MATSHITA BD-MLT UJ260AF（macOS） | RITEKF1 DVD-R | `geo` 和 `disexport` 跑通，已有人用它刻图成功 | NaiveTomcat，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| MATSHITA BD-MLT UJ272 | RITEKF1 DVD-R | 预设直接填进 DIS，十字线又直又垂直（目测），也刻出了成品图 | domerawind，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19421274) |
| HL-DT-ST GP90NB70 | `CMC MAG. AM3` DVD-R | 恒定轨距预设刻图，最高 8x 下也清晰成像（照片待补） | li-yifei，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19410771) |
| HL-DT-ST GP57EB40 | `CMC MAG. AM3` DVD-R | 预设经 DIS 刻图，轮廓和设计一致；抖动是目前报告里最低的 | MasterMT9，[disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |
| HL-DT-ST GP65NB60 | 铼德 DVD+RW（`RITEK/004/48`） | 用 `--speed 3324`，要带二次修正。加 `--ranges 10000-2290000 --chi2-abort 100` 测到 24–58 mm，修正后刻图成功，最外圈径向线略翘（用户反馈，无量化图像误差） | FanJZSS，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19445201) |
| PIONEER DVR-S21（PA01） | DVD-R（`MCC 03RG20`，真伪不明） | 用 `--speed 22160`。同一张图用 `image` 的 ISO 和 DIS（16x CAV，直接填 disc-probe 的预设）各刻一张，都没有可见偏差，DIS 那张可能略有缩放。之前 DIS 精细标定没有出线 | Lakida0，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19434982) |
| HL-DT-ST SP80NB80（RC00） | DVD-R，Verbatim AZO（`MCC 03RG20`） | 用 `--speed 3324`（约 1432 rpm）。`geo` 跑通，再用 DIS 精细标定，一共刻了 5 张盘后图案对上了（用户反馈，无量化图像误差）。这台光驱读 `CMC MAG. AM3` 时不适合，见下 | Sliicy，[DIS #171](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171) |
| HL-DT-ST GHB0N（JE01） | Banana DVD-R（`MCC 03RG20`） | 用 `--speed 5540`。`geo` 跑通，手调后的参数刻出的圆环和径向线规整（用户反馈，无量化图像误差）。和先锋 DVR-S21 测的同内圈编码的盘相差约 0.05° rms | dhao2001，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19438546) |
| 联想 PLDS DS8A8SH（KL31） | 羽毛/旭宇达 DVD+R | 之前拍照分析卡住，用预设刻图成功 | anyezhixie，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19426856) |
| PLDS DU8A6SH（macOS） | 绿联 DVD+R（`MCC 004`） | 导出 ISO 用系统刻录（3x）出图正确；DIS 流式刻录选 2x 时出错，原因未查 | ShiroiTree，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS SDRW-08D2S-U | Verbatim CD-R | 用 `--speed 4234`；预设不做精细标定，最低速刻图，轮廓和原图一致 | moodyos，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19424471) |
| ASUS SDRW-08D2S-U（B911，Linux） | Verbatim DVD+R | `geo` 加网格扫描修正后导出预设，刻图成功 | NO-ob，[disc-probe #6](https://github.com/Ashley-QwQ/disc-probe/issues/6) |
| Sony Optiarc AD-7201S | Memorex CD-R | `geo` 后再用 DIS 图像法精修才出图（之前试约 15 张未成） | pugod124，[disc-probe #2](https://github.com/Ashley-QwQ/disc-probe/issues/2) |

### 能测，刻图结果不完整或还没有报告

| 光驱 | 盘 | 结论 | 来源 |
|---|---|---|---|
| Slimtype DS8A9SH | CD-R（ATIP 97:15:17） | 抖动偏大（2.9–3.4°）。`geo` 跑通，两张盘校准成功（用户反馈） | kasumikira，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19415813) |
| PLDS DS8A8SH | RITEK ARITA DVD-R | Windows 和 Linux 上 `geo` 都跑通；Windows 上和 GH70N 相差约 0.05° rms | bczhc，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS DRW-24D5MT | DVD+R（`MCC/004/0`） | `geo` 跑通，恒定轨距 rms 0.29° | Disappear9，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS SDRW-08U9M-U | RITEK ARITA DVD-R | 只测了 `timing`，`geo` 待测 | bczhc，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| HP BD-RE BU20N | 联想 Thinkplus CD-R | 用 WindowsNoEditor 自己的探测程序测的，不是本工具，方法相同 | WindowsNoEditor，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| PLDS DU-8A5LH | 海存 POSO CD-R | 同样用他们的探测程序。整盘校准没问题，测局部细节不适合 | WindowsNoEditor，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| TSSTcorp SN-208FB（CH00） | DVD-R（`RITEKF1`） | 测量很好，和本仓库 GH70N 相差约 0.05° rms。普通数据盘能刻（最高 8x），但刻图案屡次失败（`0xC0AA0301`，从约 0.3 MB 到约 284 MiB），三种盘都试过。刻图建议换一台光驱 | Lakida0，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19435910) |

### 目前不建议用

这里说的是报告里那张盘和那个速度下的结果，换个条件不一定一样。

| 光驱 | 盘 | 结论 | 来源 |
|---|---|---|---|
| ASUS BW-16D1H-U | RITEK ARITA DVD-R；BD-R | `geo` 能跑完，但结果不建议用来刻图：27–54 mm 有约 9.5° 峰峰的偏差 | bczhc，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| HL-DT-ST SP80NB80 | DVD-R（`CMC MAG. AM3`） | 噪声太大，`geo` 在第二级停下，降速也不降 | Sliicy，[disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |
| HL-DT-ST BD-RE WH14NS40（1.02） | DVD-R（Verbatim AZO 95101 2201-203） | 重新放盘后是 CAV，约 9280 rpm，`timing` 正常；但 `geo` 跑了 18 分钟，只在 42.3–42.8 mm 拿到 6 个点，判定噪声太大。加 `--speed` 会变成 CLV，要重新放盘才恢复。用别人的参数刻图成功（1 张，用户反馈） | sanitysama，[#171](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171#issuecomment-6701560294) |
| MATSHITA UJ8B1（用户标注 ThinkPlus GP90NS60） | 铼德 DVD+RW（`RITEK/004/48`） | `--speed 3324 --sectors 16` 把抖动从约 307 µs（`--speed 5540`）降到约 82 µs，但 29–33 mm 两次都有 5–10° 的局部跳动，`geo` 在那里停下。跳过这段后只覆盖 34–54 mm，rms 1.54° | Doctor-shengru，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19444762) |
| HP HLDS GUD0N | DVD-R（`CMC MAG. AM3`） | `geo` 能跑完，但 rms 3.7°，单点偏差最大约 8°，结果不可信 | Sliicy，[disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |

<details>
<summary>完整数据：接口、缓存、转速、抖动和细节</summary>

| 光驱 | 接口 / 系统 | 盘 | 缓存 | 转速模式 | 单次抖动 | 备注 | 来源 |
|---|---|---|---|---|---|---|---|
| HL-DT-ST GH70N（NYA2） | SATA / Windows | Ritek F1 DVD-R | `fua` | CAV，4x 约 2830 rpm | 0.43–0.55° | 阶梯和刻图都已验证（首刻约 0.1°）；外圈约 53 mm 处会换转速档 | 本仓库 |
| HL-DT-ST GH70N（NYA2） | SATA / Windows | CMC CD-R | `fua` | CAV，用 `--speed 1411`（约 2080 rpm）；`--speed 2822`（3226 rpm）下 49.8 mm 以外完成时刻晚约 0.2 ms，不能用 | 0.5–0.76° | CD 阶梯可用；这条路径（IMAPI 刻录 + READ(12)）的沿轨道常数约 206 帧，已用两张网格盘验证（第二张残余 +0.6 帧）；这批盘的轨距有约 0.45° 峰峰的波浪 | 本仓库 |
| MATSHITA BD-MLT UJ260AF（1.01） | USB 3.0 / macOS（[discprobe-macos](https://github.com/NaiveTomcat/discprobe-macos)） | RITEK RiDATA 可打印 DVD-R（MID `RITEKF1`） | `fua` | CAV，2364 rpm | 0.65–0.87° | `geo` 和 `disexport` 跑通，参数见 [#87](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/87)，已有人用它刻图成功；和本仓库 GH70N 的 Ritek F1 结果在 25–58 mm 相差 0.13° rms（30 mm 以外在 ±0.2° 内）。FUA 重读固定两圈；SET CD SPEED 请求 4x 不换档；建议 `--sectors 16` | NaiveTomcat，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| MATSHITA DVD+-RW UJ8B1（D.03，用户标注 ThinkPlus GP90NS60） | Windows，接口未报告 | 铼德 ExcellentX DVD+RW 4X（`RITEK/004/48`），随机数据 | `fua` | CAV：不加 `--speed` 约 4691 rpm，`--speed 3324` 和 `--speed 5540` 都约 2354 rpm | 4691 rpm 下 2.79–9.81°；2354 rpm 下 1.50–6.06°（106–429 µs），加 `--sectors 16` 后 0.79–4.84°（56–342 µs） | 不建议用它测量。`geo` 开始时的抖动：`--speed 5540` 307 µs，`--speed 3324 --sectors 16` 82 µs，`--speed 5540 --sectors 16` 192 µs，转速相同，所以这台上 3324 更好。`--speed 5540 --reps 32` 能跑完，但 rms 2.68°，不确定度约 1.7°，28.9–32.7 mm 从 +5° 跳到 −8°。`--speed 3324 --sectors 16` 在 LBA 358368（约 31.8 mm）差 10° 后停下，同一段两次出问题，不太像随机噪声，原因未查，没有重刻对比。`--ranges 450000-1950000` 跳过这段后[跑完](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19444762)，覆盖 34.22–54.39 mm，不确定度 0.59°，rms 1.54°，χ²/dof 4.9，LBA 1949984 还差 3°。和 FanJZSS 在 GP65NB60 上测的同种盘在 34–54 mm 相差约 0.2° rms，在不确定度以内。 | Doctor-shengru，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19444762) |
| MATSHITA BD-MLT UJ272（1.02） | USB 2.0 转接 / Windows | RiDATA DVD-R 银面（`RITEKF1`，PW104），随机数据 | `fua` | CAV，2364 rpm（`--speed 5540`） | 0.61–0.80° | `geo` 跑通，恒定轨距 rms 0.28°，和本仓库 GH70N 相差约 0.15° rms。预设直接填进 DIS，没有额外校准，十字线又直又垂直（用户目测，无量化误差），也刻出了成品图。此前照片标定一直不成功 换用 Lakida0 的校准数据（扇区数 2295104）后[封盘正常](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19440415)，设了 4x 但实际全程 2x，网格和文字清楚（用户反馈）。 读 BD-R（MID `RITEK (000)`，光驱报成 BD-ROM）是恒定线速度，[`timing` 判不成 CAV](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19440933)：默认和 3324 约 1.6x，8990 和 26974 约 2.1x，`--cav` 没有作用。 铼德 mini DVD-R（`RITEKG04`）：测量盘刻 700000 扇区，`geo` 量到 24.44–36.02 mm，预设用 713936 扇区填进 DIS，2x [刻图成功](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19442161)，垂直线和 F 略弯，极小的字可读（用户反馈）。 同一台测铼德 e 时代 DVD-R（`RITEKF1`）：`geo` 22 级，rms 0.219°，chi2/dof 1.34，[和 RiDATA 的预设相差约 0.1° rms](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19442592)（峰峰约 0.35°），和本仓库 GH70N 约 0.07° rms，都在不确定度以内。 用 `disexport --sectors 2297888` 重新拟合的预设刻 RiDATA（`RITEKF1`），[封盘正常](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183#issuecomment-6690200194)，实际 4x，图像正常（用户反馈，只有一张盘，未写明用哪台光驱）。比 2298496 少的 608 扇区是收尾要用的边界开销（TBO 592 加 BSGA 16），见 [DIS 作者的说明](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183#issuecomment-6691519009)。 | domerawind，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19421274) |
| HL-DT-ST GP65NB60（PF00） | USB / Windows | 铼德 ExcellentX DVD+RW（`RITEK/004/48`），随机数据 | `fua` | CAV：不加 `--speed` 2355 rpm，`--speed 3324` 1432 rpm，`--speed 11080` 3596 rpm | 1432 rpm 下 0.23–0.29°（26–34 µs），2355 rpm 下 0.53–0.65°，3596 rpm 下 1.07–1.12° | 按角度算抖动很低，建议用 `--speed 3324`。1432 和 2355 rpm 的相位只差 0.17° 以内，3596 rpm 在 52 mm 附近差到 +0.97°。刻标定图案的盘读不出，要用随机数据盘。`geo` 22 级跑通（`--speed 3324`），恒定轨距 rms 0.61°、χ²/dof 10.8，二次轨距降到 0.078°、0.20，说明这张盘轨距有缓慢变化，要带修正。用带修正的预设以 2.4x 刻标定图，径向线只有一点点歪（用户目测）；之前手动刻十几次才看到径向线 配 CD-RW（AnyBurn 10x）：`disexport --along-track-frames -100` 和 DIS 精细标定只差约 2 帧，径向线看起来是直的（用户反馈）；两种刻法都在约 33–34 mm 有约 0.2 mm 的错位（从照片粗量）。 后来 `--speed 3324 --ranges 10000-2290000` 在内圈停下（拟合误差比 27），加 `--chi2-abort 100` 跑完 22 级，覆盖 24.20–58.09 mm，恒定轨距 rms 0.951°、χ²/dof 26.2，二次 0.092°、0.27。[带二次修正刻图成功](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19445201)，最外圈径向线略翘（用户反馈）。 | FanJZSS，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19445201) |
| HL-DT-ST GP90NB70（1.00，IO-DATA 外置） | USB / Windows | VHR12JP53SV4 DVD-R（MID `CMC MAG. AM3`），随机数据 | `fua` | CAV，2355 rpm（`--speed 5540`） | 0.25–0.28°（18–20 µs） | 抖动很低。`geo` 22 级和 `disexport` 跑通。恒定轨距 rms 0.38°，二次轨距降到 0.087°，说明这种盘轨距有缓慢变化。用户[后续反馈](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19410771)已用恒定轨距预设刻图，机器最高 8x 写速下也能清晰成像（照片待补，尚无量化图像误差）。FUA 重读三圈 | li-yifei，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS BW-16D1H-U（E116） | USB / Windows、Linux | RITEK ARITA DVD-R，随机数据；BD-R | `fua` | DVD：CAV，9204 rpm（请求 2770、5540 都不降速）。BD-R：内、中圈约 9705 rpm，外圈约 1655 rpm，第一次运行不稳，判为 mixed | 约 200 µs，不随转速变（DVD 10–14°，BD-R 2–15°） | `geo` 能跑完，但**结果不建议用来刻图**：和 [#53](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/53) 同一批盘的几何比，27–54 mm 有约 9.5° 峰峰的偏差（外圈 54 mm 处 +7.7°），和 50 mm 以外约 0.2 ms 的完成时刻跳变吻合 bczhc 的[排查报告](https://gist.github.com/bczhc/0323c1762b0d47a46b59159a83353703)：`SET CD SPEED` 接受但转速不变，`SET STREAMING` 被拒（5/24/00）。DVD-RW 固定约 4840 rpm，抖动 4.8–7.0°。拆机帖说它是 Pioneer BDR-209（SCSI 读不出，非实测）。建议测量换别的光驱，刻录仍可用它。 BD-R 请求 5540 时是[恒定线速度](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19441086)，约 2x。 | bczhc，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| PLDS DVD-RW DS8A8SH | SATA 转 USB / Windows、Linux（[bczhc/disc-probe](https://github.com/bczhc/disc-probe)） | RITEK ARITA DVD-R，随机数据 | `fua` | CAV，2388 rpm | Windows 0.52–0.88°（36–61 µs），Linux 1.37–1.62°（96–113 µs） | 约 15 年前的笔记本光驱。Windows 上 `geo` 跑通（22 点，rms 0.21°），和本仓库 GH70N 的结果相差约 0.05° rms，和 bczhc 的拍照标定（[#53](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/53)）在 5 个点上差 0.02–0.23°。Linux 上 `geo` 也跑通，和 GH70N 差 0.33° rms（27 mm 处约 −0.85°） | bczhc，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| 联想 PLDS DVD-RW DS8A8SH（KL31） | USB 3.0 / Windows | 羽毛/旭宇达 DVD+R，随机数据 | `fua` | CAV，2389 rpm（`--speed 5540`） | 默认转速 1.18–2.53°（56–120 µs） | `geo` 22 级跑通，恒定轨距 rms 0.178°，chi2/dof 0.82，不需要高阶修正。预设转换误差最大 0.001°。之前拍照分析卡住，用这个预设刻图成功（用户反馈，无量化图像误差） | anyezhixie，[DiscImageStudio [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19426856) |
| ASUS SDRW-08U9M-U | USB / Windows | RITEK ARITA DVD-R，随机数据 | `fua` | CAV，2355 rpm | 0.79–1.08°（56–76 µs） | 和同一张盘在 DS8A8SH 上的 5 个相位差 −0.23、+0.25、−0.67、−0.05、−0.04°；`geo` 待测 DVD-RW 上 `--speed 2770` 约 1432 rpm，抖动 0.69°，能响应降速（bczhc 的报告）。 | bczhc，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| HP BD-RE BU20N（LG OEM，0403） | USB / Windows，用 WindowsNoEditor 自己的探测程序 | 联想 Thinkplus CD-R 80 min | 每次先读远处，READ CD 单扇区 | CAV，1241 rpm（`0x0583`）、2482 rpm（`0x0B06`） | 1241 rpm 约 0.45°（约 60 µs），2482 rpm 约 1.3–3.0° | 不是用本工具测的，方法相同；在扇区约 65,600 处测到沿轨道约 +0.2 mm 的接缝 | WindowsNoEditor，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| Sony Optiarc AD-7201S（1H9K） | Windows | Memorex CD-R（ATIP 97:15:17），随机数据 | `fua` | CAV，2168 rpm（`--speed 2822`） | 0.61–0.68°（47–53 µs） | `geo` 36 级跑通，恒定轨距 rms 0.51°，二次 0.35°，有几个点偏离较大，原因未查。沿轨道常数还没测。`geo` 后再用 DIS 图像法精修，成功出图（之前试约 15 张未成）。读 DVD-R（`CMC MAG. AM3`）时约 7514 rpm，请求 4x 或 2x 都不降速（2x 时 7514 rpm），抖动 1.7–2.1°，内圈更差，恒定轨距 rms 0.51°，二次 0.41° | pugod124，[disc-probe #2](https://github.com/Ashley-QwQ/disc-probe/issues/2) |
| Slimtype DVD A DS8A9SH（EA16） | Windows | CD-R（ATIP 97:15:17） | `fua` | CAV，约 2033 rpm | 2.9–3.4°（238–275 µs） | `geo` 36 级跑通，chi2/dof 2.75，后面有些点偏 1–2°，恒定轨距不够或抖动造成，未分开。两张盘就校准成功（用户反馈，无量化图像误差） | kasumikira，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19415813) |
| HL-DT-ST SP80NB80（RC00） | USB / Windows | DVD-R（同一张盘在 HP 上读到 MID `CMC MAG. AM3`） | `fua`（约 200 ms，8 圈） | CAV，2355 rpm | 约 236–1714 µs（3–24°） | 噪声太大，`geo` 在第二级停下。`--speed 3324` 也不降速，噪声更大（723–3368 µs），不适合 | Sliicy，[disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |
| HP HLDS GUD0N（SD03） | 内置 / Windows | DVD-R（MID `CMC MAG. AM3`） | `flush` | 默认转速不稳定（混合、CLV）；`--speed 3324` 为 CAV，2401 rpm | 3.0–3.3°（206–228 µs），2401 rpm 下 | 最新版 `geo` 22 级跑完，但 rms 3.7°，chi2/dof 9.4，单点偏差最大约 8°，结果不可信 | Sliicy，[disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |
| HL-DT-ST GP57EB40 | Windows | DVD-R（MID `CMC MAG. AM3`），随机数据 | `fua` | CAV，2355 rpm | 0.11–0.16°（7.5–11 µs） | 抖动是目前报告里最低的。`geo` 22 级跑通，恒定轨距 rms 0.78°，二次 0.53°，有三个点噪声偏大。u、v 和 li-yifei 用 GP90NB70 测的同款盘几乎相同（179792.143 对 179792.142，5.5374125 对 5.5374129）。导出预设的转换误差最大 0.366°，rms 0.086°。用预设经 DIS 刻图成功，[照片](https://github.com/Ashley-QwQ/disc-probe/issues/1#issuecomment-6672481372)里图案清晰，轮廓和设计一致（用户反馈，无量化图像误差） | MasterMT9，[disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |
| PLDS DVD±RW DU-8A5LH | Windows，用 WindowsNoEditor 自己的探测程序 | 海存 POSO CD-R 80 min（ATIP 97:27:18） | 每次先读远处，READ CD | CAV，2032 rpm（`0x06E4`）；`0x0583` 下转速不恒定 | 每级 σ 中位数 0.47° | 阶梯残差 rms 0.73°。和 BU20N 测同一张盘，几何一致，只差一个约 25 帧的沿轨道常数。这台光驱读盘时，有些扇区的完成时刻固定偏开约 0.5°，同一张盘拿回 HP 上读就没有，所以是它读盘的问题，不是盘的问题：整盘校准没问题，测局部细节不适合。 | WindowsNoEditor，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS DRW-24D5MT（1.00） | Windows | DVD+R（MID `MCC/004/0`），随机数据 | `fua` | CAV：`--speed 5540` 2353 rpm，默认和 `--speed 11080` 4747 rpm | 2353 rpm 下 0.49–0.55°（35–39 µs），4747 rpm 下 0.78–0.98° | 两档相位差 0.4° 以内。`geo` 22 级跑通，恒定轨距 rms 0.29°，χ²/dof 2.35 | Disappear9，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS SDRW-08D2S-U | USB / Windows | Verbatim CD-R | `fua`（2 圈，57.4 ms） | `--speed 1411` 是 CLV 约 4x；`--speed 4234` 是 CAV，2090 rpm | 0.19–0.28°（15–23 µs），2090 rpm 下 | `geo` 36 级跑通（`--media cd --speed 4234`），恒定轨距 rms 0.485°。`disexport` 的预设经 `disc-presets.json` 导入 DIS，不做精细标定，同一台光驱以最低速刻图成功，图案轮廓和原图一致（[照片](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19424471)，用户反馈，无量化图像误差）。这张盘很薄、接近透明，要避开镜面反射的打光才看得清 | moodyos，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS SDRW-08D2S-U（B911） | USB / Linux（bczhc 的移植版） | Verbatim DVD+R（内圈编码 `ZE0460-DVR-T47D`） | 未报告 | 未报告 | 未报告 | `geo` 加网格扫描修正后导出预设，转换误差最大 0.118°，用它刻图成功（用户反馈，无量化图像误差）；另一份 Verbatim 预设对这张盘无效。预设和照片见 [DiscImageStudio #140](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/140) | NO-ob，[disc-probe #6](https://github.com/Ashley-QwQ/disc-probe/issues/6) |
| PLDS DVD-RW DU8A6SH | macOS（[discprobe-macos](https://github.com/NaiveTomcat/discprobe-macos)） | 绿联 DVD+R（MID `MCC 004`，内圈 `PR25014-P16`），随机数据 | `fua` | CAV，1796 rpm（`--speed 4155`；2x 和 3x 是同一档，4x 下 `geo` 中止） | 约 0.68–0.83° | `geo` 22 级跑通，rms 1.45°；51.4–52.8 mm 有一段噪声带，不完全复现，去掉后 0.21°，u、v 几乎不变。和 zhajial 对同款盘的 DIS 照片标定（[DiscImageStudio #132](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/132)）相差约 0.15° rms。导出 ISO 用系统刻录（3x）出图正确，DIS 流式刻录选 2x 时出错，原因未查 | ShiroiTree，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| PIONEER DVD-RW DVR-S21（PA01） | Windows，接口未报告 | DVD-R，标识 Verbatim、外包装 SOKCK，用户认为可能是假冒盘，真伪不明（MID `MCC 03RG20`，内圈 `111102-S1`），随机数据 | `fua` | CAV，约 4747 rpm（`--speed 22160`，16x） | 0.54–0.70°（19–25 µs） | `geo` 22 级跑通，恒定轨距 rms 0.188°，chi2/dof 0.97。同一张图用 `image` 生成的 ISO 和 DIS（16x CAV，直接填 disc-probe 的预设）各刻一张，都没有可见偏差，DIS 那张可能略有缩放（用户反馈，无量化图像误差）。此前 DIS 粗标和边界各三次，精细标定没有出线 RiDATA（和 UJ272 那行同一盒）直接用 domerawind 的预设，16x 刻标线，又竖又直（用户反馈）。DIS 1.4.1、1.4.2 在 UJ272 和这台上封盘都报失败，但图像完整，当时预设里的扇区数是 2298496，比空白盘可写的多（同款 RITEKF1 空盘在 GH70N 上 `info` 报 2297888）。UJ272 换成 2295104 后封盘正常，这台还没有重刻的结果。[DIS #183](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183#issuecomment-6691519009) 查明多出的 608 扇区是收尾要用的边界开销（TBO 592 加 BSGA 16），`RITEKF1` 上按 2297888 重新拟合的预设[封盘正常](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183#issuecomment-6690200194)（UJ272 那行的报告）。 `--speed 5540` 能降到约 2354 rpm。 | Lakida0，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19434982) |
| HL-DT-ST SP80NB80（RC00） | Windows | Verbatim DVD-R AZO 95101 2201-203（MID `MCC 03RG20`），随机数据 | `fua` | 约 1432 rpm（`--speed 3324`） | 未报告 | `geo` 跑通，恒定轨距 rms 0.43°，chi2/dof 4.79，二次轨距 0.33°、2.95。再用 DIS 精细标定，一共刻了 5 张盘后图案对上了（用户反馈，无量化图像误差）。读 `CMC MAG. AM3` 时同一台光驱噪声太大，见上一条记录 | Sliicy，[DIS #171](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171) |
| HL-DT-ST BD-RE WH14NS40（1.02） | SATA / Windows | Verbatim DVD-R AZO 95101 2201-203，随机数据 | `fua` | 重新放盘后 CAV，约 9280 rpm；`--speed 1411`、`3324`、`5540` 都是 CLV，之后不加 `--speed` 也还是 CLV，重新放盘才恢复 | 0.22–0.49°（3.9–8.9 µs） | `geo` 约 18 分钟后停下，6 个点只覆盖 42.3–42.8 mm，rms 0.47°，chi2/dof 6.58，不能用 | sanitysama，[#171](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171#issuecomment-6701560294) |
| HL-DT-ST GHB0N（JE01） | SATA / Linux（bczhc 的移植版） | Banana 蓝色 DVD-R GSD-B-401（MID `MCC 03RG20`，内圈 `111102-S1`），随机数据 | `fua` | CAV，2361 rpm（`--speed 5540`） | 0.54–0.56°（38–39 µs） | `geo` 跑通，恒定轨距 rms 0.176°，chi2/dof 0.90。和 Lakida0 用先锋 DVR-S21 测的同 MID、同内圈编码的盘相差约 0.05° rms（峰峰 0.17°）。用户看到细微曲折后手调参数，刻出的径向线更直（目测）；手调结果和 `geo` 相差约 0.08° rms，小于测量不确定度 | dhao2001，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19438546) |
| TSSTcorp CDDVDW SN-208FB（CH00） | Windows，接口未报告 | 铼德 e 时代 DVD-R（MID `RITEKF1`，PW104），用另一台光驱写的随机数据 | `fua` | CAV，约 2351 rpm（`--speed 5540`） | 0.48–0.58° | `geo` 22 级跑通，rms 0.097°，chi2/dof 0.27；请求 8x 时 0.129°、0.49，两次相差约 0.03° rms。和本仓库 GH70N 的 Ritek F1 相差约 0.05° rms（峰峰 0.17°）。同一种盘刻普通数据多次成功，最高 8x（用户反馈），但刻图案失败：RITEKF1 用 DIS 流式和 ISO 刻了四张，约 0.3 MB 处失败；RiDATA 4x 约 284 MiB、另一种 DVD 4x 约 270 MB 处失败（`0xC0AA0301`）。其中 RiDATA 和那种 DVD 在先锋上能刻 | Lakida0，[#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19435910) |

</details>

Linux 版由 bczhc 移植：[bczhc/disc-probe](https://github.com/bczhc/disc-probe)（见其中的 `README-linux.md`）。macOS 版由 NaiveTomcat 移植：[NaiveTomcat/discprobe-macos](https://github.com/NaiveTomcat/discprobe-macos)（GPL-3.0-or-later），发布包里带签名、公证过的通用 helper，不需要编译。

## 手动使用

<details>
<summary>下一步提示、盘符、结果路径、常用参数、Tab 补全、语言和小游戏</summary>

这些提示、进度和动画只在标准输出是终端时出现。管道、重定向和脚本调用得到的输出基本和以前一样，结果文件的格式也没变。在终端里想关掉它们，设 `DISCPROBE_PLAIN=1`。

- 下一步跑什么：`guide` 列出做过的步骤并打印下一条命令，不碰光驱。不带参数运行 `python -m discprobe` 也是它。`info`、`timing`、`geo`、`random`、`image`、`disexport` 跑完也会打印下一步。`timing` 还会给判定：不是 CAV 就换速度，抖动大于约 2° 建议换个速度，大于约 5° 说明这台光驱很可能不适合（这两个门槛来自实践报告表，不是严格界限）。
- 盘符：`list` 列出光驱。在终端里可以不写 `--drive`，只有一台就直接用，有多台就问你。
- 结果路径：`--geo` 还接受结果文件夹、`latest` 和 `pick`（手动选）。`results --pick` 按盘和光驱分组，再按精度或日期排序。`latest` 会跳过模拟驱动器的结果和中途停下的结果。现在的结果会标明自己提前停止了；之前版本留下的结果只能按少于 8 级或 χ²/dof 超过 25 判断，8 级以上中途停下的分辨不出来。`results geo` 列出做过的测量，`results geo --latest` 只打印一行路径，方便写脚本。
- `--sectors` 有三个意思：`timing`、`geo` 里是每次读几个扇区，`16` 读一个完整的 DVD ECC 块；`random` 里是刻多少；`disexport` 里是盘的容量，DiscImageStudio 里也填同一个数。`info` 会打印建议值和来源，以空白盘上的为准。
- `--speed` 可以写 kB/s，也可以写倍速，如 `4x`（按 `--media` 的 1x 换算）。DVD：`2.4x` = 3324，`4x` = 5540（`geo` 默认），`8x` = 11080。CD：`8x` = 1411（默认），`16x` = 2822，`24x` = 4234。低速通常噪声更小，但不是每台光驱都会换档，要看 `timing` 打印的转速。
- `--ranges` 接受扇区范围 `a-b,c-d`，默认的已刻录区 3–85% 适合大多数盘。`geo` 总在同一处停下，或者外圈有换速跳变时，把那段排除。最后一个扇区看 `info`。
- CD 和 DVD：步骤相同，每条命令加 `--media cd`。终端里如果盘是 CD、命令却是 DVD 设置，会先问要不要加；托盘是空的也会直接说。
- 中途出事：测量时开仓、盘被取出或换过，`timing` 和 `geo` 会立刻停下并说明原因，退出码 1。已测的部分会保留并标明提前停止，`--geo latest` 不会用它。写镜像被中断时，没写完的文件会被删除；如果是关窗口这种来不及清理的情况，`guide` 也不会把它当成写好了。
- Tab 补全：`python -m discprobe completion install` 支持 PowerShell、bash 和 zsh。它在主目录写一个脚本，并在 shell 的启动文件里加一行，`completion uninstall` 会把两者都删掉。当前窗口要新开或运行它打印的那一行才生效。在 PowerShell 上，`discprobe` 这一行按 Tab 会弹出列表，其他命令的 Tab 不变。按 Tab 不启动 Python，所以更新后要再装一次。
- 语言：在终端里跟随系统语言。用 `--lang zh`、`--lang en` 或 `DISCPROBE_LANG=zh` 指定。管道、重定向和 `DISCPROBE_PLAIN=1` 始终是英文，只有命令里写了 `--lang` 才变。结果文件不翻译。
- 进度：`timing`、`geo` 和写 ISO 时显示同样的状态行。窗口窄时依次省掉部分内容，不会折行。按 Ctrl+C 会保留已测的部分并说明位置。
- 小游戏：测量时按 `g` 打开贪吃蛇，方向键或 WASD 转向，`r` 再来一局，`q` 关闭。按 `n` 换成“刻满”：方块从右边飞进来往左堆，上下移动，右键旋转，左键快落，排满一列就消掉。测量输出照常打印在它上方。不按 `g` 就没有这些，管道、`DISCPROBE_PLAIN=1` 和 `--no-animation` 下也不会出现。

进度行和小游戏都没有后台线程，因为后台线程可能拖后完成时间戳。它们在主线程里，趁每次计时读之前的随机等待来画，花掉的时间从等待里扣。在模拟驱动器上，相同种子下加不加这些，`summary` 和事件逐条相同。动画每秒最多 8 帧，和之前的进度行一样，但带颜色时每帧写的字节更多。`timing` 比较过旧进度行：有无它的差别（0.01–0.20°）和重复测量的差别（0.02–0.23°）相同。新动画、贪吃蛇和 `geo` 还没在真实光驱上比较过，介意的话加 `--no-animation`，或者用管道跑，重要的测量也别玩贪吃蛇。

`timing` 和 `geo` 测量时会把进程调到高优先级。2026-11-06 之前这一步在 64 位 Python 上一直失败，所以之前用 64 位 Python 跑的真实测量都是普通优先级，上面的比较也是。实践报告表里用这个工具在 Windows 上测的数据多半也是，移植版和别的探针不一定。高优先级对抖动的影响还没有比较过。

默认全用 7 位 ASCII，不受代码页和字体影响，`DISCPROBE_UNICODE=1` 可以换成更细的图形。`NO_COLOR` 只关颜色；`--no-animation`、`DISCPROBE_NO_ANIMATION=1` 和 `CI` 关动画。转动的小光盘只是装饰，不代表实际转速。详见[手册](docs/MANUAL.md#手动使用)。

</details>

## 另一种用法：计时加图像法精修

计时结果不够完美时，也可以只用它把参数带到足够接近，再用 DiscImageStudio 的图像法精修。pugod124 之前试了约 15 张 CD 都刻不好，这样做之后成功出图，详见 [disc-probe #2](https://github.com/Ashley-QwQ/disc-probe/issues/2#issuecomment-6650565706)。

<img src="docs/showcase/pugod124_cd.jpg" width="60%" alt="pugod124 的 CD-R：先用 geo，再用 DiscImageStudio 精修后刻出的图案">

*pugod124 用这种方法刻的 Memorex CD-R，已裁到盘面。*

## 局限

同一个 MID 的盘几何也可能不同：两张 `CMC MAG. AM3` 的轨距差约 0.7%。所以别人的预设不一定能用，要量自己这批。

光驱之间差别很大。转速不是 CAV，或者抖动太大（比如 200 µs）的光驱，测出的几何可能不能用，先跑 `timing` 看结果。

高转速读外圈可能出现假象。GH70N 在 3226 rpm 读 CD 时，49.8 mm 以外的完成时刻会晚约 0.2 ms，会被误读成几何，降速后就消失了。

我们自己刻图只在 GH70N 上做过，其他光驱的结果来自计时对比和少数用户的刻盘。

CD 的沿轨道常数要靠网格盘来定，206 帧只对 GH70N 加 IMAPI 刻录、READ(12) 读取这条路径成立。CMC CD-R 在约 33 mm 处还有约 0.4° 的落差，可能是刻录时的接缝，正在核对。

`geo` 目前只支持 DVD 和 CD，蓝光盘只能跑 `timing`。

## 安全

光驱部分只发送读类命令。[`discprobe/scsi.py`](discprobe/scsi.py) 里有一份白名单，白名单之外的操作码在到达设备前就被拒绝，self-test 会验证 WRITE、CLOSE TRACK、FORMAT UNIT 确实被拒。唯一会改变驱动器状态的命令是 `SET CD SPEED`，只在你传 `--speed` 或 `--cav` 时才发送。刻录由 Windows 自带的刻录功能完成，只有 [`tools/burn_imapi.ps1`](tools/burn_imapi.ps1) 加 `-Burn` 时才会写盘。

## 文档

| 文档 | 内容 |
|---|---|
| [使用手册](docs/MANUAL.md) | 每个命令的原理、参数、输出和自检结果，包括辐条盘、纹理环盘、多假设标定盘和 CD |
| [知识汇总](docs/KNOWLEDGE.md) | 方法原理、硬件实测、踩过的坑和结论 |
| [CD 物理模型](docs/CD_PHYSICAL_MODEL.md) | CD 的实现和时序假设 |
| [作品照片](docs/showcase/README.md) | 每张照片对应的盘和刻录方式 |
| [`evidence/`](evidence/README.md) | 原始测量数据和图，可复现 |
| [dis-cd-timing](https://github.com/WindowsNoEditor/disc-probe/tree/dis-cd-timing/contrib/dis-cd-timing) | WindowsNoEditor 的 C# 探测程序、拟合脚本和原始数据（在他们的 fork 里） |

## 前人工作与致谢

用读取计时测扇区角度，并不是这里首创：

- 光盘防拷里的 DPM（Data Position Measurement），SecuROM 4 及以后的版本都在用；
- redump 论坛 2025 年讨论过用 FUA 反复重读同一扇区来测一整圈的时间；
- 飞利浦专利 US7538787B2《在光盘上写入标签的方法》（优先权 2002 年，2017 年失效）已经描述了同样的思路用于在数据区刻可见标签：记录 ECC 块读完的时间戳、用重复读取求转动周期、跳跃距离逐轮加倍。

本仓库做的是：在普通消费级光驱上可复现的开源实现，处理实机的各种问题，用协方差驱动的逐级测量加不确定度估计，做实盘网格验证和跨盘修正，并能导出 DiscImageStudio 预设。

数据面刻图的编码参考了 [DiscImageStudio](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio)，`discprobe/efmplus.py` 移植自它。感谢 NaiveTomcat 和 bczhc 的移植，也感谢报告实测结果的 anyezhixie、bczhc、Disappear9、domerawind、FanJZSS、kasumikira、Lakida0、li-yifei、MasterMT9、moodyos、NaiveTomcat、NO-ob、pugod124、ShiroiTree、Sliicy、WindowsNoEditor 和 zhajial。

## 许可

Copyright (C) 2026 Ashley-QwQ

本程序是自由软件：你可以按照自由软件基金会发布的 GNU 通用公共许可证（第 3 版，或任何更新的版本）重新发布和修改它。发布本程序是希望它有用，但不提供任何担保，包括适销性或特定用途适用性的隐含担保。详见 [LICENSE](LICENSE)。SPDX：`GPL-3.0-or-later`。
