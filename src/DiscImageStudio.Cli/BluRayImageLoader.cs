using System.IO;
using DiscImageStudio.BluRay;
using DiscImageStudio.Core;

namespace DiscImageStudio.Cli;

/// <summary>
/// Loads an image as a Blu-ray Gray8 raster. This is the command-line twin of
/// the App's Services.BluRayImageLoader default (no tone profile) path: same
/// resource limits, encoded-space Rec. 709 weights and straight-alpha-over-white
/// compositing, with the portable decoder standing in for WPF imaging.
/// </summary>
public static class BluRayImageLoader
{
    private const long MaxFileBytes = 256L * 1024 * 1024;
    private const long MaxPixels = 64L * 1024 * 1024;

    public static BluRayGray8Raster Load(string path, CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        cancellationToken.ThrowIfCancellationRequested();
        using FileStream stream = new(Path.GetFullPath(path), FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > MaxFileBytes)
        {
            throw new ArgumentException("The source image must be no larger than 256 MiB.", nameof(path));
        }

        (byte[] bgra, int width, int height) = PortableImageCodec.DecodeBgra32(stream);
        if (width <= 0 || height <= 0 || (long)width * height > MaxPixels)
        {
            throw new ArgumentException(
                "The source image must contain between 1 and 67,108,864 pixels.", nameof(path));
        }

        byte[] gray = new byte[checked(width * height)];
        for (int y = 0; y < height; y++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            for (int x = 0; x < width; x++)
            {
                int pixel = y * width + x;
                int offset = pixel * 4;
                int weighted = 2126 * bgra[offset + 2] + 7152 * bgra[offset + 1] + 722 * bgra[offset];
                int alpha = bgra[offset + 3];
                gray[pixel] = (byte)((weighted * alpha + 2_550_000 * (255 - alpha) + 1_275_000) / 2_550_000);
            }
        }

        cancellationToken.ThrowIfCancellationRequested();
        return new(width, height, gray);
    }
}
