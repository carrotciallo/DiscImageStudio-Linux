namespace DiscImageStudio.Core.Calibration;

// The fit below follows the calibration derivation published in
// Isoheptane/discscape (MIT License), fitter_notes.md: with the spiral
// described by (r0, p, N), the Jacobians of the unwrapped revolution count
// n at a fixed normalized spiral position are
//   u = dn/dN = x * (r0 + pN) / r
//   v = dn/dp = (N * u - n) / p        where x = (r^2 - r0^2) / (rEnd^2 - r0^2)
// A pivot measurement is matched exactly; pitch is solved by least squares
// over the remaining measurements, then N follows from the pivot.
// Re-implemented here from that published math.

/// <summary>
/// A constant-pitch Archimedean spiral geometry: inner radius
/// <paramref name="InnerRadiusMm"/>, radial pitch per revolution
/// <paramref name="PitchMmPerRev"/>, and total revolution count
/// <paramref name="Revolutions"/>.
/// </summary>
public sealed record SpiralGeometrySpec(double InnerRadiusMm, double PitchMmPerRev, double Revolutions)
{
    public double OuterRadiusMm => InnerRadiusMm + PitchMmPerRev * Revolutions;

    /// <summary>Exact Archimedean arc length of the spiral, in millimetres.</summary>
    public double TrackLengthMm
    {
        get
        {
            double g = PitchMmPerRev / (2 * Math.PI);
            static double Primitive(double r, double g)
                => (r * Math.Sqrt(r * r + g * g) + g * g * Math.Asinh(r / g)) / (2 * g);
            return Primitive(OuterRadiusMm, g) - Primitive(InnerRadiusMm, g);
        }
    }

    /// <summary>Unwrapped revolution count from the inner radius out to <paramref name="radiusMm"/>.</summary>
    public double RevolutionsAtRadius(double radiusMm) => (radiusMm - InnerRadiusMm) / PitchMmPerRev;

    /// <summary>Normalized spiral position (0 at the inner radius, 1 at the outer radius).</summary>
    public double NormalizedPositionAtRadius(double radiusMm)
        => (radiusMm * radiusMm - InnerRadiusMm * InnerRadiusMm)
           / (OuterRadiusMm * OuterRadiusMm - InnerRadiusMm * InnerRadiusMm);
}

/// <summary>
/// One spoke phase measurement: at <paramref name="RadiusMm"/> the burned spoke
/// appears rotated by <paramref name="PhaseErrorDeg"/> degrees relative to the
/// ideal radial direction, viewed from the data side, clockwise positive.
/// </summary>
public sealed record PhaseSample(double RadiusMm, double PhaseErrorDeg);

/// <summary>Outcome of a spoke phase fit: the corrected geometry plus diagnostics.</summary>
public sealed record SpiralFitResult(
    SpiralGeometrySpec Corrected,
    double DeltaPitchMmPerRev,
    double DeltaRevolutions,
    IReadOnlyList<double> ResidualPhaseDeg,
    double RmsBeforeDeg,
    double RmsAfterDeg);

/// <summary>
/// Solves for the true spiral geometry from spoke phase measurements taken on
/// a disc burned with a nominal geometry. The corrected geometry's unwrapped
/// revolution count reproduces the measured phase error exactly at the pivot
/// radius and in the least-squares sense at the other measured radii; the
/// leftover residuals are the phase-correction samples for any remaining
/// radius-dependent error.
/// </summary>
public static class SpiralPhaseFitter
{
    public static SpiralFitResult Fit(
        SpiralGeometrySpec current,
        IReadOnlyList<PhaseSample> samples,
        double? pivotRadiusMm = null)
    {
        ArgumentNullException.ThrowIfNull(current);
        ArgumentNullException.ThrowIfNull(samples);
        if (!double.IsFinite(current.PitchMmPerRev) || current.PitchMmPerRev <= 0)
            throw new ArgumentOutOfRangeException(nameof(current), "Pitch must be positive and finite.");
        if (!double.IsFinite(current.Revolutions) || current.Revolutions <= 0)
            throw new ArgumentOutOfRangeException(nameof(current), "Revolution count must be positive and finite.");
        if (samples.Count < 2)
            throw new ArgumentException("At least two phase samples are required.", nameof(samples));

        double r0 = current.InnerRadiusMm, p = current.PitchMmPerRev, n = current.Revolutions;
        double rEnd = current.OuterRadiusMm;
        int count = samples.Count;
        double[] u = new double[count], v = new double[count], e = new double[count];
        for (int i = 0; i < count; i++)
        {
            double r = samples[i].RadiusMm;
            if (!double.IsFinite(r) || r <= r0 || r > rEnd)
                throw new ArgumentOutOfRangeException(nameof(samples),
                    $"Sample radius {r} mm lies outside the data ring ({r0} .. {rEnd} mm).");
            double x = current.NormalizedPositionAtRadius(r);
            double ni = current.RevolutionsAtRadius(r);
            u[i] = x * (r0 + p * n) / r;
            v[i] = (n * u[i] - ni) / p;
            e[i] = samples[i].PhaseErrorDeg / 360.0;
        }

        int pivot = 0;
        double pivotTarget = pivotRadiusMm ?? samples.Max(s => s.RadiusMm);
        double best = double.MaxValue;
        for (int i = 0; i < count; i++)
        {
            double d = Math.Abs(samples[i].RadiusMm - pivotTarget);
            if (d < best) { best = d; pivot = i; }
        }
        if (Math.Abs(u[pivot]) < 1e-12)
            throw new InvalidOperationException("Pivot sample carries no revolution-count sensitivity; choose a pivot at a larger radius.");

        double sumAA = 0, sumAB = 0;
        for (int i = 0; i < count; i++)
        {
            if (i == pivot) continue;
            double a = v[i] - u[i] * v[pivot] / u[pivot];
            double b = e[i] - u[i] * e[pivot] / u[pivot];
            sumAA += a * a;
            sumAB += a * b;
        }
        if (sumAA < 1e-18)
            throw new InvalidOperationException("Phase samples do not constrain the pitch (radii too close together).");
        double deltaP = sumAB / sumAA;
        double deltaN = (e[pivot] - v[pivot] * deltaP) / u[pivot];

        double correctedP = p + deltaP;
        double correctedN = n + deltaN;
        if (correctedP <= 0 || correctedN <= 0)
            throw new InvalidOperationException("Fit produced a non-positive pitch or revolution count; measurements are inconsistent with the nominal geometry.");

        double[] residuals = new double[count];
        double sumBefore = 0, sumAfter = 0;
        for (int i = 0; i < count; i++)
        {
            residuals[i] = (e[i] - (u[i] * deltaN + v[i] * deltaP)) * 360.0;
            sumBefore += e[i] * e[i];
            double residualRev = residuals[i] / 360.0;
            sumAfter += residualRev * residualRev;
        }
        var corrected = new SpiralGeometrySpec(r0, correctedP, correctedN);
        return new SpiralFitResult(
            corrected,
            deltaP,
            deltaN,
            residuals,
            Math.Sqrt(sumBefore / count) * 360.0,
            Math.Sqrt(sumAfter / count) * 360.0);
    }
}
