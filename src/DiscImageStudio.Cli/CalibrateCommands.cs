using System.Globalization;
using DiscImageStudio.Core;
using DiscImageStudio.Core.Calibration;

namespace DiscImageStudio.Cli;

/// <summary>
/// Spoke calibration host commands: render the spoke test pattern, then fit a
/// corrected spiral geometry from phase errors measured on the burned disc.
/// Workflow: calibrate-spoke -> solve/burn the pattern with a nominal
/// geometry -> measure spoke rotation at each ring radius -> calibrate-fit.
/// </summary>
internal static class CalibrateCommands
{
    public static int Spoke(string[] arguments)
    {
        string? output = GetOption(arguments, "--output");
        if (output is null)
        {
            Console.Error.WriteLine(
                "usage: calibrate-spoke --output spoke.png [--size 4096] [--spokes 36] " +
                "[--canvas-mm 60] [--line-mm 0.35] [--rings 25,30,35,40,45,50,55]");
            return 2;
        }
        var settings = new SpokePatternSettings
        {
            Size = GetInt(arguments, "--size", 4096),
            Spokes = GetInt(arguments, "--spokes", 36),
            CanvasRadiusMm = GetDouble(arguments, "--canvas-mm", 60.0),
            LineWidthMm = GetDouble(arguments, "--line-mm", 0.35),
            RingRadiiMm = GetDoubleList(arguments, "--rings") ?? new SpokePatternSettings().RingRadiiMm,
        };
        var (bgra, size) = SpokePattern.Render(settings);
        using (FileStream stream = File.Create(output))
        {
            PortableImageCodec.WritePngBgra32(stream, bgra, size, size);
        }
        Console.WriteLine($"spoke pattern: {Path.GetFullPath(output)}");
        Console.WriteLine($"  {size}x{size}px, {settings.Spokes} spokes, rings at " +
            string.Join(", ", settings.RingRadiiMm.Select(r => F(r, "0.#"))) + " mm");
        Console.WriteLine("  burn it with the nominal geometry, then measure each spoke's " +
            "angular offset at the rings and run calibrate-fit.");
        return 0;
    }

