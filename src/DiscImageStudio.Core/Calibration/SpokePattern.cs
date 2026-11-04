namespace DiscImageStudio.Core.Calibration;

/// <summary>
/// Settings for the spoke calibration pattern: radial spokes plus concentric
/// rings at known radii, drawn in the same image space the disc encoders
/// consume (square canvas, disc centre at the image centre, +x right,
/// +y down). Burn the pattern with a nominal geometry, measure how far the
/// spokes have rotated at each ring radius, and feed those phase errors to
/// <see cref="SpiralPhaseFitter"/> to solve for the true geometry.
/// </summary>
public sealed record SpokePatternSettings
{
    /// <summary>Canvas edge length in pixels (the canvas spans 2 × <see cref="CanvasRadiusMm"/>).</summary>
    public int Size { get; init; } = 4096;

    /// <summary>Number of equally spaced spokes (default 36, one every 10 degrees).</summary>
    public int Spokes { get; init; } = 36;

    /// <summary>Physical radius the canvas edge-to-centre distance represents.</summary>
    public double CanvasRadiusMm { get; init; } = 60.0;

    /// <summary>Stroke width of spokes and rings, in millimetres.</summary>
    public double LineWidthMm { get; init; } = 0.35;

    /// <summary>Radii of the measurement rings — the radii at which phase error is read.</summary>
    public IReadOnlyList<double> RingRadiiMm { get; init; } = [25, 30, 35, 40, 45, 50, 55];
}

/// <summary>Renders the spoke calibration pattern to a BGRA32 buffer.</summary>
public static class SpokePattern
{
    public static (byte[] Bgra, int Size) Render(SpokePatternSettings settings)
    {
        ArgumentNullException.ThrowIfNull(settings);
        int size = settings.Size;
        if (size < 64)
            throw new ArgumentOutOfRangeException(nameof(settings), "Pattern size must be at least 64 pixels.");
        if (settings.Spokes < 4)
            throw new ArgumentOutOfRangeException(nameof(settings), "At least 4 spokes are required.");
        if (!double.IsFinite(settings.CanvasRadiusMm) || settings.CanvasRadiusMm <= 0)
            throw new ArgumentOutOfRangeException(nameof(settings), "Canvas radius must be positive and finite.");
        if (settings.RingRadiiMm.Count == 0)
            throw new ArgumentOutOfRangeException(nameof(settings), "At least one measurement ring is required.");

        double centre = (size - 1) / 2.0;
        double mmPerPixel = settings.CanvasRadiusMm / centre;
        double halfLine = settings.LineWidthMm / 2.0;
        double spokeStep = 2 * Math.PI / settings.Spokes;
        double outerRing = settings.RingRadiiMm.Max();
        // Spokes run from the hub to just past the outermost measurement ring.
        double spokeReach = outerRing + 2.0;

        byte[] bgra = new byte[size * size * 4];
        for (int py = 0; py < size; py++)
        {
            double y = (py - centre) * mmPerPixel;
            for (int px = 0; px < size; px++)
            {
                double x = (px - centre) * mmPerPixel;
                double r = Math.Sqrt(x * x + y * y);
                bool ink = false;
                if (r <= settings.CanvasRadiusMm)
                {
                    foreach (double ring in settings.RingRadiiMm)
                    {
                        if (Math.Abs(r - ring) <= halfLine) { ink = true; break; }
                    }
                    if (!ink && r <= spokeReach)
                    {
                        // Angular distance to the nearest spoke, as arc length in mm.
                        double angle = Math.Atan2(y, x);
                        double offset = angle % spokeStep;
                        if (offset < 0) offset += spokeStep;
                        double arc = Math.Min(offset, spokeStep - offset) * r;
                        ink = arc <= halfLine;
                        // The 0-degree spoke (towards +x) is drawn double width as
                        // the orientation reference.
                        if (!ink && x > 0 && Math.Abs(y) <= settings.LineWidthMm)
                            ink = true;
                        // Centre cross for hub registration.
                        if (!ink && r <= 3.0 && (Math.Abs(x) <= halfLine || Math.Abs(y) <= halfLine))
                            ink = true;
                    }
                }
                int i = (py * size + px) * 4;
                byte v = ink ? (byte)0 : (byte)255;
                bgra[i] = v; bgra[i + 1] = v; bgra[i + 2] = v; bgra[i + 3] = 255;
            }
        }
        return (bgra, size);
    }
}
