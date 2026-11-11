"""Tab completion: `python -m discprobe completion <shell>` prints a script for the shell to load.

The script holds every command and option as plain data, so pressing Tab never starts Python and
stays instant; regenerating it is the price after an update. Matching is by prefix over one
command's options, a few dozen at most, which is also what argparse accepts as an abbreviation.
Everything is keyed on `python -m discprobe`, and other uses of python keep the default completion.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from .i18n import block, tr

SHELLS = ("powershell", "bash", "zsh")
PATH_DESTS = {"output", "geo", "picture", "design_npy", "correction", "layout", "spec", "out", "rings_layout",
              "refine_from", "output_dir", "image", "images", "scans", "phi"}
VALUE_HINTS = {"--geo": ("latest", "pick"), "--speed": ("4x", "8x", "16x", "24x")}
POSITIONAL_VALUES = {"results": ("geo", "timing", "info")}
MARKER = "# disc-probe Tab completion"
BLOCKED_POLICIES = ("Restricted", "AllSigned")
USAGE = """\
Tab completion for disc-probe. One command sets it up:
  python -m discprobe completion install

It writes a script to your home folder and adds one line to your shell's startup file.
`completion uninstall` takes both out, and installing again after an update refreshes the script.
Add --lang zh or --lang en to choose the language of the descriptions.

Or by hand, generate the script once and have your shell load it:

PowerShell:
  python -m discprobe completion powershell > $HOME\\discprobe-completion.ps1
  add to $PROFILE:  . $HOME\\discprobe-completion.ps1
bash:
  python -m discprobe completion bash > ~/.discprobe-completion.bash
  add to ~/.bashrc:  source ~/.discprobe-completion.bash
zsh:
  python -m discprobe completion zsh > ~/.discprobe-completion.zsh
  add to ~/.zshrc:  source ~/.discprobe-completion.zsh"""


def _label(action) -> str:
    """What an option's value is, for the description."""
    if action.nargs == 0:
        return ""
    if action.choices:
        return "|".join(action.choices)
    if action.type is int:
        return tr("integer")
    if action.type is float:
        return tr("number")
    if getattr(action.type, "__name__", "") == "_speed":
        return tr("kB/s or 4x")
    return tr("path") if action.dest in PATH_DESTS else tr("text")


def table(build_parser):
    """{command: [(word, kind, values, label, help)]}.

    kind: "c" a word, "f" an option without a value, "v" with a value, "p" with a path, where files may be offered.
    """
    top, sub, _ = build_parser()
    rows = {"": [(a.dest, "c", (), "", tr(a.help)) for a in sub._choices_actions]}
    rows[""].append(("completion", "c", (), "", tr("print a script that adds Tab completion to your shell")))
    shared = [("--lang", "v", ("zh", "en"), "zh|en", tr("language of the text")),
              ("--no-animation", "f", (), "", tr("keep the screen still"))]
    rows[""] += shared + [("-h", "f", (), "", tr("show this help message and exit"))]
    for name, parser in sub.choices.items():
        rows[name] = [(value, "c", (), "", "") for value in POSITIONAL_VALUES.get(name, ())]
        for action in parser._actions:
            help_text = (action.help or "").replace("%%", "%")
            for flag in action.option_strings:
                values = tuple(action.choices or VALUE_HINTS.get(flag, ()))
                kind = "f" if action.nargs == 0 else "p" if action.dest in PATH_DESTS else "v"
                rows[name].append((flag, kind, values, _label(action), help_text))
        rows[name] += shared
    rows["completion"] = [(word, "c", (), "", "") for word in ("install", "uninstall") + SHELLS]
    return rows


def _ps_text(text: str) -> str:
    """ASCII whatever the code page or the file's encoding; the completer unescapes it when shown."""
    out = text.replace("\\", "\\\\").replace("\t", " ").replace("'", "''")
    return "".join(ch if ch < "\x7f" else f"\\u{ord(ch):04x}" for ch in out)


