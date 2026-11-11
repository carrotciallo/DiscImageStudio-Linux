# 论文提纲（草稿）：用普通 DVD 刻录机在数据面"写"出图像

**状态：**提纲和证据清单，2026-11-04。正文等颜色对照表（LUT）和至少第二台光驱的验证完成后再写。语言待定（中文或英文）；英文标题备选如下。

- *Drawing with data: calibrated, multi-colour images on the data side of stock DVD-R discs*
- *Your burner is a plotter: timing-calibrated geometry, texture contrast and structural colour on DVD-R*

## 摘要要点（一段话）

普通 DVD 刻录机只接受用户数据，但通过选择字节，可以控制盘面上坑与岸的纹理。我们要解决三个问题：
1. **把图放对位置**：只用光驱读取的完成时刻来测量盘面螺旋几何，第一次刻录的角度误差约为 0.1° 峰峰值（rms 0.03°），并做了预先登记的检验；
2. **让图看得见**：刻录机的 DSV 控制使大面积的覆盖率被钉在 50%，可见对比来自游程长度和观察几何；
3. **做出颜色**：把沿轨周期纹理当作衍射光栅，在同一视角下得到多种结构色，并建立"纹理 × 观察几何 → 颜色"的对照表。

全部工具开源（GPL-3.0-or-later），实测光驱为一台 GH70N。

## 章节与证据

| # | 章节 | 主张 | 证据（仓库内） | 状态 |
|---|---|---|---|---|
| 1 | 引言 | 现有做法（DiscImageStudio、CDImage、DiscT@2、LabelFlash）及其标定的痛点 | KNOWLEDGE §8、§10b、§10c；DIS issues #40/#49/#65/#71 | 有 |
| 2 | 背景：DVD 编码链 | 字节 → 扰码 → ECC → EFMPlus/DSV → NRZI；可控与不可控部分 | `discprobe/dvd.py`、`efmplus.py`；KNOWLEDGE §2 | 有 |
| 3 | 几何：读取计时标定 | 相位模型、梯子算法、驱动怪癖（缓存、FUA、整圈重读、变速） | `discprobe/timing.py`、`geo.py`；KNOWLEDGE §6 | 有 |
| 3.1 | 验证 | 预先登记复测 D = 0.082°（0.73σ）；网格盘 3 峰峰值 0.106°、rms 0.032°；与社区标定 #53 相差 0.08° | `docs/PREREG_remeasure.md`、`evidence/geo`、`evidence/gridscan` | 有 |
| 3.2 | 前人工作 | DPM、redump 2025、Philips US7538787B2（同一思路，用于写标签） | KNOWLEDGE §10c | 有 |
| 4 | 对比度的物理 | DSV 把覆盖率钉在 50%（模拟里连最优贪心也只有 0.500）；对比来自游程类 | `evidence/coverage/greedy_coverage*` | 有 |
| 4.1 | 观察几何 | 零级亮场或暗场下整张盘都可见；"披萨片"是导槽的一级衍射（≥ 31°） | KNOWLEDGE §10（E0）；照片（未入库） | 定性；**缺定量反差测量** |
| 4.2 | 分辨率 | 肉眼可见约 0.1–0.15 mm；600 dpi 扫描可分辨 0.12 mm | KNOWLEDGE §10（密铺盘） | 有；**缺显微或微距的定量数据** |
| 5 | 结构色 | 沿轨周期即光栅；纹理搜索；同视角多色（花盘）；无周期纹理降低饱和度 | §10d；`evidence/tilephoto`、`evidence/coverage/period_search_v2*` | 部分 |
| 5.1 | 颜色对照表 | 闪光灯几何下 δ = 2 c·t；LUT 靶盘 v2；重复字节 = 单线光栅（`92` 稳健符合；`66` 只有红端可靠；`B9` 不符合，已交外部研究）；跨轨不相干 | `tools/flash_lut_tiles.py`、`iso/lut2.iso`、`evidence/flash_lut/grating_check.*` | 部分（269 个观测，\|δ\| ≤ 0.62；还缺 0.6–0.8） |
| 5.2 | 斜拍解码 | 斜拍时椭圆中心 ≠ 圆心的像；用焦距反解圆的姿态，得到两个候选 | `discprobe/tilephoto.py`、`evidence/tilephoto/synth_photo_test.txt` | 完成（合成 6/6 情况 75/75） |
| 5.2 | 指定颜色的反向设计 | 给定观察几何，逐点选纹理，实刻验证 | — | **待做** |
| 6 | 成像流程 | 共形双环映射、文字补偿、降噪兼抗混叠、反锐化、抖动、阴刻/阳刻 | §10e；`docs/showcase/` | 有（作品） |
| 7 | 测量工具 | 自定位色板（差分编码）、扫描去条纹、照片单应（极线即消失线）、相机姿态 | `discprobe/tilescan.py`、`tilephoto.py`；§10f | 有 |
| 8 | 局限 | 一台光驱、一种盘；需要 CAV；全息做不到（要亚微米相位）；颜色随视角变 | KNOWLEDGE §9、§11 | 有 |
| 9 | 可复现性 | 命令、数据、预先登记、自检 | README、`evidence/README.md`、`selftest` | 有 |

## 写作前还缺的实验（按重要性）

1. **颜色对照表**：在 LUT 靶盘 v2 上拍闪光灯横移系列，得到 18 种纹理随 δ 变化的颜色；再按对照表刻一张"指定颜色"的图来验证。
2. **第二台光驱、第二种盘**：最好是一台不同芯片的光驱，加一种 AZO 染料盘（Verbatim），检验计时法和对比度结论是否通用。
3. **定量的可见度**：在固定光照下（iPad 白块，固定几何）拍纹理环盘，做平场除法，给出各纹理的零级反射率差。
4. **刻录速度**：4x 与 16x 对比（需要 ImgBurn）。
5. **外圈 54.4–58 mm** 的计时测量。
6. （可选）CD-R：EFM 和合并位的 DSV 更细，覆盖率被锁得更死；纹理与结构色是否同样成立。

## 图表清单（初稿）

- 编码链示意图；可控与不可控字节的比例。
- 梯子测量的残差图（`evidence/figures/ladder_residuals.png`）；三张网格盘的弯曲曲线（`bending_before_after.png`）。
- DSV 模拟：贪心最大化岸占比时的帧序列（`greedy_coverage_output.txt`）。
- 观察几何示意：导槽径向衍射与沿轨衍射的方向对比；零级亮场的光路。
- 色板图（`evidence/tilephoto/swatch_chart.png`）；四色花的特写；LUT 图（待测）。
- 作品：清明上河图（全盘、标题、内圈）、密铺盘（`docs/showcase/`）。

## 注意事项

- 清明上河图所用扫描的来源有使用条款，论文里只放实拍照片。人形等原创图形的作者是用户本人，是否收录由作者决定。
- 正文要明确说明：计时测角的原理不是首创（DPM、Philips 专利），我们的贡献在于实现、验证、对比度与颜色的研究，以及开源工具。
