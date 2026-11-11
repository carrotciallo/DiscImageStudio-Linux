"""Chinese for people at a terminal. English stays the source text everywhere else.

Nothing here runs while the language is English, so scripts get exactly the bytes they always
had. With Chinese on, finished lines are looked up in `zh.TEXT` on their way out of stdout and
stderr; the measuring and writing code does not know. A line with no entry stays English, so a
changed message degrades instead of breaking. Result files are never translated.

Language: `--lang` on the command line wins anywhere. A pipe or DISCPROBE_PLAIN=1 stays English
without it, even with DISCPROBE_LANG set, because agents read that output. At a terminal it is
DISCPROBE_LANG, then the system language.
"""

from __future__ import annotations

import argparse
import functools
import locale
import os
import re
import sys
import unicodedata

CHINESE_CODE_PAGES = (936, 950, 54936)
_lang = "en"
_pinned = False
_saved = None
_exact = None
_patterns = None
_placeholder = re.compile(r"\{(\w+)\}")


def normalize(value: str) -> str | None:
    value = value.strip().lower()
    if value.startswith("zh") or value in ("cn", "chinese"):
        return "zh"
    return "en" if value.startswith("en") else None


def take_flag(argv: list[str]) -> tuple[str | None, list[str]]:
    """Pull --lang out of the arguments, so it can sit anywhere and never reaches summary.json."""
    rest, flag = [], None
    args = iter(argv)
    for arg in args:
        if arg == "--lang" or arg.startswith("--lang="):
            value = arg.partition("=")[2] if "=" in arg else next(args, "")
            flag = normalize(value)
            if flag is None:
                raise ValueError(f"--lang takes zh or en, not {value!r} (--lang 只能是 zh 或 en)")
        else:
            rest.append(arg)
    return flag, rest


def system_is_chinese(env=None, platform=None) -> bool:
    env = os.environ if env is None else env
    platform = platform or sys.platform
    for key in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        if env.get(key):
            return env[key].lower().startswith("zh")
    if platform == "win32":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            return k32.GetUserDefaultUILanguage() & 0x3FF == 0x04 or k32.GetACP() in CHINESE_CODE_PAGES
        except (AttributeError, OSError):
            return False
    try:
        return (locale.getlocale()[0] or "").lower().startswith(("zh", "chinese"))
    except ValueError:
        return False


def can_encode(stream) -> bool:
    try:
        "光盘".encode(getattr(stream, "encoding", None) or "ascii")
        return True
    except (UnicodeError, LookupError):
        return False


def decide(flag, interactive: bool, env, encodable: bool, chinese_system) -> str:
    """`chinese_system` is called only when the system language is what decides."""
    if flag:
        return flag
    if not interactive:
        return "en"
    forced = normalize(env.get("DISCPROBE_LANG", ""))
    if forced:
        return forced
    return "zh" if encodable and env.get("TERM") != "linux" and chinese_system() else "en"


class _Lines:
    """A text stream that translates each finished line."""

    def __init__(self, stream):
        self._stream = stream
        self._held = ""

    def write(self, text):
        self._held += text
        *lines, self._held = self._held.split("\n")
        for line in lines:
            self._stream.write(tr(line) + "\n")
        return len(text)

    def flush(self):
        if self._held:
            self._stream.write(tr(self._held))
            self._held = ""
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _prepare(stream) -> None:
    """Chinese must not crash on a narrow encoding; a file or pipe gets UTF-8."""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(errors="replace") if stream.isatty() else reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        pass


def use(lang: str) -> None:
    global _lang, _saved
    if lang == _lang:
        return
    _lang = lang
    if lang == "zh":
        _prepare(sys.stdout)
        _prepare(sys.stderr)
        _saved = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = _Lines(sys.stdout), _Lines(sys.stderr)
    else:
        for stream in (sys.stdout, sys.stderr):
            if isinstance(stream, _Lines):
                stream.flush()
        if isinstance(sys.stdout, _Lines):
            sys.stdout = _saved[0]
        if isinstance(sys.stderr, _Lines):
            sys.stderr = _saved[1]


