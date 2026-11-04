using System.Diagnostics;
using System.Security.Cryptography;

namespace DiscImageStudio.Cli;

/// <summary>
/// Linux burning for the command-line host, built on the system tools the
/// distro already trusts (xorriso for ISO images and media blanking, cdrdao
/// for CD CUE sheets) instead of a second in-process MMC implementation.
/// Writing is guarded twice: an explicit --yes is required, and the media
/// state is probed first — a non-blank disc is refused unless --blank was
/// given, and an unreadable state is always refused.
/// </summary>
public static class BurnCommands
{
    internal static int PrintDevices()
    {
        List<(string Node, string Vendor, string Model)> drives = EnumerateDrives("/sys/block");
        if (drives.Count == 0)
        {
            Console.WriteLine("No optical drives found.");
        }
        else
        {
            foreach ((string node, string vendor, string model) in drives)
            {
                Console.WriteLine($"{node}\t{vendor} {model}".TrimEnd());
            }
        }

        foreach (string tool in new[] { "xorriso", "cdrdao", "cdrecord" })
        {
            Console.WriteLine($"{tool}: {FindTool(tool) ?? "not found on PATH"}");
        }

        return 0;
    }

    public static List<(string Node, string Vendor, string Model)> EnumerateDrives(string sysBlockRoot)
    {
        List<(string, string, string)> drives = [];
        if (!Directory.Exists(sysBlockRoot))
        {
            return drives;
        }

        foreach (string directory in Directory.EnumerateDirectories(sysBlockRoot, "sr*").Order())
        {
            string name = Path.GetFileName(directory);
            string vendor = ReadSysfs(Path.Combine(directory, "device", "vendor"));
            string model = ReadSysfs(Path.Combine(directory, "device", "model"));
            drives.Add(("/dev/" + name, vendor, model));
        }

        return drives;
    }

    public static int Burn(string[] arguments)
        => BurnCore(arguments, Console.WriteLine, Console.Error.WriteLine);

    public static int BurnCore(
        string[] arguments, Action<string> info, Action<string> error)
    {
        string? device = FindOption(arguments, "device");
        string? image = FindOption(arguments, "image");
        string? cue = FindOption(arguments, "cue");
        string? speed = FindOption(arguments, "speed");
        bool blank = arguments.Contains("--blank", StringComparer.OrdinalIgnoreCase);
        bool verify = arguments.Contains("--verify", StringComparer.OrdinalIgnoreCase);
        bool yes = arguments.Contains("--yes", StringComparer.OrdinalIgnoreCase);
        if (device is null
            || (image is null) == (cue is null)
            || (verify && cue is not null))
        {
            error(
                "usage: burn --device /dev/srN (--image IMAGE.iso | --cue TRACK.cue) "
                + "[--blank] [--verify] [--speed N] [--yes]");
            if (verify && cue is not null)
            {
                error("--verify is only supported for ISO images.");
            }

            return 1;
        }

        string sourcePath = Path.GetFullPath(image ?? cue!);
        if (!File.Exists(sourcePath))
        {
            error($"error: source not found: {sourcePath}");
            return 1;
        }

        string mediaTool = "xorriso";
        if (FindTool(mediaTool) is null)
        {
            error("error: required tool 'xorriso' was not found on PATH.");
            return 1;
        }

        if (cue is not null && FindTool("cdrdao") is null)
        {
            error("error: required tool 'cdrdao' was not found on PATH.");
            return 1;
        }

        MediaState state = ProbeMedia(device);
        info($"device: {device}");
        info($"source: {sourcePath} ({new FileInfo(sourcePath).Length} bytes)");
        info($"media: {Describe(state)}");
        if (blank)
        {
            info("plan: blank media first (xorriso -blank as_needed)");
        }

        info(image is not null
            ? $"plan: write ISO with xorriso (cdrecord emulation, DAO)"
            : "plan: write CD track with cdrdao (DAO)");
        if (verify)
        {
            info("plan: read back and compare SHA-256 after writing");
        }

        if (!yes)
        {
            info("dry run: nothing was written. Pass --yes to burn.");
            return 0;
        }

        if (state == MediaState.Unknown)
        {
            error("error: media state could not be determined; refusing to write.");
            return 1;
        }

        if (state != MediaState.Blank && !blank)
        {
            error(
                "error: media is not blank. Pass --blank to erase rewritable media first.");
            return 1;
        }

        if (blank && state != MediaState.Blank)
        {
            int blankExit = RunTool(mediaTool, ["-outdev", device, "-blank", "as_needed"]);
            if (blankExit != 0)
            {
                error($"error: blanking failed (exit {blankExit}).");
                return blankExit;
            }
        }

        if (image is not null)
        {
            string? sizeError = CheckImageFitsMedia(device, sourcePath);
            if (sizeError is not null)
            {
                error(sizeError);
                return 5;
            }
        }

        int writeExit;
        if (image is not null)
        {
            List<string> args = ["-as", "cdrecord", $"dev={device}", "-v", "-dao"];
            if (speed is not null)
            {
                args.Add($"speed={speed}");
            }

            args.Add(sourcePath);
            writeExit = RunTool("xorriso", args);
        }
        else
        {
            List<string> args = ["write", "--device", device];
            if (speed is not null)
            {
                args.Add("--speed");
                args.Add(speed);
            }

            args.Add(sourcePath);
            writeExit = RunTool("cdrdao", args);
        }

        if (writeExit != 0)
        {
            error($"error: writing failed (exit {writeExit}).");
            return writeExit;
        }

        info("write completed.");
        if (verify && image is not null)
        {
            return VerifyIso(device, sourcePath, info, error) ? 0 : 1;
        }

        return 0;
    }