    public static int Fit(string[] arguments)
    {
        string? samplesText = GetOption(arguments, "--samples");
        if (samplesText is null)
        {
            Console.Error.WriteLine(
                "usage: calibrate-fit --samples \"25:-11.1,30:-51.8,...\" [--inner-mm 24] " +
                "[--pitch-um 0.74] [--outer-mm 58 | --revolutions N] [--pivot-mm 55] [--channel-bit-nm 133.3]");
            return 2;
        }
        double inner = GetDouble(arguments, "--inner-mm", 24.0);
        double pitchMm = GetDouble(arguments, "--pitch-um", 0.74) / 1000.0;
        double revolutions = GetOption(arguments, "--revolutions") is { } revText
            ? ParseDouble(revText, "--revolutions")
            : (GetDouble(arguments, "--outer-mm", 58.0) - inner) / pitchMm;
        var nominal = new SpiralGeometrySpec(inner, pitchMm, revolutions);
        var samples = ParseSamples(samplesText);
        double? pivot = GetOption(arguments, "--pivot-mm") is { } pivotText
            ? ParseDouble(pivotText, "--pivot-mm")
            : null;

        SpiralFitResult result = SpiralPhaseFitter.Fit(nominal, samples, pivot);
        SpiralGeometrySpec fit = result.Corrected;

        Console.WriteLine("nominal geometry:");
        PrintGeometry(nominal);
        Console.WriteLine("samples (measured -> residual after fit):");
        for (int i = 0; i < samples.Count; i++)
        {
            Console.WriteLine($"  r={F(samples[i].RadiusMm, "0.0")} mm  {FS(samples[i].PhaseErrorDeg, "0.00")} deg" +
                $"  ->  {FS(result.ResidualPhaseDeg[i], "0.000")} deg");
        }
        Console.WriteLine($"fit: dPitch={FS(result.DeltaPitchMmPerRev * 1000, "0.000000")} um, " +
            $"dRevolutions={FS(result.DeltaRevolutions, "0.00")}");
        Console.WriteLine($"RMS phase error: {F(result.RmsBeforeDeg, "0.00")} deg -> {F(result.RmsAfterDeg, "0.00")} deg");
        Console.WriteLine("corrected geometry:");
        PrintGeometry(fit);

        double channelBitNm = GetDouble(arguments, "--channel-bit-nm", 133.3);
        double mmPerSector = CalibrationParameters.DvdChannelBitsPerSector * channelBitNm * 1e-6;
        long sectors = (long)Math.Round(fit.TrackLengthMm / mmPerSector);
        Console.WriteLine($"suggested total sectors (DVD, estimate): {sectors}");
        Console.WriteLine("preset snippet:");
        Console.WriteLine("  { \"id\": \"fitted-dvd\", \"displayName\": \"Spoke-fitted DVD\",");
        Console.WriteLine($"    \"totalSectors\": {sectors}, \"innerRadiusMm\": {F(fit.InnerRadiusMm, "0.###")}, " +
            $"\"outerRadiusMm\": {F(fit.OuterRadiusMm, "0.###")}, \"channelBitLengthNm\": {F(channelBitNm, "0.0")} }}");
        Console.WriteLine("note: this port's DVD encoder drives geometry from total sectors and a " +
            "pitch distribution; use the fitted pitch/revolutions as the calibration " +
            "record and starting point for per-media presets.");
        return 0;
    }

    public static int SelfTest()
    {
        int failures = 0;
        void Check(string name, bool ok, string detail = "")
        {
            Console.WriteLine($"{(ok ? "PASS" : "FAIL")} {name}{(ok ? "" : $": {detail}")}");
            if (!ok) failures++;
        }

        // Recovery: synthesize measurements from a known perturbed geometry
        // through the exact nonlinear forward model, then require the
        // linearized fitter to recover that geometry.
        var nominal = new SpiralGeometrySpec(24.0, 0.00074, 46000.0);
        var truth = new SpiralGeometrySpec(24.0, 0.0007418, 45982.0);
        static double RevAt(SpiralGeometrySpec g, double x)
        {
            double r = Math.Sqrt(g.InnerRadiusMm * g.InnerRadiusMm
                + x * (g.OuterRadiusMm * g.OuterRadiusMm - g.InnerRadiusMm * g.InnerRadiusMm));
            return (r - g.InnerRadiusMm) / g.PitchMmPerRev;
        }
        var samples = new List<PhaseSample>();
        foreach (double r in new[] { 25.0, 30, 35, 40, 45, 50, 55 })
        {
            double x = nominal.NormalizedPositionAtRadius(r);
            samples.Add(new PhaseSample(r, (RevAt(truth, x) - RevAt(nominal, x)) * 360.0));
        }
        SpiralFitResult fit = SpiralPhaseFitter.Fit(nominal, samples);
        double pitchError = Math.Abs(fit.Corrected.PitchMmPerRev - truth.PitchMmPerRev) / truth.PitchMmPerRev;
        double revError = Math.Abs(fit.Corrected.Revolutions - truth.Revolutions) / truth.Revolutions;
        Check("fitter recovers pitch", pitchError < 0.005, $"relative error {pitchError:P2}");
        Check("fitter recovers revolutions", revError < 0.005, $"relative error {revError:P2}");
        Check("pivot residual is zero", Math.Abs(fit.ResidualPhaseDeg[^1]) < 1e-6,
            $"pivot residual {fit.ResidualPhaseDeg[^1]} deg");
        Check("fit reduces RMS", fit.RmsAfterDeg < fit.RmsBeforeDeg * 0.25,
            $"RMS {fit.RmsBeforeDeg} -> {fit.RmsAfterDeg}");

        // Pattern: sample the rendered buffer at known disc coordinates.
        var settings = new SpokePatternSettings { Size = 512 };
        var (bgra, size) = SpokePattern.Render(settings);
        double centre = (size - 1) / 2.0;
        double mmPerPixel = settings.CanvasRadiusMm / centre;
        bool InkAt(double xMm, double yMm)
        {
            int px = (int)Math.Round(centre + xMm / mmPerPixel);
            int py = (int)Math.Round(centre + yMm / mmPerPixel);
            return bgra[(py * size + px) * 4] == 0;
        }
        Check("spoke at 0 deg is inked", InkAt(40, 0));
        Check("ring at 40 mm is inked", InkAt(40 * Math.Cos(5 * Math.PI / 180), 40 * Math.Sin(5 * Math.PI / 180)));
        Check("gap between spokes is blank", !InkAt(42.5 * Math.Cos(5 * Math.PI / 180), 42.5 * Math.Sin(5 * Math.PI / 180)));

        Console.WriteLine(failures == 0 ? "calibrate selftest: all checks passed" : $"calibrate selftest: {failures} check(s) FAILED");
        return failures == 0 ? 0 : 1;
    }

    private static void PrintGeometry(SpiralGeometrySpec g)
    {
        Console.WriteLine($"  r0={F(g.InnerRadiusMm, "0.###")} mm, pitch={F(g.PitchMmPerRev * 1000, "0.000000")} um, " +
            $"revolutions={F(g.Revolutions, "0.00")}, outer={F(g.OuterRadiusMm, "0.###")} mm, " +
            $"track length={F(g.TrackLengthMm, "0")} mm");
    }

    private static List<PhaseSample> ParseSamples(string text)
    {
        var samples = new List<PhaseSample>();
        foreach (string part in text.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            string[] pair = part.Split(':', 2);
            if (pair.Length != 2)
                throw new ArgumentException($"sample '{part}' is not in radius:degrees form.");
            samples.Add(new PhaseSample(ParseDouble(pair[0], "sample radius"), ParseDouble(pair[1], "sample degrees")));
        }
        return samples;
    }

    private static string? GetOption(string[] arguments, string name)
    {
        for (int i = 0; i < arguments.Length - 1; i++)
        {
            if (string.Equals(arguments[i], name, StringComparison.OrdinalIgnoreCase))
                return arguments[i + 1];
        }
        return null;
    }

    private static double GetDouble(string[] arguments, string name, double fallback)
        => GetOption(arguments, name) is { } text ? ParseDouble(text, name) : fallback;

    private static int GetInt(string[] arguments, string name, int fallback)
        => GetOption(arguments, name) is { } text
            ? int.Parse(text, CultureInfo.InvariantCulture)
            : fallback;

    private static List<double>? GetDoubleList(string[] arguments, string name)
        => GetOption(arguments, name) is { } text
            ? text.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                  .Select(part => ParseDouble(part, name)).ToList()
            : null;

    private static double ParseDouble(string text, string name)
        => double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out double value)
            ? value
            : throw new ArgumentException($"value '{text}' for {name} is not a number.");

    private static string F(double value, string format) => value.ToString(format, CultureInfo.InvariantCulture);

    /// <summary>Formats with an explicit + sign; values that round to zero print as +0.</summary>
    private static string FS(double value, string format)
    {
        int decimals = format.Length - format.IndexOf('.') - 1;
        double rounded = Math.Round(value, decimals);
        if (rounded == 0) return "+" + 0.0.ToString(format, CultureInfo.InvariantCulture);
        return (rounded > 0 ? "+" : "") + rounded.ToString(format, CultureInfo.InvariantCulture);
    }
}