def pin(lang: str) -> None:
    """Hold this language whatever `setup` is asked later (the self-test checks English text)."""
    global _pinned
    use(lang)
    _pinned = True


def unpin(lang: str) -> None:
    global _pinned
    _pinned = False
    use(lang)


def setup(flag: str | None, t) -> None:
    if not _pinned:
        use(decide(flag, t.interactive, os.environ, can_encode(t.stream), system_is_chinese))


def active() -> str:
    return _lang


def _load():
    global _exact, _patterns
    from . import zh
    _exact, _patterns = {}, []
    for key, value in zh.TEXT.items():
        if "{" not in key:
            _exact[key] = value
            continue
        pattern, seen = "", set()
        for i, part in enumerate(_placeholder.split(key)):
            if not i % 2:
                pattern += re.escape(part)
            else:       # a value used twice must be the same value
                pattern += f"(?P={part})" if part in seen else f"(?P<{part}>.*?)"
                seen.add(part)
        _patterns.append((len(_placeholder.sub("", key)), re.compile(pattern, re.DOTALL), value))
    _patterns.sort(key=lambda item: -item[0])      # the most specific wording first


@functools.lru_cache(maxsize=4096)
def _zh(text: str) -> str:
    body = text.strip()
    if not body or not re.search(r"[A-Za-z]", body):
        return text
    if _exact is None:
        _load()
    lead = text[:len(text) - len(text.lstrip())]
    tail = text[len(text.rstrip()):]
    if body in _exact:
        return lead + _exact[body] + tail
    for _, pattern, value in _patterns:
        m = pattern.fullmatch(body)
        if m:
            parts = {name: _zh(part) for name, part in m.groupdict().items()}
            return lead + _placeholder.sub(lambda p: parts[p[1]], value) + tail
    return text


def tr(text: str) -> str:
    return _zh(text) if _lang == "zh" else text


def block(name: str, english: str | None) -> str | None:
    """A whole help paragraph."""
    if _lang != "zh" or english is None:
        return english
    from . import zh
    return zh.BLOCKS.get(name, english)


def display_width(text: str) -> int:
    """Terminal columns: a Chinese character takes two, a combining mark none."""
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def fit(text: str, width: int) -> str:
    """Cut to `width` columns, marking the cut."""
    if display_width(text) <= width:
        return text
    out, used = [], 0
    for ch in text:
        w = display_width(ch)
        if used + w > max(width - 2, 0):
            break
        out.append(ch)
        used += w
    return "".join(out) + ".."[:max(width - used, 0)]


NO_LINE_START = "，。；：、）》？！,.;:)"


def wrap(text: str, width: int) -> list[str]:
    """Break by columns: anywhere between Chinese characters, only at spaces inside Latin words."""
    width = max(width, 8)
    tokens = re.findall(r"[^\s⺀-鿿＀-￯　-〿]+|\s+|.", " ".join(text.split()))
    lines, line = [], ""
    for token in tokens:
        if display_width(line) + display_width(token) > width and line and token not in NO_LINE_START:
            lines.append(line.rstrip())
            line = "" if token.isspace() else token
        else:
            line += token
    return lines + [line] if line else lines


class Formatter(argparse.RawDescriptionHelpFormatter):
    """argparse counts characters; Chinese help has to be wrapped by columns."""

    def add_usage(self, usage, actions, groups, prefix=None):
        super().add_usage(usage, actions, groups, "用法: " if prefix is None else prefix)

    def _split_lines(self, text, width):
        return wrap(text, width)


def localize_parser(parser: argparse.ArgumentParser) -> None:
    if _lang != "zh":
        return
    parser.formatter_class = Formatter
    for action in parser._actions:
        if action.help and action.help is not argparse.SUPPRESS:
            action.help = tr(action.help)
    for group in parser._action_groups:
        if group.title:
            group.title = tr(group.title)