POWERSHELL = r"""# disc-probe completion for PowerShell, from `python -m discprobe completion powershell`.
# All the data is here, so pressing Tab never starts Python. Generate it again after an update.
$global:DiscprobeCompletion = @{
@TABLE@
}
Register-ArgumentCompleter -Native -CommandName python, python3, py -ScriptBlock {
    param($word, $ast, $cursor)
    $items = @($ast.CommandElements | Where-Object { $_.Extent.EndOffset -lt $cursor -or ($_.Extent.EndOffset -eq $cursor -and -not $word) } |
        ForEach-Object { $_.Extent.Text })
    $start = -1
    for ($i = 1; $i -lt $items.Count - 1; $i++) {
        if ($items[$i] -eq '-m' -and $items[$i + 1] -eq 'discprobe') { $start = $i + 2; break }
    }
    if ($start -lt 0) {     # still typing `python -m discprobe`
        if ($items.Count -gt 1 -and $items[-1] -eq '-m' -and 'discprobe'.StartsWith($word, 'OrdinalIgnoreCase')) {
            [System.Management.Automation.CompletionResult]::new('discprobe', 'discprobe', 'ParameterValue', 'disc-probe')
        } elseif ($items.Count -eq 1 -and -not $word -and (Test-Path 'discprobe\__main__.py')) {     # in the repository
            [System.Management.Automation.CompletionResult]::new('-m discprobe', '-m discprobe', 'ParameterValue', 'disc-probe')
            [System.Management.Automation.CompletionCompleters]::CompleteFilename('')
        }
        return
    }
    $command = ''; $previous = ''
    for ($i = $start; $i -lt $items.Count; $i++) {
        if (-not $command -and $items[$i] -notlike '-*' -and $previous -ne '--lang') { $command = $items[$i] }
        $previous = $items[$i]
    }
    $rows = $global:DiscprobeCompletion[$command]
    if (-not $rows) { return }
    $option = $null
    foreach ($row in $rows) {
        $f = $row -split "`t"
        if ($f[0] -eq $previous -and $f[1] -in 'v', 'p') { $option = $f; break }
    }
    if ($option) {
        $values = @($option[2] -split ' ' | Where-Object { $_ })
        if ($previous -eq '--drive') {
            $values = @([System.IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq 'CDRom' } | ForEach-Object { $_.Name.TrimEnd('\') })
        }
        $hits = @($values | Where-Object { $_.StartsWith($word, 'OrdinalIgnoreCase') })
        foreach ($v in $hits) { [System.Management.Automation.CompletionResult]::new($v, $v, 'ParameterValue', $v) }
        if (-not $hits -and $option[1] -eq 'v') {   # nothing to offer, and files would be wrong here: say what it takes
            $hint = "<$([regex]::Unescape($option[3]))>"
            $text = if ($word) { $word } else { ' ' }
            [System.Management.Automation.CompletionResult]::new($text, $hint, 'Text', "$hint  $([regex]::Unescape($option[4]))")
        }
        return
    }
    $matched = $false
    foreach ($row in $rows) {
        if ($row.StartsWith($word, 'OrdinalIgnoreCase')) {
            $matched = $true
            $f = $row -split "`t"
            $type = if ($f[1] -eq 'c') { 'ParameterValue' } else { 'ParameterName' }
            $list = if ($f[3]) { "$($f[0]) <$($f[3])>" } else { $f[0] }
            $tip = [regex]::Unescape($f[4])
            $list = [regex]::Unescape($list)
            [System.Management.Automation.CompletionResult]::new($f[0], $list, $type, $(if ($tip) { "$list  $tip" } else { $list }))
        }
    }
    if (-not $matched -and $word -and (-not $command -or $word -like '-*')) {   # a typo here is not a file name
        [System.Management.Automation.CompletionResult]::new($word, $word, 'Text', $word)
    }
}
# On a discprobe line, Tab shows a list with what each entry means; elsewhere it does what it did.
if (Get-Module PSReadLine) {
    $tab = (Get-PSReadLineKeyHandler -Bound | Where-Object { $_.Key -eq 'Tab' } | Select-Object -First 1).Function
    if ($tab -in 'TabCompleteNext', 'TabCompletePrevious', 'Complete', 'MenuComplete') {
        $global:DiscprobeTab = $tab
        Set-PSReadLineKeyHandler -Key Tab -BriefDescription DiscprobeTab -LongDescription 'List disc-probe options on a discprobe line' -ScriptBlock {
            param($key, $arg)
            $line = $null; $cursor = $null
            [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)
            if ($line -match '\s-m\s+discprobe\b') {
                [Microsoft.PowerShell.PSConsoleReadLine]::MenuComplete($key, $arg)
            } else {
                [Microsoft.PowerShell.PSConsoleReadLine]::$global:DiscprobeTab($key, $arg)
            }
        }
    }
}
"""


def powershell(rows) -> str:
    lines = []
    for command, entries in rows.items():
        lines.append(f"'{command}' = @(")
        lines += ["'" + "\t".join((word, kind, " ".join(values), _ps_text(label), _ps_text(text))) + "'"
                  for word, kind, values, label, text in entries]
        lines.append(")")
    return POWERSHELL.replace("@TABLE@", "\n".join(lines))


