using DiscImageStudio.BluRay;
using DiscImageStudio.Cd;
using DiscImageStudio.Core;
using DiscImageStudio.Dvd;

namespace DiscImageStudio.Cli;

/// <summary>
/// Command-line host for the disc generation modules. This mirrors the App's
/// UnifiedCommandRunner disc-command path — same DiscModuleCatalog, arguments,
/// progress reporting and exit codes — without the GUI and IMAPI2 commands.
/// </summary>
internal static class Program
{
    private static readonly DiscModuleCatalog Modules = new(
    [
        new CdDiscModule(),
        new DvdDiscModule(),
        new BluRayDiscModule((path, token) => BluRayImageLoader.Load(path, token)),
    ]);

    private static int Main(string[] arguments)
    {
        try
        {
            if (arguments.Length == 0)
            {
                return PrintHelp();
            }

            string command = arguments[0].ToLowerInvariant();
            if (command is "help" or "--help" or "-h")
            {
                return PrintHelp();
            }

            if (command == "burn-devices")
            {
                return BurnCommands.PrintDevices();
            }

            if (command == "burn")
            {
                return BurnCommands.Burn(arguments.Skip(1).ToArray());
            }

            if (command == "calibrate-spoke")
            {
                return CalibrateCommands.Spoke(arguments.Skip(1).ToArray());
            }

            if (command == "calibrate-fit")
            {
                return CalibrateCommands.Fit(arguments.Skip(1).ToArray());
            }

            if (command == "calibrate-selftest")
            {
                return CalibrateCommands.SelfTest();
            }

            DiscJobRequest request = new(command, arguments.Skip(1));
            ImmediateProgress progress = new(value =>
            {
                if (!string.IsNullOrWhiteSpace(value.Message))
                {
                    Console.WriteLine(value.Message);
                }
            });
            using CancellationTokenSource cancellation = new();
            bool supportsCancellation = Modules.Resolve(command).Descriptor.SupportsCancellation;
            ConsoleCancelEventHandler cancelHandler = (_, e) =>
            {
                if (!supportsCancellation) return;
                e.Cancel = true;
                cancellation.Cancel();
            };
            DiscJobResult result;
            Console.CancelKeyPress += cancelHandler;
            try
            {
                result = Modules.ExecuteAsync(request, progress, cancellation.Token).GetAwaiter().GetResult();
            }
            finally
            {
                Console.CancelKeyPress -= cancelHandler;
            }

            if (!string.IsNullOrWhiteSpace(result.Summary))
            {
                Console.WriteLine(result.Summary);
            }

            return result.ExitCode;
        }
        catch (OperationCanceledException)
        {
            Console.Error.WriteLine("Cancelled.");
            return 130;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"error: {exception}");
            return 1;
        }
    }

    private static int PrintHelp()
    {
        Console.WriteLine(
            """
            Disc Image Studio - modular CD/DVD/Blu-ray optical-disc image generator

            Disc commands are provided by modules through DiscImageStudio.Core.
            """);
        foreach (IOpticalDiscModule module in Modules.Modules)
        {
            Console.WriteLine($"\n{module.Descriptor.DisplayName} [{module.Descriptor.Id}]");
            foreach (DiscCommandDescriptor command in module.Descriptor.Commands)
            {
                Console.WriteLine($"  {command.Name,-20} {command.Description}");
            }
        }

        Console.WriteLine(
            """

            Host commands (Linux burning):
              burn-devices        List optical drives and the burning tools on PATH.
              burn --device /dev/srN --image IMAGE.iso [--blank] [--verify] [--speed N] [--yes]
              burn --device /dev/srN --cue TRACK.cue [--blank] [--speed N] [--yes]
                                  Without --yes, burn only probes the media and prints
                                  the plan; nothing is written.
              calibrate-spoke --output spoke.png [--size 4096] [--spokes 36] [--rings 25,30,...]
                                  Render the spoke calibration pattern (spokes plus
                                  measurement rings) as a PNG source image.
              calibrate-fit --samples "25:-11.1,30:-51.8,..." [--pitch-um 0.74] [--outer-mm 58]
                                  Fit the true spiral geometry (pitch, revolutions)
                                  from spoke phase errors measured on a burned disc.
              calibrate-selftest  Run the spoke calibration checks.

            Blu-ray: bd-info exports parameters; bd-probe exports raw payload tests;
            bd-encode exports one ECC cluster; bd-generate maps dark to 3T and light to 6T run-count bias.
              bd-generate --input IMAGE.png --output PICTURE.iso [--invert true]
                          [--total-sectors 12219392] [--data-dir FOLDER] [--volume-label BD_IMAGE]
                          [--tone-dither 0..1] [--tone-brightness -64..64] [--tone-gamma true]
            Total sectors must align to 32. Output is a complete ISO9660/Joliet image:
            inner files first, followed by picture data. Press Ctrl+C to cancel.
            See docs/ADDING_BLURAY.md for options and physical-model limitations.
            """);
        return 0;
    }

    private sealed class ImmediateProgress(Action<DiscJobProgress> report)
        : IProgress<DiscJobProgress>
    {
        public void Report(DiscJobProgress value) => report(value);
    }
}
