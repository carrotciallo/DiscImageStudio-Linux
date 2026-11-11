"""One line under the opening screen of `guide`, set by the day and the hour.

The same moment of the week always gets the same line. It is only small talk: nothing here may
read like a result, so no line says a drive is ready or steady. Each entry is (English, Chinese).
`guide` is the only place that shows one, and only at a terminal.
"""

from __future__ import annotations

import datetime

from .i18n import active

FIRST_TIME = (("Welcome. Your first disc starts here.", "欢迎，你的第一张盘从这里开始。"),
              ("Welcome. All it takes is a drive and a few blank discs.", "欢迎，有一台光驱和几张空盘就够了。"))

# Each day, in order: late night (22-05), early (05-09), morning (09-12), afternoon (12-18), evening (18-22).
WEEK = (
    (("Monday hasn't started, but you have.", "周一还没开始，你先开始了。"),            # Monday
     ("Up early. The blank discs won't mind.", "这么早，空盘们也不介意。"),
     ("New week, new spiral.", "新的一周，新的一圈。"),
     ("Good afternoon. Got a disc for me?", "下午好，有盘要测吗？"),
     ("Evening. How did today's disc turn out?", "晚上好，今天的盘刻得怎么样？")),
    (("It's late. One more turn, then bed?", "夜深了，这圈转完就睡？"),                  # Tuesday
     ("Good morning. Which disc today?", "早上好，今天测哪张盘？"),
     ("Coffee first, then the drive.", "先来杯咖啡，再开光驱。"),
     ("A good afternoon for a few turns.", "这个下午，适合转上几圈。"),
     ("Back for another turn.", "又转回来了。")),
    (("Late-night burn session.", "深夜刻盘时间。"),                                     # Wednesday
     ("Morning. The drive is awake too.", "早，光驱也刚醒。"),
     ("Midweek. The discs keep turning.", "周中了，盘还是要转的。"),
     ("One blank disc, several ideas.", "一张空盘，几个想法。"),
     ("Evening. Is that disc still in the tray?", "晚上好，那张盘还在托盘里吗？")),
    (("Up late? So is the drive.", "还没睡？光驱陪你。"),                                 # Thursday
     ("Early start, fresh disc.", "起得真早，来张新盘？"),
     ("What are we measuring?", "今天测点什么？"),
     ("What are we burning?", "今天刻点什么？"),
     ("Good evening. What's going on the disc tonight?", "晚上好，今晚往盘上刻点什么？")),
    (("Hello, night owl. Mind the spin-up noise.", "夜猫子你好，转起来声音有点大哦。"),  # Friday
     ("Friday. Let's get that disc burned.", "周五了，今天把盘刻了吧。"),
     ("Load a disc when you're ready.", "准备好了就放盘。"),
     ("Friday afternoon. Time to try a new picture.", "周五下午，正好试张新图。"),
     ("It's Friday. Burn one to celebrate?", "周五了，刻张盘庆祝一下？")),
    (("A weekend night. No rush, spin slowly.", "周末的夜晚，不急，慢慢转。"),            # Saturday
     ("This early on a Saturday? Even the disc is surprised.", "周六这么早？盘都没想到。"),
     ("The weekend. Let it spin.", "周末了，让它转吧。"),
     ("Hello, world. Starting at sector 0.", "你好，世界。从第 0 扇区开始。"),
     ("Saturday night. Burn something pretty.", "周六晚上，刻张好看的。")),
    (("Reading discs by moonlight?", "月光下读盘？"),                                     # Sunday
     ("This early on a Sunday? The drive is barely awake.", "周日这么早，光驱还没睡醒。"),
     ("Sunday. A good day for a low read speed.", "周日，适合低速读盘。"),
     ("Sunday afternoon. A few turns, then?", "周日下午，转几圈吧？"),
     ("Last disc of the weekend?", "周末的最后一张盘？")),
)


def _slot(hour: int) -> int:
    for slot, end in ((1, 9), (2, 12), (3, 18), (4, 22)):
        if 5 <= hour < end:
            return slot
    return 0


def pick(first_time: bool = False, now: datetime.datetime | None = None) -> str:
    now = now or datetime.datetime.now()
    entry = FIRST_TIME[now.toordinal() % len(FIRST_TIME)] if first_time else WEEK[now.weekday()][_slot(now.hour)]
    return entry[1] if active() == "zh" else entry[0]