BASH = r"""# disc-probe completion for bash and zsh, from `python -m discprobe completion`.
# All the data is here, so pressing Tab never starts Python. Generate it again after an update.
_discprobe_complete() {
    local cur=${COMP_WORDS[COMP_CWORD]} previous= command= start=0 i word
    for ((i = 1; i < COMP_CWORD - 1; i++)); do
        if [[ ${COMP_WORDS[i]} == -m && ${COMP_WORDS[i + 1]} == discprobe ]]; then start=$((i + 2)); break; fi
    done
    COMPREPLY=()
    if ((start == 0)); then     # still typing `python -m discprobe`
        if ((COMP_CWORD > 1)) && [[ ${COMP_WORDS[COMP_CWORD - 1]} == -m ]]; then
            COMPREPLY=($(compgen -W "discprobe" -- "$cur"))
        elif ((COMP_CWORD == 1)) && { [[ $cur == -* ]] || [[ -z $cur && -f discprobe/__main__.py ]]; }; then
            COMPREPLY=($(compgen -W "-m" -- "$cur"))
        fi
        return 0
    fi
    for ((i = start; i < COMP_CWORD; i++)); do
        word=${COMP_WORDS[i]}
        case $word in :|=) continue ;; esac     # the shell splits E: and --speed=4x at these
        if [[ -z $command && $word != -* && $word != *[!a-z]* ]]; then
            case $previous in @VALUE_FLAGS@) ;; *) command=$word ;; esac
        fi
        previous=$word
    done
    local words=
    case $previous in
@VALUES@
    esac
    if [[ -z $words ]]; then
        case $previous in @PATH_FLAGS@) return 0 ;; esac
        case $previous in @VALUE_FLAGS@) compopt +o default +o bashdefault 2>/dev/null; return 0 ;; esac    # not a file
        [[ -n $command && $cur != -* ]] || compopt +o default +o bashdefault 2>/dev/null                     # a typo is not a file
        case $command in
@COMMANDS@
            *) return 0 ;;
        esac
    fi
    COMPREPLY=($(compgen -W "$words" -- "$cur"))
}
"""
BASH_TAIL = "complete -o default -o bashdefault -F _discprobe_complete python python3\n"
ZSH_HEAD = ("(( $+functions[compdef] )) || { autoload -Uz compinit && compinit; }\n"
            "autoload -Uz bashcompinit && bashcompinit\n")


def bash(rows) -> str:
    choices, value_flags, path_flags = {}, set(), set()
    for entries in rows.values():
        for word, kind, values, _, _ in entries:
            if kind in ("v", "p"):
                value_flags.add(word)
                if kind == "p":
                    path_flags.add(word)
                if values:
                    choices[word] = values
    values = [f"        {flag}) words=\"{' '.join(v)}\" ;;" for flag, v in sorted(choices.items())]
    commands = ["            " + (command or '""') + ') words="' + " ".join(e[0] for e in entries) + '" ;;'
                for command, entries in rows.items()]
    return (BASH.replace("@VALUE_FLAGS@", "|".join(sorted(value_flags))).replace("@PATH_FLAGS@", "|".join(sorted(path_flags)))
            .replace("@VALUES@", "\n".join(values)).replace("@COMMANDS@", "\n".join(commands))) + BASH_TAIL


def script(shell: str, build_parser) -> str:
    rows = table(build_parser)
    if shell == "powershell":
        return powershell(rows)
    return (ZSH_HEAD if shell == "zsh" else "") + bash(rows)


def script_path(shell: str, home: str) -> str:
    name = {"powershell": "discprobe-completion.ps1", "bash": ".discprobe-completion.bash", "zsh": ".discprobe-completion.zsh"}
    return os.path.join(home, name[shell])


def load_line(shell: str) -> str:
    return {"powershell": '. "$HOME\\discprobe-completion.ps1"', "bash": "source ~/.discprobe-completion.bash",
            "zsh": "source ~/.discprobe-completion.zsh"}[shell]


def installed(home: str | None = None) -> bool:
    home = home or os.path.expanduser("~")
    return any(os.path.exists(script_path(shell, home)) for shell in SHELLS)


def default_shell(env=None, platform=None) -> str | None:
    env = os.environ if env is None else env
    if (platform or sys.platform) == "win32" and not env.get("MSYSTEM"):
        return "powershell"
    name = os.path.basename(env.get("SHELL", "")).removesuffix(".exe")
    return name if name in ("bash", "zsh") else None