    private enum MediaState
    {
        Unknown,
        Blank,
        Written,
    }

    private static string Describe(MediaState state) => state switch
    {
        MediaState.Blank => "blank",
        MediaState.Written => "written (not blank)",
        _ => "unknown (no media or probe failed)",
    };

    // xorriso's cdrecord emulation pads the image by 150 sectors; together
    // with the formatted capacity of DVD+RW (smaller than DVD-R), an image
    // sized for a full DVD-R silently overflows rewritable media. Probe the
    // free space first and refuse with a regenerate hint instead of exit 5.
    private static string? CheckImageFitsMedia(string device, string sourcePath)
    {
        (int exit, string output) = RunToolCaptured("xorriso", ["-outdev", device, "-tell_media_space"]);
        if (exit != 0)
        {
            return null;
        }

        long freeSectors = -1;
        foreach (string line in output.Split('\n'))
        {
            if (line.Contains("Media space"))
            {
                string tail = line[(line.IndexOf(':') + 1)..].Trim().TrimEnd('s');
                if (long.TryParse(tail, out long parsed))
                {
                    freeSectors = parsed;
                }
            }
        }

        if (freeSectors < 0)
        {
            return null;
        }

        long imageSectors = (new FileInfo(sourcePath).Length + 2047) / 2048;
        const long paddingSectors = 150;
        if (imageSectors + paddingSectors <= freeSectors)
        {
            return null;
        }

        return $"error: image is too large for this media: {imageSectors} sectors + {paddingSectors} padding"
            + $" exceeds {freeSectors} free sectors. Regenerate with --total-sectors {freeSectors - paddingSectors} or less.";
    }

    private static MediaState ProbeMedia(string device)
    {
        (int exit, string output) = RunToolCaptured("xorriso", ["-indev", device, "-toc"]);
        _ = exit;
        foreach (string line in output.Split('\n'))
        {
            if (!line.Contains("Media status", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (line.Contains("is blank", StringComparison.OrdinalIgnoreCase))
            {
                return MediaState.Blank;
            }

            if (line.Contains("appendable", StringComparison.OrdinalIgnoreCase)
                || line.Contains("is written", StringComparison.OrdinalIgnoreCase)
                || line.Contains("is closed", StringComparison.OrdinalIgnoreCase))
            {
                return MediaState.Written;
            }
        }

        return MediaState.Unknown;
    }

    private static bool VerifyIso(string device, string imagePath, Action<string> info, Action<string> error)
    {
        long length = new FileInfo(imagePath).Length;
        info($"verifying {length} bytes read back from {device} ...");
        using FileStream source = File.OpenRead(imagePath);
        using FileStream disc = new(device, FileMode.Open, FileAccess.Read, FileShare.Read);
        byte[] sourceHash = SHA256.HashData(source);
        byte[] buffer = new byte[length];
        int read = 0;
        while (read < buffer.Length)
        {
            int chunk = disc.Read(buffer, read, buffer.Length - read);
            if (chunk <= 0)
            {
                break;
            }

            read += chunk;
        }

        if (read != buffer.Length)
        {
            error($"error: short read from device ({read} of {length} bytes).");
            return false;
        }

        bool match = SHA256.HashData(buffer).SequenceEqual(sourceHash);
        info(match
            ? "verify: SHA-256 match, the disc holds exactly the image bytes."
            : "verify: SHA-256 MISMATCH, the disc differs from the image.");
        return match;
    }

    private static string ReadSysfs(string path)
        => File.Exists(path) ? File.ReadAllText(path).Trim() : string.Empty;

    private static string? FindTool(string name)
    {
        string? pathVariable = Environment.GetEnvironmentVariable("PATH");
        if (pathVariable is null)
        {
            return null;
        }

        foreach (string directory in pathVariable.Split(Path.PathSeparator))
        {
            string candidate = Path.Combine(directory, name);
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private static int RunTool(string tool, IReadOnlyList<string> arguments)
    {
        ProcessStartInfo start = new(FindTool(tool) ?? tool)
        {
            UseShellExecute = false,
        };
        foreach (string argument in arguments)
        {
            start.ArgumentList.Add(argument);
        }

        using Process process = Process.Start(start)
            ?? throw new InvalidOperationException($"Failed to start {tool}.");
        process.WaitForExit();
        return process.ExitCode;
    }

    private static (int ExitCode, string Output) RunToolCaptured(
        string tool, IReadOnlyList<string> arguments)
    {
        ProcessStartInfo start = new(FindTool(tool) ?? tool)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (string argument in arguments)
        {
            start.ArgumentList.Add(argument);
        }

        using Process process = Process.Start(start)
            ?? throw new InvalidOperationException($"Failed to start {tool}.");
        string stdout = process.StandardOutput.ReadToEnd();
        string stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();
        return (process.ExitCode, stdout + stderr);
    }

    private static string? FindOption(IReadOnlyList<string> arguments, string key)
    {
        string name = "--" + key;
        string prefix = name + "=";
        for (int index = 0; index < arguments.Count; index++)
        {
            string argument = arguments[index];
            if (argument.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                return argument[prefix.Length..];
            }

            if (argument.Equals(name, StringComparison.OrdinalIgnoreCase)
                && index + 1 < arguments.Count)
            {
                return arguments[index + 1];
            }
        }

        return null;
    }
}
