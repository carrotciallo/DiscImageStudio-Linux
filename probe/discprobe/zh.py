"""The Chinese text of the command line: English wording -> Chinese wording.

A key with {name} parts matches a whole line with values in those places; each value is looked up
again, so messages compose. Written for someone using this for the first time: "rung" is 测量点,
"phase" is 盘面角度, and "CAV" is always glossed. A line with no entry simply stays English.
Developer output (selftest) stays English on purpose.
"""

TEXT = {
    # Terms that appear inside other messages
    "CAV": "恒定转速 (CAV)",
    "CLV": "恒定线速度 (CLV)",
    "unknown": "无法判断",
    "mixed (P-CAV / Z-CLV?)": "分段变速 (可能是 P-CAV 或 Z-CLV)",
    "the drive": "光驱",
    "none": "无",

    # Progress line
    "starting": "准备中",
    "reading the disc": "读取盘信息",
    "warming up": "预热光驱",
    "cache test": "检查光驱缓存",
    "waiting for a steady spindle": "等转速稳定",
    "rotation test, zone {a}/{b}": "转速测试，第 {a}/{b} 区",
    "phase test, target {a}/{b}": "盘面角度测试，第 {a}/{b} 个位置",
    "rung {a}/{b}: {stage}": "测量点 {a}/{b}：{stage}",
    "rung {a}/{b}": "测量点 {a}/{b}",
    "about {t} left": "还剩约 {t}",
    "Ctrl+C to stop": "Ctrl+C 停止",
    "{p} %   about {t} left": "{p} %   还剩约 {t}",
    "g: game": "按 g 玩游戏",
    "Snake {s}  best {b}  arrows or WASD steer, n next, q closes": "贪吃蛇 {s} 分  最高 {b}  方向键或 WASD 转向，n 换游戏，q 关闭",
    "Snake {s}  best {b}  crashed: r plays again, n next, q closes": "贪吃蛇 {s} 分  最高 {b}  撞上了：r 再来一局，n 换游戏，q 关闭",
    "Snake: best score {n}": "贪吃蛇最高 {n} 分",
    "Fill the Disc {s}  best {b}  up/down, right spin, left drop, n next, q closes": "刻满 {s} 分  最高 {b}  上下移动，右键旋转，左键快落，n 换游戏，q 关闭",
    "Fill the Disc {s}  best {b}  disc full: r plays again, n next, q closes": "刻满 {s} 分  最高 {b}  盘满了：r 再来一局，n 换游戏，q 关闭",
    "Fill the Disc: best score {n}": "刻满最高 {n} 分",
    "The window is too small for the game": "窗口太小，放不下游戏",
    "Finished in {t}": "用时 {t}",
    "writing the image": "正在写镜像",
    "read timing -> disc geometry -> pictures on discs": "读取计时 -> 盘面螺旋几何 -> 把图片刻到盘上",

    # Measuring
    "Measuring on {d}. Ctrl+C stops and keeps what was measured.{limit}": "正在用 {d} 测量。按 Ctrl+C 可停止，已测的数据会保留。{limit}",
    "Measuring on {d}. Ctrl+C stops and keeps what was measured. It gives up after {m} minutes.":
        "正在用 {d} 测量。按 Ctrl+C 可停止，已测的数据会保留。超过 {m} 分钟会自动放弃。",
    "Disc: {p}, last LBA {l}, reading with {m}": "光盘：{p}，最后扇区号 {l}，读取命令 {m}",
    "Cache: {c} -> strategy {s}": "缓存测试耗时：{c}，采用的读取方式 {s}",
    "Spindle steady: T = {t} ms ({r} rpm)": "转速已稳定：转一圈 {t} ms（{r} 转/分）",
    "Spindle did not reach a steady speed; expect noisy results": "转速一直没稳定，结果可能噪声较大",
    "Zone {f} (LBA {l}): T = {t} ms ({r} rpm), jitter {u} us = {d} deg, coherence {c}":
        "位置 {f}（扇区号 {l}）：转一圈 {t} ms（{r} 转/分），抖动 {u} µs = {d}°，周期清晰度 {c}",
    "Zone {f} (LBA {l}): no period found": "位置 {f}（扇区号 {l}）：没找到转动周期",
    "Rotation: {m} ({r})": "转速方式：{m}（{r}）",
    "Rotation: {m}": "转速方式：{m}",
    "zones {z} have no clear period; the speed may be changing, try a fixed --speed":
        "位置 {z} 没有清晰的周期，转速可能还在变化，试试用 --speed 固定速度",
    "fewer than two zones with a clear period": "周期清晰的位置不足两个",
    "Warning: a FUA read takes {t} turns of this period, not a whole number, {rest}":
        "警告：一次绕过缓存的读取用了这个周期的 {t} 圈，不是整数圈，{rest}",
    "Warning: this period looks like the Windows timer tick (15.625 ms), not the spindle":
        "警告：这个周期像是 Windows 的定时器 (15.625 ms)，不是光盘转动",
    "Target {f} (LBA {x}): phase {m} deg +/- {s} (single-shot std {d}, n={n}), ref jitter {j} deg":
        "位置 {f}（扇区号 {x}）：盘面角度 {m}° ± {s}（单次标准差 {d}，{n} 次），基准抖动 {j}°",
    "Target {f}: not enough usable reads": "位置 {f}：可用的读取次数不够",
    "Warning: drive did not look CAV; phase values are not disc angles.":
        "警告：这台光驱看起来不是恒定转速，这些数值不代表盘面角度。",
    "Rotation is {m}, not CAV, so the phase test would not give disc angles; skipping it. Try another --speed, or pass --force to run it anyway.":
        "转速方式是 {m}，不是恒定转速，测不出盘面角度，所以跳过这一步。换一个 --speed 试试，或加 --force 强制测量。",
    "reads keep failing with medium errors ({s}): the drive cannot read this disc reliably. Picture, calibration and texture discs often behave like this. Timing needs plain data: burn a random-data disc from the same batch (python -m discprobe random) and measure that.":
        "读取一直报介质错误（{s}）：光驱读不稳这张盘。刻了图案、标定图或纹理的盘经常这样。测量需要普通数据盘：用同一批盘刻一张随机数据盘（python -m discprobe random），再测那张。",
    "stopped after the {m} minute time limit (--max-minutes); reads are far slower than expected":
        "到了 {m} 分钟的时间上限（--max-minutes）后停止；读取比预期慢很多",
    "--media cd requires a CD-ROM Mode 1 data track and READ(12)/READ(10), not READ CD":
        "--media cd 需要 CD-ROM Mode 1 数据轨，并能用 READ(12)/READ(10) 读取，不支持 READ CD",
    "no readable recorded area; burn a test disc first (blank media has nothing to read)":
        "没有可读的已刻录区域；请先刻一张测试盘（空白盘没有东西可读）",
    "{m} fails on this disc ({s})": "{m} 读不了这张盘（{s}）",
    "Spindle settled: T = {t} ms ({r} rpm), jitter {j} us": "转速已稳定：转一圈 {t} ms（{r} 转/分），抖动 {j} µs",
    "the spindle speed never settled; is the read speed fixed (--speed)?": "转速一直没稳定；读取速度固定了吗（--speed）？",
    "LBA {l}: spindle unsteady or reads failing; settling and retrying": "扇区号 {l}：转速不稳或读取失败，等稳定后重试",
    "warning: cache strategy {s}; phases will be noisier": "警告：读取方式为 {s}，角度噪声会大一些",
    "no readable {m} ranges longer than 64 sectors": "没有超过 64 个扇区的可读 {m} 区域",
    "Reference LBA {r}; readable ranges {x}": "基准扇区号 {r}；可读范围 {x}",
    "no room for a rung {t} turns from the reference": "距基准 {t} 圈的地方放不下测量点",
    "could not measure LBA {l} near the reference": "基准附近的扇区 {l} 测不出来",
    "rung {n}: LBA {l} ({t} turns) phase {p} +/- {s} deg": "测量点 {n}：扇区号 {l}（{t} 圈）角度 {p} ± {s}°",
    "rung {n}: LBA {l} predicted +/- {p} deg, whole turns {w}, residual {r} deg, chi2/dof {c}":
        "测量点 {n}：扇区号 {l}  预测误差 ± {p}°，整圈数 {w}，残差 {r}°，拟合误差比 {c}",
    "LBA {l}: skipped (no stable measurement)": "扇区号 {l}：跳过（测不稳）",
    "no CD rung is within the safe 25-degree prediction limit": "没有测量点落在 25° 的安全预测范围内",
    "after the rung at LBA {l}: chi2/dof {c}, worst residual {w} deg; a whole-turn count is probably wrong, so the fit was stopped":
        "测完扇区 {l} 这个测量点后：拟合误差比 {c}，最大残差 {w}°；很可能数错了整圈数，所以停止拟合",
    "stopped: {e}": "已停止：{e}",
    "u = r0/b = {u}, v = p/b = {v}  (chi2/dof {c}, residual rms {r} deg)": "u = r0/b = {u}，v = p/b = {v}（拟合误差比 {c}，残差 rms {r}°）",
    "With bit length {b} nm: r0 {r} mm, pitch {p} um": "按位长 {b} nm 算：起始半径 {r} mm，轨距 {p} µm",
    "Angle uncertainty across the measured span {a}-{b} mm: {c} deg (1 sigma); across {d}-58 mm: {e} deg":
        "角度不确定度：实测范围 {a}-{b} mm 内 {c}°（1 sigma）；{d}-58 mm 内 {e}°",
    "The constant-pitch fit leaves more than noise. See whether a varying pitch fits better: {c}":
        "按恒定轨距拟合后，剩下的误差比噪声大。看看可变轨距是否更合适：{c}",
    "targets.csv, summary.json, events.csv: {p}": "targets.csv、summary.json、events.csv 保存在：{p}",
    "no results written: it stopped before the first fit. Run `timing` to see how noisy this drive is.":
        "没有写入结果：在第一次拟合前就停了。运行 `timing` 看看这台光驱噪声有多大。",
    "Raw events and summary: {p}": "原始事件和汇总保存在：{p}",
    "Full dump: {p}": "完整信息保存在：{p}",
    "note: SPTI was refused (not elevated); using the IMAPI2 transport instead": "提示：SPTI 被拒绝（没有管理员权限），改用 IMAPI2 通道",
    "note: could not raise process priority": "提示：无法提高进程优先级",

    # info
    "Drive: {a} rev {b}": "光驱：{a}，固件 {b}",
    "Current profile: {a}": "当前盘型：{a}",
    "Disc status: {a}, sessions {b}, erasable {c}": "光盘状态：{a}，会话数 {b}，可擦写 {c}",
    "Readable capacity: last LBA {a} x {b} B": "可读容量：最后扇区号 {a}，每扇区 {b} 字节",
    "ATIP: {a}, lead-in start {b} (manufacturer code), last lead-out start {c} = LBA {d}":
        "ATIP：{a}，导入区起点 {b}（厂商代码），最后导出区起点 {c} = 扇区号 {d}",
    "DVD physical: {a}": "DVD 物理信息：{a}",
    "DVD-R MID: {a}": "DVD-R 厂商代码 (MID)：{a}",
    "DVD-R pre-recorded text: {a}": "DVD-R 预刻文字：{a}",
    "DVD+R MID: {a}": "DVD+R 厂商代码 (MID)：{a}",
    "Read perf: LBA {a}..{b}  {c} -> {d} kB/s (ratio {e})": "读取速度：扇区 {a}..{b}  {c} -> {d} kB/s（比值 {e}）",
    "Write perf: LBA {a}..{b}  {c} -> {d} kB/s (ratio {e})": "写入速度：扇区 {a}..{b}  {c} -> {d} kB/s（比值 {e}）",
    "Write speed descriptor: read {a} / write {b} kB/s to LBA {c}": "写入速度档：读 {a} / 写 {b} kB/s，到扇区 {c}",
    "Page 2A: buffer {a} kB, rotation {b}, write speeds {c}": "Page 2A：缓存 {a} kB，写入时转速方式 {b}，写入速度 {c}",
    "Not available on this drive/disc: {a}": "这台光驱或这张盘不支持：{a}",

    # Advice after a command (guide.py)
    "Plug the drive in and check that it shows up in Explorer,": "接上光驱，确认它在资源管理器里能看到，",
    "or try the flow on the simulated drive: {c}": "或者先用模拟光驱走一遍流程：{c}",
    "Next, see what the drive and disc report:": "下一步，看看光驱和盘的信息：",
    "With several drives, use the letter of the one holding your disc.": "有多台光驱时，用放了盘的那台的盘符。",
    "Sector count for disexport --sectors: {a} ({b}).": "disexport --sectors 要填的扇区数：{a}（{b}）。",
    "Enter the same number in DiscImageStudio. A blank disc's `info` is the count to go by: one user found read-from-disc there too high.":
        "DiscImageStudio 里也填这个数。以空白盘上 `info` 的数为准：有用户发现它的“从光盘读取”给的数偏大。",
    "free space of this blank disc": "这张空白盘的剩余空间",
    "lead-out in the ATIP; `info` on a blank disc gives a closer count": "ATIP 里的导出区起点；对空白盘运行 `info` 给的数更准",
    "last LBA + 1, the blank size only if this disc was burned full": "最后扇区号 + 1，只有整张刻满时才等于空白盘容量",
    "Nothing is recorded on this disc, so timing cannot use it. Burn a random-data disc first:": "这张盘上没有数据，timing 用不了。先刻一张随机数据盘：",
    "Nothing is recorded on this disc, so timing cannot use it. The usual random disc would not fit, so make a smaller one:": "这张盘上没有数据，timing 用不了。默认大小的随机数据盘放不下，做一张小一点的：",
    "The Blu-ray drives reported so far kept a constant linear speed whatever was asked, so another speed may not change this. To try one:": "目前报告过的蓝光光驱，请求什么速度都保持恒定线速度，所以换速度可能没用。想试的话：",
    "geo supports DVD and CD, so timing is as far as this disc goes for now.": "geo 只支持 DVD 和 CD，这张盘目前只能测到 timing。",
    "This is a Blu-ray disc, so {a}x is {b} kB/s": "这是蓝光盘，{a}x 是 {b} kB/s",
    "The middle of a CD holds its file system, so the picture is left out inside 26 mm radius.": "CD 中间放着文件系统，所以半径 26 mm 以内不画图。",
    "ISO 9660 sectors overlap the drawing; leave an inner background margin": "图案压到了文件系统的扇区上；请把半径 26 mm 以内留空",
    "On the CD route you can skip --along-track-frames: fine calibration in DiscImageStudio settles that constant.": "走 CD 路线可以不管 --along-track-frames：DiscImageStudio 的精细标定会定下这个常数。",
    "Next, check the drive (1 to 3 minutes):": "下一步，检查这台光驱能不能测量（1 到 3 分钟）：",
    "Verdict: rotation is {m}, not CAV, so sector angles cannot be read at this speed.": "结论：转速方式是 {m}，不是恒定转速，这个速度下读不出扇区在盘面上的角度。",
    "Next, try another speed. Some drives never leave one, and the rotation test will show that:": "下一步，换个速度试试。有些光驱只有一个速度，转速测试会显示出来：",
    "Verdict: rotation is CAV, but no jitter was measured.": "结论：转速恒定，但没有测到抖动。",
    "Verdict: CAV with {s} jitter. This drive looks usable.": "结论：转速恒定，抖动 {s}。这台光驱看起来可以用。",
    "Verdict: CAV, but {s} jitter is noisy. Another speed may help:": "结论：转速恒定，但抖动 {s} 偏大。换个速度可能好一些：",
    "Verdict: CAV, but {s} jitter is too high: drives reported at this level stopped early or gave a wrong geometry. Try another speed or another drive:":
        "结论：转速恒定，但抖动 {s} 太大：报告过这个水平的光驱都中途停下或测错了。换个速度或换台光驱：",
    "{a}-{b} deg": "{a}-{b}°",
    "Or read whole ECC blocks, which was cleaner on one drive: {c}": "或者每次读一个完整的 ECC 块（16 扇区），在一台光驱上更干净：{c}",
    "Next, measure the geometry:": "下一步，测量盘面螺旋几何：",
    "Make a plain data disc: {c}": "做一张普通数据盘：{c}",
    "Burn it (Windows: right-click the .iso, Burn disc image) and run timing on it.": "刻录它（Windows：右键 .iso，选“刻录光盘映像”），然后对这张盘运行 timing。",
    "This was the simulated drive: the verdict and commands below show the flow, do not burn from them.": "这是模拟光驱的结果：下面的结论和命令只用来演示流程，不要拿它刻盘。",
    "Verdict: good. Only noise is left after the fit, and {a} deg is about {b} mm at 50 mm radius.":
        "结论：可以用。拟合后只剩噪声，{a}° 在 50 mm 半径处约 {b} mm。",
    "Verdict: not settled. More than noise is left, and the comparison below could not run here.":
        "结论：还不能确定。剩下的误差比噪声大，下面的比较这里跑不了，要你手动跑。",
    "Verdict: usable, but noisy: {a} deg is about {b} mm at 50 mm radius.": "结论：能用，但噪声偏大：{a}° 在 50 mm 半径处约 {b} mm。",
    "Verdict: too noisy to rely on: {a} deg is about {b} mm at 50 mm radius.": "结论：噪声太大，不能依赖这次结果：{a}° 在 50 mm 半径处约 {b} mm。",
    "Verdict: a correction helps, but it stays noisy: {a} deg is about {b} mm at 50 mm radius.": "结论：修正有帮助，但修正后噪声仍然偏大：{a}° 在 50 mm 半径处约 {b} mm。",
    "a lower speed": "降速",
    "a different speed": "换一个速度",
    "For a cleaner run, try {s} or another drive:": "想测得更干净，可以{s}，或者换一台光驱：",
    "A varying track pitch does not fit better (fit error ratio {a} -> {b}), so the extra scatter is probably read noise. Try {s} or another drive:":
        "改用可变轨距也没有更好（拟合误差比 {a} -> {b}），多半是读取噪声。{s}，或者换一台光驱：",
    "Verdict: good once corrected.": "结论：加上修正就可以用。",
    "Verdict: usable, but noisy.": "结论：能用，但噪声偏大。",
    "Next, export a DiscImageStudio preset. CD has one more constant that timing cannot see, and fine": "下一步，导出 DiscImageStudio 预设。CD 还有一个计时测不到的常数，",
    "calibration there settles it on one more blank disc (the CD route in README.md):": "在 DiscImageStudio 里做精细标定就能定下来，要再用一张空盘（见 README.md 的 CD 路线）：",
    "Or make a picture ISO now (replace my_picture.png); radial lines may come out twisted without that constant:": "或者现在就做图片镜像（把 my_picture.png 换成你的图片）；没有这个常数，径向线可能是扭的：",
    "CD still needs one more constant, so the preset below is the usual way on (the CD route in README.md). A picture ISO:": "CD 还差一个常数，通常走下面的预设（见 README.md 的 CD 路线）。图片镜像：",
    "This run only covers {a}-{b} mm, so angles outside that are extrapolated.": "这次只测到 {a}-{b} mm，范围外的角度是外推的。",
    "The fit left more than noise. Compare pitch models first, no new measurement needed; if quadratic is": "拟合后剩下的误差比噪声大。先比较轨距模型，不用重新测量；如果二次模型明显更好，",
    "clearly better, write a correction and add --correction correction.json to the commands below:": "就写一个修正文件，并在下面的命令里加上 --correction correction.json：",
    "Measured {n} points across {a}-{b} mm: angles known to about {s} deg, points {r} deg from the fit on average.":
        "测量完成：{n} 个测量点，覆盖 {a}-{b} mm。角度不确定度约 {s}°，测量点平均偏离拟合曲线 {r}°。",
    "A varying track pitch fits clearly better (fit error ratio {a} -> {b}). Write a correction first; the commands below use it:":
        "轨距有变化：改用可变轨距后拟合明显更好（拟合误差比 {a} -> {b}）。先生成修正文件，下面的命令会用到它：",
    "A varying track pitch does not fit better (fit error ratio {a} -> {b}), so the extra scatter is probably read noise. You can carry on. For a cleaner run, try {s}:":
        "偏差比噪声略大，但改用可变轨距也没有更好（拟合误差比 {a} -> {b}），多半是读取噪声，可以继续。想测得更干净，可以{s}再测一次：",
    "Next, make a picture ISO (replace my_picture.png with your image):": "下一步，把图片做成可刻录的镜像（把 my_picture.png 换成你的图片）：",
    "Enter the same --sectors in DiscImageStudio.": "DiscImageStudio 里也填同一个 --sectors。",
    "Or export a DiscImageStudio preset:": "或者导出 DiscImageStudio 预设：",
    "--sectors is from your last `info`: {a}": "--sectors 来自你上次的 `info`：{a}",
    "--sectors is how much was burned on the measured disc. A blank can hold more: `info` on a blank gives its count.": "--sectors 是所测这张盘刻了多少。空白盘可能放得更多，对空白盘运行 `info` 可以看到它的扇区数。",
    "run `info` on a blank disc to {verb} --sectors": "对空白盘运行 `info` 可以查到 --sectors",
    "The drive would not hold one speed. Check it with timing, then try geo at {s}:": "光驱保持不住一个速度。先用 timing 检查，再{s}跑 geo：",
    "USB slim drives are often too noisy here; an internal drive may simply work.": "USB 超薄光驱在这里常常噪声太大，换内置光驱可能直接就行。",
    "A whole-turn count went wrong, or the pitch varies more than the model allows. Try {s}:": "整圈数算错了，或者轨距的变化超出了模型范围。先{s}试试：",
    "If it keeps stopping near one LBA, leave that area out with --ranges a-b (see `geo -h`).": "如果总停在同一个扇区附近，用 --ranges a-b 避开那一段（见 `geo -h`）。",
    "A disc whose pitch varies can take a higher limit, for example --chi2-abort 100.": "轨距本来就有变化的盘，可以放宽上限，比如 --chi2-abort 100。",
    "--ranges has to overlap the recorded area. See the last LBA with:": "--ranges 要和已刻录区域有重叠。查看最后扇区号：",
    "geo needs a burned disc of plain data. Make one, burn it and run geo again:": "geo 需要一张刻好的普通数据盘。做一张、刻好，再运行 geo：",
    "See how noisy this drive is: {c}": "看看这台光驱噪声有多大：{c}",
    "Burn it onto a blank disc (Windows: right-click the .iso, Burn disc image), and keep some blanks of the same": "把它刻到空白盘上（Windows：右键 .iso，选“刻录光盘映像”），再留几张同一批的空白盘用来刻图。",
    "batch for pictures. If the burner says it does not fit, make a smaller one with --sectors.": "如果刻录软件说放不下，用 --sectors 做一张小一点的。",
    "Then check the drive with it (1 to 3 minutes):": "然后用这张盘检查光驱（1 到 3 分钟）：",
    "Next, check the angle difference above (well under 0.1 deg is fine), then enter the preset in DiscImageStudio": "下一步，看一下上面的角度差（远小于 0.1° 就行），然后把预设填进 DiscImageStudio",
    "(inner and outer radius, sectors, the three pitch terms). Steps: docs/MANUAL.md.": "（内外半径、扇区数、三个轨距项）。步骤见 docs/MANUAL.md。",
    "Next, see where you are: {c}": "下一步，看看进行到哪了：{c}",
    "Try --sectors {a} ({b}). Enter the same number in DiscImageStudio. `info` on a blank disc is the count to go by: one user found read-from-disc there too high.":
        "试试 --sectors {a}（{b}）。DiscImageStudio 里也填这个数。以空白盘上 `info` 的数为准：有用户发现它的“从光盘读取”给的数偏大。",
    "This repository drives real hardware on Windows only. Ports: Linux github.com/bczhc/disc-probe, macOS github.com/NaiveTomcat/discprobe-macos. Anything with --sim works here.":
        "这个仓库只在 Windows 上操作真实光驱。其他系统的移植版：Linux github.com/bczhc/disc-probe，macOS github.com/NaiveTomcat/discprobe-macos。带 --sim 的命令这里都能跑。",

    # guide
    "Burn {p} to a disc and load it, then check this drive (1 to 3 minutes):": "把 {p} 刻到盘上并放入光驱，然后检查这台光驱（1 到 3 分钟）：",
    "Next, check the preview: {p}": "下一步，先看预览图：{p}",
    "If it looks right, burn {p} to a blank disc from the batch you measured": "没问题的话，把 {p} 刻到测量用的同一批空盘上",
    "(Windows: right-click the .iso, Burn disc image).": "（Windows：右键 .iso，选“刻录光盘映像”）。",
    "This geometry came from the simulated drive, so it only shows the flow: do not burn this ISO.": "这个几何来自模拟光驱，只用来演示流程：不要刻这个镜像。",
    "This was the simulated drive, so the verdict below says nothing about your own drive.": "这是模拟光驱的结果，下面的结论和你自己的光驱无关。",
    "Those were only the checks that run without {p}. Install what is missing and run it again:": "刚才只跑了不需要 {p} 的检查。装上缺的依赖，再运行一次：",
    "no such file: {p}": "找不到文件：{p}",
    "Make the random-data disc: write this file, then burn it:": "做随机数据盘：先写出这个文件，再把它刻到盘上：",
    "Check that this drive can measure (1 to 3 minutes):": "检查这台光驱能不能测量（1 到 3 分钟）：",
    "This speed did not work; try another (1 to 3 minutes):": "这个速度不行，换一个再试（1 到 3 分钟）：",
    "Measure the disc's spiral (about 5 minutes):": "测量盘面螺旋几何（约 5 分钟）：",
    "Make a picture ISO (replace my_picture.png with your image):": "把图片做成可刻录的镜像（把 my_picture.png 换成你的图片）：",
    "Or export a preset for DiscImageStudio (enter the same --sectors there; `info` on a blank disc gives the count):": "或者导出 DiscImageStudio 预设（那边也填同一个 --sectors，这个数看空白盘上的 `info`）：",
    "Install the Python packages disc-probe uses:": "安装 disc-probe 用到的 Python 依赖：",
    "Try the flow on the simulated drive:": "用模拟光驱走一遍流程：",
    "Where you are, for {m} ({o}: {c}):": "{m} 的进度（要看 {o}：{c}）：",
    "Next:": "下一步：",
    "All commands: {a}    One command: {b}    Details: docs/MANUAL.md": "全部命令：{a}    单个命令：{b}    详细说明：docs/MANUAL.md",
    "Python packages": "Python 依赖",
    "Optical drive": "光驱",
    "Random-data disc": "随机数据盘",
    "Drive check (timing)": "光驱检查 (timing)",
    "Geometry (geo)": "盘面几何 (geo)",
    "{a} missing": "缺少 {a}",
    "none found": "没找到",
    "real drives need Windows or a port": "真实光驱需要 Windows 或移植版",
    "{a} written; burn it": "{a} 已生成，请刻录",
    "measured": "已测过",
    "not made yet": "还没做",
    "not run yet": "还没运行",
    "stopped before the first fit": "在第一次拟合前停止",
    "{n} rungs, rms {r} deg, chi2/dof {c}, {s} mm  (stopped early)": "{n} 个测量点，残差 {r}°，拟合误差比 {c}，{s} mm（提前停止）",
    "{n} rungs, rms {r} deg, chi2/dof {c}, {s} mm": "{n} 个测量点，残差 {r}°，拟合误差比 {c}，{s} mm",
    "stopped before the rotation test": "在转速测试前停止",
    "{m}, jitter {a}-{b} deg  (stopped early)": "{m}，抖动 {a}-{b}°（提前停止）",
    "{m}, jitter {a}-{b} deg": "{m}，抖动 {a}-{b}°",
    "{m}  (stopped early)": "{m}（提前停止）",
    "no results in {o}": "{o} 里没有结果",
    "no complete {k} result in {o}": "{o} 里没有完整的 {k} 结果",
    "... and {n} older (-n {m} shows all)": "……还有 {n} 个更早的（-n {m} 显示全部）",
    "Using the latest geo result: {p}": "使用最新的可靠 geo 结果：{p}",
    "Using the geo result you chose: {p}": "使用你选的 geo 结果：{p}",
    "It was judged too noisy to rely on, and there is nothing better. To see them all: python -m discprobe results --pick": "这次被判定噪声太大、不能依赖，也没有更好的结果。想看全部：python -m discprobe results --pick",
    "Left out {n} newer run(s) judged too noisy. To see them all: python -m discprobe results --pick": "跳过了 {n} 次判定噪声太大的较新结果。想看全部：python -m discprobe results --pick",
    "You chose: {p} ({d})": "你选的是：{p}（{d}）",
    "Use it with:": "这样使用：",
    "Nothing chosen.": "没有选择。",
    "There are no geo results to choose from in {o}. Run geo first.": "{o} 里还没有可选的 geo 结果。先运行 geo。",
    "--geo pick needs a terminal. Give a result's folder, or see them with: results --pick": "--geo pick 需要在终端里使用。请给出结果文件夹，或者用 results --pick 查看。",
    "Choose a disc (arrows move, Enter opens, q quits)": "选择盘（方向键移动，回车进入，q 退出）",
    "(s sort, r reverse, Enter chooses, left goes back, q quits)": "（s 换排序，r 反过来，回车选择，左键返回，q 退出）",
    "~ matched from an info run near the same time, as older results didn't record the disc": "~ 旧结果没有记录盘型，这是按时间相近的 info 记录匹配的",
    "Which number? Enter alone cancels: ": "选哪一个？输入序号，直接回车取消：",
    "runs": "次",
    "best": "最好",
    "points": "个点",
    "default": "默认",
    "good": "好",
    "usable": "能用",
    "too noisy": "噪声太大",
    "narrow span": "只测了一小段",
    "stopped early": "中途停下",
    "most precise first": "按精度：最好的在前",
    "least precise first": "按精度：最差的在前",
    "newest first": "按日期：最新的在前",
    "oldest first": "按日期：最早的在前",
    "print only the newest folder, skipping simulated runs, stopped geo runs and ones judged too noisy": "只显示最新的文件夹，跳过模拟的、中途停下的和判定噪声太大的 geo 结果",
    "choose a geo result: by disc and drive, then by precision or date": "选择 geo 结果：先按盘和光驱，再按精度或日期",
    "for --pick: what to sort by (default: precision)": "配合 --pick：按什么排序（默认：精度）",
    "for --pick: the other way round": "配合 --pick：反过来排",
    "--geo latest: only simulated or stopped runs were found in {o}. Run geo first, or give a summary.json path.":
        "--geo latest：{o} 里只有模拟的或中途停下的结果。先运行 geo，或者给出 summary.json 的路径。",
    "--geo latest: there is no geo result yet in {o}. Run geo first, or give a summary.json path.":
        "--geo latest：{o} 里还没有 geo 结果。先运行 geo，或者给出 summary.json 的路径。",

    # Errors and hints in the command line
    "no optical drive found; to try the flow without one, add --sim cav": "没找到光驱；想先走一遍流程，可以加 --sim cav",
    "Using the only optical drive, {d}": "只有一台光驱，使用 {d}",
    "Optical drives: {d}": "光驱：{d}",
    "Which drive? [{d}]": "用哪一台？[{d}]",
    "no drive chosen": "没有选择光驱",
    "give --drive E: (see `python -m discprobe list`) or --sim cav|clv|cav-nofua": "请给出 --drive E:（盘符见 `python -m discprobe list`）或 --sim cav|clv|cav-nofua",
    "expected a drive letter such as E:, got {d}": "需要盘符，比如 E:，收到的是 {d}",
    "{e} (see `python -m discprobe list`)": "{e}（盘符见 `python -m discprobe list`）",
    "{e}. Optical drives here: {d}": "{e}。这台电脑的光驱：{d}",
    "No disc in the drive, or the tray is open (burning ejects the disc when it finishes). Load the disc, wait a few seconds and run this again":
        "光驱里没有盘，或者托盘开着（刻完盘托盘会弹出）。把盘放好，等几秒再运行一次",
    "The drive says its tray is open (burning ejects the disc when it finishes). Load the disc, close the tray, wait a few seconds and run this again":
        "光驱报告托盘开着（刻完盘托盘会弹出）。把盘放好，关上托盘，等几秒再运行一次",
    "The drive says its tray is closed, but it finds no disc. If one is in there, wait a few seconds and run this again. If it keeps saying this, the drive can't read that disc: check it sits flat, label up, and is clean, or try another disc":
        "光驱报告托盘已关，但认不出盘。如果放了盘，等几秒再运行一次。一直这样的话，就是光驱读不了这张盘：看看盘是否放平、标签面朝上、盘面是否干净，或者换一张盘",
    "The drive is not ready yet, it may still be loading the disc. Wait a few seconds and run this again": "光驱还没准备好，可能正在读入盘。等几秒再运行一次",
    "The drive says the disc was changed during the run, so these measurements can't be combined. Run this again": "光驱说测量途中换过盘，前后的数据不能合在一起用。请重新运行一次",
    "It stopped early, so `--geo latest` won't use these. Don't burn from them.": "这次是提前停止的，所以 `--geo latest` 不会用它们。不要拿它们刻盘。",
    "The unfinished image was removed.": "没写完的镜像已删除。",
    "This is a CD, but the command has DVD settings. Add --media cd?": "这是 CD，但命令用的是 DVD 设置。要加上 --media cd 吗？",
    "Note: geo supports DVD and CD; on this BD only timing is known to work.": "提示：geo 支持 DVD 和 CD；这张 BD 目前只确认 timing 能用。",
    "no such geo result: {p}": "找不到这个 geo 结果：{p}",
    "Your last measurement is {p}.": "你上次的测量结果是 {p}。",
    "Use it with --geo latest.": "用 --geo latest 就能使用它。",
    "Run geo first, then use --geo latest.": "先运行 geo，再用 --geo latest。",
    "{p} is not the summary.json of a geo run (it has no geometry fit)": "{p} 不是 geo 结果的 summary.json（里面没有几何拟合）",
    "no optical drives found": "没找到光驱",
    "--ranges {r}: give LBA ranges as start-end, for example 70000-1900000 or 2000-90000,120000-356000":
        "--ranges {r}：请写成“起始扇区-结束扇区”，比如 70000-1900000 或 2000-90000,120000-356000",
    "CD image needs a CD geometry fit (media=cd); DVD fits must not be reused": "CD 镜像需要 CD 的几何拟合 (media=cd)，不能用 DVD 的结果",
    "--along-track-frames is for CD": "--along-track-frames 只用于 CD",
    "design must be {a} x {b} cells of {c} mm": "图案必须是 {a} x {b} 格，每格 {c} mm",
    "a label design (not boolean) needs --textures, one per label": "标签图案（非布尔）需要 --textures，每个标签一种纹理",
    "--media {m} does not match {g}, which measured a {t}": "--media {m} 和 {g} 不符，那次测的是 {t}",
    "A preset needs --sectors: the capacity of your disc (`info` prints it)": "预设需要 --sectors，也就是你这张盘的容量（`info` 会打印）",
    "Run `info` on a blank disc to get the count, and enter the same number in DiscImageStudio.": "对空白盘运行 `info` 可以查到这个数，DiscImageStudio 里也填这个数。",
    "CD tiles need a CD geometry fit (media=cd)": "CD 色块盘需要 CD 的几何拟合 (media=cd)",
    "{a} has no geometry fit": "{a} 里没有几何拟合",
    "Stopped by Ctrl+C.{k}": "已按 Ctrl+C 停止。{k}",
    "What was measured so far is in {p}": "已测的数据在 {p}",
    "this command needs {p}. Install what disc-probe uses with: {c}": "这条命令需要 {p}。安装 disc-probe 的依赖：{c}",
    "error: {e}": "出错：{e}",
    "--speed is {s} kB/s": "--speed 是 {s} kB/s",
    "Note: --speed is in kB/s, so {s} is very slow. For a multiple, write {s}x.": "提示：--speed 的单位是 kB/s，{s} 非常慢。想写倍速请用 {s}x。",
    "{t} is not a speed: give kB/s like 5540, or a multiple like 4x": "{t} 不是速度：请写 kB/s，比如 5540，或者倍速，比如 4x",
    "cannot open {d}: {e}": "打不开 {d}：{e}",
    "(run the terminal as Administrator, or use --transport imapi)": "（以管理员身份运行终端，或用 --transport imapi）",

    # argparse's own messages
    "{p}: error: {m}": "{p}：出错：{m}",
    "the following arguments are required: {a}": "缺少必需的参数：{a}",
    "unrecognized arguments: {a}": "不认识的参数：{a}",
    "argument {a}: {m}": "参数 {a}：{m}",
    "invalid choice: {v} (choose from {c})": "无效的选择：{v}（可选：{c}）",
    "invalid {t} value: {v}": "无效的 {t} 值：{v}",
    "expected one argument": "需要一个值",
    "Did you mean: {c}": "你是不是想用：{c}",
    "Did you mean {c}?": "你是不是想用 {c}？",
    "See the commands with: {c}": "查看所有命令：{c}",
    "See the options with: {c}": "查看所有选项：{c}",
    "Use your last measurement: {c}": "使用上次的测量结果：{c}",
    "Not sure where to start? {c}": "不知道从哪开始？{c}",
    "options": "选项",
    "positional arguments": "位置参数",
    "show this help message and exit": "显示这份帮助并退出",

    # Tab completion
    "Tab completion: {c}": "Tab 补全：{c}",
    "Wrote {p}": "已写入 {p}",
    "Added to {p}": "已加入 {p}",
    "Already in {p}": "{p} 里已经有了",
    "Removed from {p}": "已从 {p} 移除",
    "Deleted {p}": "已删除 {p}",
    "Tab completion was not installed.": "还没有安装 Tab 补全。",
    "This window does not have it yet. Open a new window, or run this line here first:": "当前窗口还不能用。新开一个窗口，或者先在这里运行这一行：",
    "Then try it: type python -m discprobe timing --s and press Tab.": "然后试试：输入 python -m discprobe timing --s 再按 Tab。",
    "This PowerShell's execution policy is {a}, so it would not load the script, and {b} was left alone.":
        "这个 PowerShell 的执行策略是 {a}，不会加载脚本，所以没有改动 {b}。",
    "The policy is yours to decide. To allow your own scripts: {c}": "要不要放开由你决定。允许运行自己的脚本：{c}",
    "Then run this command again.": "然后再运行一次这条命令。",
    "integer": "整数",
    "number": "数字",
    "path": "路径",
    "text": "文字",
    "kB/s or 4x": "kB/s 或倍速，如 4x",
    "print a script that adds Tab completion to your shell": "生成脚本，让 shell 能按 Tab 补全",
    "language of the text": "显示语言",
    "keep the screen still": "关掉动画",

    # Writing files
    "Writing {p}: {n} sectors of seeded random data": "正在写 {p}：{n} 个扇区的随机数据",
    "Burn it with any image burner, then run `geo` on it.": "用任意镜像刻录工具刻好，再对它运行 `geo`。",
    "Writing {p} (about a minute)": "正在写 {p}（约一分钟）",
    "Writing {p}": "正在写 {p}",
    "Checking what was written...": "正在检查写入的内容……",
    "Verified: sampled sectors in every ring record the intended byte": "检查通过：每个环抽样的扇区都记录了预期的字节",
    "Verified: guards are pure, bands follow their patterns": "检查通过：保护环干净，各条带符合图案",
    "Verified: sampled sectors match the design": "检查通过：抽样的扇区与图案一致",
    "VERIFY FAILED: {x}": "检查未通过：{x}",
    "VERIFY FAILED:": "检查未通过：",
    "Layout: {p}  (needed by ringscan)": "布局文件：{p}（ringscan 要用）",
    "Layout: {p}  (needed by calscan)": "布局文件：{p}（calscan 要用）",
    "Layout: {p}": "布局文件：{p}",
    "Spec: {p}": "规格文件：{p}",
    "Preview (data-side view): {p}": "预览图（从数据面看）：{p}",
    "Preview (data-side view, false colours): {p}": "预览图（从数据面看，假彩色）：{p}",
    "Pattern: {p}": "图案：{p}",
    "Burn with any image burner (Windows Disc Image Burner works) and note the speed. The file system is an empty ISO 9660 placeholder.":
        "用任意镜像刻录工具刻录（Windows 自带的就行），并记下速度。文件系统只是一个空的 ISO 9660 占位。",
    "Burn with any image burner (Windows Disc Image Burner works). The file system is an empty ISO 9660 placeholder.":
        "用任意镜像刻录工具刻录（Windows 自带的就行）。文件系统只是一个空的 ISO 9660 占位。",
    "Make the image exactly fill the DiscImageStudio canvas (radius {r} mm), centred.": "让图片正好铺满 DiscImageStudio 的画布（半径 {r} mm）并居中。",
    "{k}, geometry u {u}, v {v} from {g}; {n} sectors ({s} GB), {t}": "{k}，几何 u {u}、v {v}，来自 {g}；{n} 个扇区（{s} GB），{t}",
    "{n} tiles, palette {p}; geometry u {u}, v {v} from {g}; {c} sectors ({s} GB)": "{n} 个色块，调色板 {p}；几何 u {u}、v {v}，来自 {g}；{c} 个扇区（{s} GB）",
    "dark {a}, light {b}": "深色 {a}，浅色 {b}",
    "textures {a}": "纹理 {a}",
    "picture {a}": "图片 {a}",
    "design {a}": "图案 {a}",
    "grid, {a} mm lines": "网格，线宽 {a} mm",
    "{n} rings from {m} scans, fit residual rms {r} deg": "{m} 张扫描共 {n} 个环，拟合残差 rms {r}°",
    "Angle correction: {p}  (use with image --correction)": "角度修正文件：{p}（配合 image --correction 使用）",
    "inner {a} mm, outer {b} mm, pitch shape {c}": "内半径 {a} mm，外半径 {b} mm，轨距形状 {c}",
    "angle difference to the measured map over {a}-{b} mm: max {c} deg, rms {d} deg": "在 {a}-{b} mm 内与实测角度的差：最大 {c}°，rms {d}°",
    "DiscImageStudio {m} preset object in {p} (key 'preset')": "DiscImageStudio 的 {m} 预设已写入 {p}（键名 preset）",
    "Timing cannot see the CD along-track constant and none was given, so radial lines may come out twisted. Measure it on a burned disc, then use --along-track-frames.":
        "计时测不到 CD 的沿轨常数，而你也没有提供，所以径向线可能会扭曲。请在刻好的盘上测出它，再用 --along-track-frames。",
    "the preset misses the measured map by {a} deg over {b}-{c} mm (outer radius came out {d} mm); check --sectors and the fit range. No preset written.":
        "预设与实测角度差了 {a}°（{b}-{c} mm 范围内，外半径算出来是 {d} mm）；请检查 --sectors 和拟合范围。没有写入预设。",
    "CD output already exists: {p}; choose a new filename": "CD 输出文件已存在：{p}；请换一个文件名",
    "CD image needs {a} sectors, got {b}": "CD 镜像需要 {a} 个扇区，实际是 {b}",
    "ISO 9660 sectors overlap the drawing; leave an inner background margin": "ISO 9660 扇区和图案重叠了；内圈要留出背景余量",
    "phase.csv, summary.json and check images: {p}": "phase.csv、summary.json 和检查图保存在：{p}",
    "rings.csv, textures.csv, summary.json and unrolled views: {p}": "rings.csv、textures.csv、summary.json 和展开图保存在：{p}",
    "bands.csv, phase.csv, summary.json and unrolled.png: {p}": "bands.csv、phase.csv、summary.json 和 unrolled.png 保存在：{p}",
    "phi.csv and summary.json: {p}": "phi.csv 和 summary.json 保存在：{p}",
    "No DPI in file and none given; assuming 600 dpi.": "文件里没有 DPI，也没有指定；按 600 dpi 计算。",
    "could not locate the disc edge; pass --centre X,Y in pixels": "找不到盘的边缘；请用 --centre X,Y 给出圆心像素坐标",
    "fewer than 20 rings show the spoke pattern; check the scan and the spec file": "能看到辐条图案的环不足 20 个；请检查扫描图和规格文件",
    "could not fit the guard-ring edges; check the scan and the layout file": "拟合不出保护环边缘；请检查扫描图和布局文件",
    "{n}: part of the disc is outside the scan": "{n}：盘的一部分在扫描范围外",
    "{n}: no DPI in file and none given; assuming 600 dpi": "{n}：文件里没有 DPI，也没有指定；按 600 dpi 计算",
    "Suggested palette (dark to bright): {a}": "建议的调色板（从暗到亮）：{a}",
    "warning: {a}": "警告：{a}",

    # Command summaries
    "Start here": "从这里开始",
    "Measure a disc": "测量光盘",
    "Make a disc image": "制作光盘镜像",
    "Read scans of burned discs": "分析刻好的盘的扫描图",
    "Use elsewhere": "用到别处",
    "Measure a burned disc's spiral from read timing, then put pictures on discs. Drive commands only read.":
        "用读取计时测出刻好的盘的螺旋走向，再把图片刻到盘上。操作光驱的命令只读不写。",
    "list optical drives": "列出光驱",
    "show which steps are done and the next command to run": "显示做到了哪一步，以及下一条命令",
    "list past results, newest first": "列出以前的结果，最新的在前",
    "dump drive and disc information": "显示光驱和光盘的信息",
    "cache/FUA test, CAV check, sector phase measurement": "检查光驱能不能测量：缓存、转速是否恒定、扇区角度",
    "generate the radial-spoke calibration pattern": "生成径向辐条标定图",
    "measure spoke rotation versus radius on a flatbed scan": "在平板扫描图上测辐条随半径的旋转",
    "write the DVD texture-ring test ISO (one recorded byte per ring)": "写 DVD 纹理环测试镜像（每个环记录一种字节）",
    "measure texture brightness on scans of the ring disc": "在纹理环盘的扫描图上测各纹理的亮度",
    "write a multi-hypothesis calibration ISO (bracketing disc, or refinement disc)": "写多假设标定镜像（粗定盘或精修盘）",
    "fit the disc geometry from a scan of a calibration disc": "从标定盘的扫描图拟合盘面几何",
    "measure the spiral geometry of a burned DVD from read timing (ladder)": "用读取计时测出刻好的盘的螺旋几何",
    "write a picture ISO placed with a measured geometry (grid test by default)": "按测出的几何写图片镜像（默认是网格测试图）",
    "write a self-locating texture palette target (IDs + swatches in every tile)": "写能自定位的纹理调色板盘（每个色块带编号和色样）",
    "write the beacon target (tiles readable from one photo, no whole-disc fit)": "写信标盘（一张照片就能读色块，不需要拟合整张盘）",
    "read IDs and swatch levels from flatbed scans of the tile palette target": "从调色板盘的平板扫描图读取编号和色样亮度",
    "measure line straightness on scans of the burned grid test": "在网格测试盘的扫描图上测线条是否笔直",
    "fit an angle-correction curve from gridscan phi.csv files": "用 gridscan 的 phi.csv 拟合角度修正曲线",
    "fit the measured angle map as a DiscImageStudio DVD or CD preset (cubic pitch)": "把测出的角度关系拟合成 DiscImageStudio 的 DVD 或 CD 预设",
    "write a random-data ISO for full-disc timing calibration": "写随机数据镜像，刻好后用来测量",
    "parser checks and end-to-end runs on the simulated drive and a synthetic scan": "用模拟光驱和合成扫描图做自检",

    # Option help
    "which steps to show (default: what you measured last)": "显示哪种盘的步骤（默认：你上次测的那种）",
    "only this kind, e.g. geo, timing, info": "只看这一种，比如 geo、timing、info",
    "print only the newest folder, skipping simulated runs and stopped geo runs": "只打印最新的文件夹，跳过模拟的和中途停下的 geo 结果",
    "how many to list (default 15)": "列出多少个（默认 15）",
    "results directory (default: results)": "结果目录（默认 results）",
    "drive letter, e.g. E:; `list` shows them. At a terminal it can be left out when there is one drive": "光驱盘符，比如 E:；用 `list` 查看。在终端里只有一台光驱时可以不写",
    "use the simulated drive (nofua: FUA ignored; flush: FUA ignored but a zero-length FUA read drops the cache)": "使用模拟光驱，不需要真光驱（nofua：模拟忽略 FUA；flush：忽略 FUA，但零长度 FUA 读能清缓存）",
    "Windows command path: spti may need an elevated terminal; imapi (IMAPI2 IDiscRecorder2Ex) works as a standard user; auto tries spti, then imapi": "Windows 上发命令的通道：spti 可能要管理员权限；imapi 普通用户可用；auto 先试 spti，再试 imapi",
    "simulation seed": "模拟用的随机种子",
    "output directory (default: results)": "输出目录（默认 results）",
    "R/X pairs per phase target": "每个测量位置读多少对（基准扇区 / 目标扇区）",
    "reads per zone in the period test": "转速测试中每个位置读多少次",
    "comma-separated disc fractions, default 0.15,0.35,0.55,0.75,0.95": "测量位置，用占已刻录容量的比例表示，逗号分隔，默认 0.15,0.35,0.55,0.75,0.95",
    "reference sector as a disc fraction": "基准扇区的位置，用占已刻录容量的比例表示",
    "read speed in kB/s or as a multiple: 4x, or DVD 8x = 11080, 16x = 22160 (omit to leave as is, sends SET CD SPEED otherwise)": "读取速度，写 kB/s 或倍速：4x，或 DVD 8x = 11080、16x = 22160（不写就不改速度；写了会发送 SET CD SPEED）",
    "set the Rotational Control bit of SET CD SPEED; MMC defines it for writing, so whether reads change is only known from the period test": "设置 SET CD SPEED 的转速控制位；标准里它是给写入用的，读取会不会变，只能看转速测试",
    "sectors per measurement read, not the disc size: 1, or on a DVD 16 for one whole ECC block": "每次测量读几个扇区，不是盘的大小：1，或在 DVD 上用 16 读一个完整的 ECC 块",
    "sectors per measurement read, not the disc size; 16 reads one whole aligned DVD ECC block": "每次测量读几个扇区，不是盘的大小；16 表示读一个完整对齐的 DVD ECC 块",
    "random pause (0..N ms) before each timed read, so repeated reads do not all span the same number of revolutions; should exceed one revolution": "每次计时读之前随机等待 0 到 N 毫秒，避免重复读取都跨过相同圈数；应当长于转一圈的时间",
    "sectors read elsewhere before each measurement when the cache cannot be bypassed": "绕不过缓存时，每次测量前先读别处多少个扇区把缓存挤掉",
    "run the phase test even if the drive did not look CAV": "即使转速看起来不恒定，也继续测盘面角度",
    "give up after this long (0 = no limit)": "超过这么多分钟就放弃（0 表示不限）",
    "disc radius at the image edge: DiscImageStudio canvas radius (CD 57.5, DVD/BD the generation outer radius)": "图片边缘对应的盘面半径：即 DiscImageStudio 的画布半径（CD 57.5，DVD/BD 是生成时的外半径）",
    "image size in pixels": "图片边长（像素）",
    "scan file (PNG/TIFF; avoid JPEG)": "扫描图（PNG/TIFF，避免 JPEG）",
    "the .spokes.json written next to the pattern": "和图案一起生成的 .spokes.json",
    "scan resolution if the file does not record it": "文件里没记录时，在这里给扫描分辨率",
    "approximate disc centre X,Y in pixels if detection fails": "自动检测失败时，给出大致的圆心像素坐标 X,Y",
    "scrambled-domain bytes in hex, or RND; must include A5 and 92": "要记录的字节（十六进制，加扰后的值）或 RND；必须包含 A5 和 92",
    "repeats of the full texture set, inner to outer": "整组纹理从内到外重复几次",
    "radius where the first ring starts": "第一个环开始的半径",
    "texture between the data start and the first ring": "数据起点和第一个环之间用的纹理",
    "nominal data start radius for placing rings": "排环时用的标称数据起始半径",
    "print the layout without writing": "只打印布局，不写文件",
    "one or more scans (PNG/TIFF, no auto adjustments); rotate the disc between scans for repeats": "一张或多张扫描图（PNG/TIFF，不要自动调整）；重复扫描时把盘转一下",
    "the .rings.json written next to the ISO": "和镜像一起生成的 .rings.json",
    "dark,bright references (DVD A5,92; CD 0D,AA) defining levels 0 and 1; use the darkest and brightest textures the scan shows": "定义亮度 0 和 1 的暗、亮参考（DVD A5,92；CD 0D,AA）；用扫描图里最暗和最亮的纹理",
    "summary.json of a calscan run: write the refinement disc, every band drawn with that fit": "calscan 的 summary.json：写精修盘，每条带都按那次拟合来画",
    "largest local-rate offset tried, e.g. 0.012 = 1.2 %%": "尝试的最大局部速率偏差，比如 0.012 = 1.2 %%",
    "repeats of the hypothesis set (default 3; 20 for refinement)": "整组假设重复几次（默认 3；精修盘 20）",
    "centre geometry of the sweep": "扫描范围的中心几何",
    "scan (PNG/TIFF, grey or colour, no auto adjustments)": "扫描图（PNG/TIFF，灰度或彩色，不要自动调整）",
    "the .cal.json written next to the ISO": "和镜像一起生成的 .cal.json",
    "read speed to fix, in kB/s or as a multiple like 4x (default 4x = 5540; CD 8x = 1411)": "固定的读取速度，写 kB/s 或倍速如 4x（默认 4x = 5540；CD 8x = 1411）",
    "readable LBA ranges a-b,c-d (default 3-85 %% of the recorded area); see below": "可读的扇区范围 a-b,c-d（默认已刻录区域的 3-85 %%）；见下文",
    "texture-ring layout file: use only the rings of --texture": "纹理环布局文件：只用 --texture 指定的环",
    "kept away from ring edges": "离环边缘留多少扇区",
    "reference/target read pairs per rung": "每个测量点读多少对（基准 / 目标）",
    "prior geometry (loose)": "初始几何估计（宽松）",
    "stop when chi2/dof of the constant-pitch fit exceeds this; raise it for media whose pitch varies (CD: a smooth S of a few degrees), the 90-degree residual check still catches whole-turn errors": "恒定轨距拟合的误差比 (chi2/dof) 超过这个值就停止；轨距本来有变化的盘可以调大（CD 常有几度的平滑 S 形），90° 残差检查仍能发现数错整圈",
    "summary.json of a geo run, its folder, latest, or pick to choose": "geo 结果的 summary.json、它所在的文件夹、latest（最新一次可靠的结果），或 pick（手动选）",
    "greyscale picture to threshold instead of the grid test": "用这张灰度图代替网格测试图",
    "prepared boolean design (True = dark), 6000 x 6000 cells of 0.02 mm, data-side view": "准备好的布尔图案（True 为深色），6000 x 6000 格，每格 0.02 mm，从数据面看",
    "the picture's longer side on the disc, in mm; it keeps its shape": "图片长边在盘上的长度（mm），保持比例",
    "outer radius of the drawing": "图案的外半径",
    "grid line width": "网格线宽",
    "angle-correction file (phi(r) measured on a burned grid)": "角度修正文件（在刻好的网格盘上测得）",
    "CD: frames the read completion lies beyond the timing model, measured on a burned grid": "CD：读取完成点比计时模型多出的帧数，在刻好的网格盘上测得",
    "light texture (B9 scanned brightest on Ritek F1)": "浅色纹理（Ritek F1 上 B9 扫出来最亮）",
    "for a label design (uint8): one texture per label, e.g. A5 92 8B00 RND MIX:92,4F": "标签图案 (uint8) 用：每个标签一种纹理，比如 A5 92 8B00 RND MIX:92,4F",
    "up to 9 textures: a byte (A5), a repeated sequence (8B00), RND, or MIX:92,4F": "最多 9 种纹理：一个字节 (A5)、重复序列 (8B00)、RND 或 MIX:92,4F",
    "angle-correction file": "角度修正文件",
    "radii (mm) separating the tile rings": "分隔各色块环的半径 (mm)",
    "tile size along the arc": "色块沿弧方向的大小",
    "cell columns per tile (4 hold the ID, the rest swatches)": "每个色块的列数（4 列放编号，其余放色样）",
    "add an angle scale band (mm)": "加一条角度刻度带 (mm)",
    "background gap between tiles": "色块之间的背景间隙",
    "give every tile its own random swatch order (decouples texture from position)": "让每个色块的色样顺序各自随机（把纹理和位置分开）",
    "scan images (PNG/TIFF/JPEG)": "扫描图（PNG/TIFF/JPEG）",
    "layout file written by the tiles command": "tiles 命令生成的布局文件",
    "must match the image command": "要和 image 命令一致",
    "let the (weak) mirror test decide orientation": "让（不太可靠的）镜像测试决定方向",
    "phi.csv files written by gridscan": "gridscan 生成的 phi.csv",
    "summary.json of the geo run the grid disc was burned with (recorded only)": "刻网格盘时所用 geo 结果的 summary.json（只作记录）",
    "summary.json of a geo run, its folder, latest, or pick to choose; a CD fit gives a CD preset": "geo 结果的 summary.json、它所在的文件夹、latest，或 pick（手动选）；CD 的结果会生成 CD 预设",
    "angle-correction file from the correction command": "correction 命令生成的角度修正文件",
    "the disc's capacity, not how much was burned (`info` on a blank disc prints it); required": "盘的容量，不是刻了多少（对空白盘运行 `info` 会打印）；必填",
    "how much to burn, not the disc size; it has to fit on the blank": "要刻多少，不是盘的容量；要放得下这张空盘",
    "fit range: use the measured span (DVD default 25.8, CD the span geo measured)": "拟合范围：用实测范围（DVD 默认 25.8，CD 用 geo 测到的范围）",
    "DVD default 54.4, CD the span geo measured": "DVD 默认 54.4，CD 用 geo 测到的范围",
    "CD only: along-track constant in frames, as in image --along-track-frames": "仅 CD：沿轨常数（帧），含义同 image --along-track-frames",
    "disc type; cd also switches the defaults to CD values (default: dvd)": "盘的类型；cd 同时会把默认值换成 CD 的值（默认 dvd）",
    "check that --geo measured this disc type; the fit decides the preset": "检查 --geo 测的是不是这种盘；预设类型由拟合结果决定",
    "CD only: sector layout the burner writes; IMAPI2 data burns are Mode 2 Form 1 (user data from byte 24), so textures are pre-scrambled for that unless you burn Mode 1": "仅 CD：刻录工具写的扇区格式；IMAPI2 刻数据盘是 Mode 2 Form 1（用户数据从第 24 字节开始），除非你刻 Mode 1，否则纹理都按它预先加扰",
}