def powershell_targets() -> list[tuple[str, str]]:
    """(profile path, execution policy) of each PowerShell here; 5.1 and 7 keep separate profiles."""
    found = []
    for program in ("powershell", "pwsh"):
        if shutil.which(program):
            try:
                done = subprocess.run([program, "-NoProfile", "-NonInteractive", "-Command", "$PROFILE; Get-ExecutionPolicy"],
                                      capture_output=True, text=True, timeout=30)
            except (OSError, subprocess.SubprocessError):
                continue
            lines = done.stdout.splitlines()
            if len(lines) >= 2:
                found.append((lines[0].strip(), lines[1].strip()))
    return found


def _read(path: str) -> tuple[bytes, str, str]:
    """A startup file's bytes and how to edit them without damaging what is there."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        data = b""
    return (data, "utf-16-le", "surrogatepass") if data[:2] == b"\xff\xfe" else (data, "utf-8", "surrogateescape")


def add_to_startup(path: str, line: str) -> bool:
    """Add the loading line once. False if it was already there."""
    data, encoding, errors = _read(path)
    text = data.decode(encoding, errors)
    if line in text:
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    added = ("" if not text or text.endswith("\n") else "\n") + ("" if MARKER in text else f"{MARKER}\n") + f"{line}\n"
    with open(path, "ab") as f:
        f.write(added.encode(encoding, errors))
    return True


def remove_from_startup(path: str, line: str) -> bool:
    data, encoding, errors = _read(path)
    text = data.decode(encoding, errors)
    if MARKER not in text:
        return False
    kept = [x for x in text.splitlines(keepends=True) if x.strip() not in (MARKER, line)]
    with open(path, "wb") as f:
        f.write("".join(kept).encode(encoding, errors))
    return True


def _write_script(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def install(shell: str, build_parser, home: str, targets: list[tuple[str, str]]) -> list[str]:
    """Write the script and add it to each startup file that can load it; the lines to tell the person."""
    path = script_path(shell, home)
    _write_script(path, script(shell, build_parser))
    lines = [f"Wrote {path}"]
    added = 0
    for startup, policy in targets:
        if policy in BLOCKED_POLICIES:
            lines += [f"This PowerShell's execution policy is {policy}, so it would not load the script, and {startup} was left alone.",
                      "The policy is yours to decide. To allow your own scripts: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned",
                      "Then run this command again."]
            continue
        added += 1
        lines.append(f"Added to {startup}" if add_to_startup(startup, load_line(shell)) else f"Already in {startup}")
    if added:
        lines += ["This window does not have it yet. Open a new window, or run this line here first:", f"  {load_line(shell)}",
                  "Then try it: type python -m discprobe timing --s and press Tab."]
    return lines


def uninstall(shell: str, home: str, targets: list[tuple[str, str]]) -> list[str]:
    lines = []
    for startup, _ in targets:
        if remove_from_startup(startup, load_line(shell)):
            lines.append(f"Removed from {startup}")
    path = script_path(shell, home)
    if os.path.exists(path):
        os.remove(path)
        lines.append(f"Deleted {path}")
    return lines or ["Tab completion was not installed."]


def _targets(shell: str, home: str) -> list[tuple[str, str]]:
    if shell == "powershell":
        return powershell_targets()
    return [(os.path.join(home, ".bashrc" if shell == "bash" else ".zshrc"), "")]


def main(args: list[str], build_parser, stream) -> None:
    """The script goes straight to the real output, past the line-by-line translation."""
    if args and args[0] in ("install", "uninstall"):
        shell = args[1] if len(args) > 1 else default_shell()
        if shell not in SHELLS:
            print(block("completion", USAGE), file=sys.stderr)
            sys.exit(2)
        home = os.path.expanduser("~")
        lines = install(shell, build_parser, home, _targets(shell, home)) if args[0] == "install" \
            else uninstall(shell, home, _targets(shell, home))
        for line in lines:
            print(line)
    elif len(args) == 1 and args[0] in SHELLS:
        if args[0] != "powershell" and hasattr(stream, "reconfigure"):
            stream.reconfigure(newline="\n")        # Git Bash on Windows cannot read a script with CRLF
        stream.write(script(args[0], build_parser))
        stream.flush()
    elif not args or args[0] in ("-h", "--help"):
        print(block("completion", USAGE))
    else:
        print(block("completion", USAGE), file=sys.stderr)
        sys.exit(2)