BLOCKS = {
    "completion": """\
给 disc-probe 加上 Tab 补全。一条命令就能装好：
  python -m discprobe completion install

它会在主目录写一个脚本，并在 shell 的启动文件里加一行。
`completion uninstall` 会把两者都删掉；更新 disc-probe 后再 install 一次就会刷新脚本。
加 --lang zh 或 --lang en 可以指定说明文字的语言。

也可以手动：先生成一次脚本，再让 shell 加载它：

PowerShell：
  python -m discprobe completion powershell > $HOME\\discprobe-completion.ps1
  加到 $PROFILE：. $HOME\\discprobe-completion.ps1
bash：
  python -m discprobe completion bash > ~/.discprobe-completion.bash
  加到 ~/.bashrc：source ~/.discprobe-completion.bash
zsh：
  python -m discprobe completion zsh > ~/.discprobe-completion.zsh
  加到 ~/.zshrc：source ~/.discprobe-completion.zsh""",
    "workflow": """\
通常的流程，以 DVD 为例（CD 在每条命令后加 --media cd，步骤见 docs/MANUAL.md）：
  python -m discprobe random --output iso/random.iso    然后把它刻到盘上
  python -m discprobe timing --drive E:                 这台光驱能不能测量？
  python -m discprobe geo --drive E:                    测量盘面螺旋几何
  python -m discprobe image --geo latest --picture my_picture.png --output iso/picture.iso
  python -m discprobe disexport --geo latest --sectors <sectors> --output dis_preset.json

在终端里，只有一台光驱时可以不写 --drive，每条命令结束时都会打印下一条。
`python -m discprobe <command> -h` 查看某条命令的选项。""",
    "timing": """\
例子：
  python -m discprobe timing --drive E:                 第一次看一台光驱，1 到 3 分钟
  python -m discprobe timing --drive E: --speed 4x      固定读取速度
  python -m discprobe timing --drive E: --sectors 16    每次读一个完整的 DVD ECC 块，在一台光驱上更干净
  python -m discprobe timing --drive E: --media cd      CD（默认速度 1411 kB/s = 8x）

--speed 怎么选：低速通常噪声更小，但不是每台光驱都会换速度；
看“转速方式”和“位置”那几行就知道它实际怎么转。可以写 kB/s 或倍速（1x：DVD 1385，CD 176.4，BD 4495）。
  DVD  2.4x 3324   4x 5540   8x 11080
  CD   8x 1411    16x 2822   24x 4234

这里的 --sectors 是每次读几个扇区，和 disexport --sectors 的盘容量不是一回事。""",
    "geo": """\
例子：
  python -m discprobe geo --drive E:                    DVD，固定 4x
  python -m discprobe geo --drive E: --speed 3324       timing 显示更干净的低速度
  python -m discprobe geo --drive E: --media cd         CD，固定 1411 kB/s

--ranges 怎么选：默认（已刻录区域的 3-85 %）适合大多数盘。总出错或在换速点之后的区域可以排除：
运行时会打印停下的扇区号（LBA），`info` 显示最后扇区号。范围加宽能覆盖更大半径，前提是光驱读得干净。
  python -m discprobe geo --drive E: --ranges 70000-1900000""",
    "info": """\
例子：
  python -m discprobe info --drive E:     空白盘也能用；显示厂商代码 (MID 或 ATIP) 和扇区数""",
    "random": """\
例子：
  python -m discprobe random --output iso/random.iso
  python -m discprobe random --media cd --output iso/cd-random.iso

把它刻到空白盘上（Windows：右键 .iso，选“刻录光盘映像”），再对这张盘运行 timing。""",
    "image": """\
例子：
  python -m discprobe image --geo latest --picture my_picture.png --output iso/picture.iso
  python -m discprobe image --geo results/geo-E-20261105-120000 --correction correction.json --picture my_picture.png
  python -m discprobe image --media cd --geo latest --along-track-frames 206 --output iso/cd-grid.iso

--geo 可以写 summary.json、geo 结果文件夹、latest（最新一次可靠的真实测量），或 pick（手动选）。""",
    "disexport": """\
例子：
  python -m discprobe disexport --geo latest --sectors <sectors> --r-min 25.8 --r-max 54.4 --output dis_preset.json
  python -m discprobe disexport --geo latest --sectors <sectors> --correction correction.json --output dis_preset_cd.json

--sectors 是盘的容量：看空白盘上的 `info`，DiscImageStudio 里也填这个数。
有用户发现它的“从光盘读取”给的数偏大。和 timing --sectors 不是一回事。
--geo 可以写 summary.json、geo 结果文件夹、latest，或 pick（手动选）。CD 的结果会生成 CD 预设；--media 只用来核对。""",
    "results": """\
例子：
  python -m discprobe results                 按时间列出运行过的测量，最新的在前
  python -m discprobe results geo             只看 geo
  python -m discprobe results geo --latest    只打印最新一次可靠结果的文件夹，脚本里用
  python -m discprobe results --pick          选择 geo 结果：先按盘和光驱，再按精度或日期""",
    "guide": """\
读取结果文件夹，显示哪些步骤已完成，并打印下一条命令。不会操作光驱。""",
}
