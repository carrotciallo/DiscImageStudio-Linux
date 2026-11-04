using System.Buffers.Binary;
using System.IO.Compression;
using SixLabors.ImageSharp;
using SixLabors.ImageSharp.PixelFormats;
using StbImageSharp;

namespace DiscImageStudio.Core;

/// <summary>
/// Cross-platform image decode and PNG encode for the disc engines, replacing
/// the WPF imaging stack (BitmapFrame / FormatConvertedBitmap / PngBitmapEncoder).
/// Decode yields straight-alpha BGRA32 — the exact layout the WPF conversion
/// produced — and encode writes those pixels back as an 8-bit RGBA PNG, so the
/// engines' pixel math is unchanged on every platform.
/// </summary>
public static class PortableImageCodec
{
    /// <summary>Decodes the first frame of an image stream to BGRA32 pixels.</summary>
    public static (byte[] Bgra, int Width, int Height) DecodeBgra32(Stream stream)
    {
        ArgumentNullException.ThrowIfNull(stream);
        using MemoryStream buffer = new();
        stream.CopyTo(buffer);
        byte[] bytes = buffer.ToArray();
        if (IsWebP(bytes))
        {
            // stb_image ships no WebP decoder; ImageSharp covers that one format
            // and its Bgra32 layout already matches the engines' channel order.
            using Image<Bgra32> image = Image.Load<Bgra32>(bytes);
            byte[] pixels = new byte[checked(image.Width * image.Height * 4)];
            image.CopyPixelDataTo(pixels);
            return (pixels, image.Width, image.Height);
        }

        using MemoryStream input = new(bytes);
        ImageResult stbImage = ImageResult.FromStream(input, ColorComponents.RedGreenBlueAlpha);
        byte[] bgra = stbImage.Data;
        // StbImageSharp returns RGBA; the engines work in BGRA channel order.
        for (int offset = 0; offset + 3 < bgra.Length; offset += 4)
        {
            (bgra[offset], bgra[offset + 2]) = (bgra[offset + 2], bgra[offset]);
        }

        return (bgra, stbImage.Width, stbImage.Height);
    }

    private static bool IsWebP(ReadOnlySpan<byte> bytes)
        => bytes.Length >= 12
           && bytes[..4].SequenceEqual("RIFF"u8)
           && bytes.Slice(8, 4).SequenceEqual("WEBP"u8);

    /// <summary>Writes tightly packed BGRA32 pixels (stride = width * 4) as a PNG.</summary>
    public static void WritePngBgra32(Stream output, ReadOnlySpan<byte> bgra, int width, int height)
        => WritePngBgra32(output, bgra, width, height, checked(width * 4));

    /// <summary>Writes BGRA32 pixels with an explicit row stride as a PNG.</summary>
    public static void WritePngBgra32(
        Stream output, ReadOnlySpan<byte> bgra, int width, int height, int stride)
    {
        ArgumentNullException.ThrowIfNull(output);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(width);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(height);
        if (stride < width * 4)
        {
            throw new ArgumentException("Stride is smaller than one BGRA row.", nameof(stride));
        }

        if (bgra.Length < (long)stride * height)
        {
            throw new ArgumentException("Pixel buffer is smaller than stride * height.", nameof(bgra));
        }

        // Raw scanlines: one filter byte (0 = None) per row, RGBA channel order.
        byte[] raw = new byte[checked((width * 4 + 1) * height)];
        for (int y = 0; y < height; y++)
        {
            int sourceRow = y * stride;
            int targetRow = y * (width * 4 + 1);
            for (int x = 0; x < width; x++)
            {
                int source = sourceRow + x * 4;
                int target = targetRow + 1 + x * 4;
                raw[target] = bgra[source + 2];
                raw[target + 1] = bgra[source + 1];
                raw[target + 2] = bgra[source];
                raw[target + 3] = bgra[source + 3];
            }
        }

        using MemoryStream compressed = new();
        using (ZLibStream zlib = new(compressed, CompressionLevel.Optimal, leaveOpen: true))
        {
            zlib.Write(raw);
        }

        output.Write([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
        Span<byte> header = stackalloc byte[13];
        BinaryPrimitives.WriteInt32BigEndian(header, width);
        BinaryPrimitives.WriteInt32BigEndian(header[4..], height);
        header[8] = 8; // bit depth
        header[9] = 6; // color type RGBA; compression/filter/interlace stay 0
        WriteChunk(output, "IHDR", header);
        WriteChunk(output, "IDAT", compressed.ToArray());
        WriteChunk(output, "IEND", []);
    }

    private static void WriteChunk(Stream output, string type, ReadOnlySpan<byte> data)
    {
        Span<byte> word = stackalloc byte[4];
        BinaryPrimitives.WriteInt32BigEndian(word, data.Length);
        output.Write(word);
        byte[] typeBytes = System.Text.Encoding.ASCII.GetBytes(type);
        output.Write(typeBytes);
        output.Write(data);
        uint crc = 0xFFFFFFFFu;
        foreach (byte value in typeBytes)
        {
            crc = UpdateCrc(crc, value);
        }

        foreach (byte value in data)
        {
            crc = UpdateCrc(crc, value);
        }

        BinaryPrimitives.WriteUInt32BigEndian(word, crc ^ 0xFFFFFFFFu);
        output.Write(word);
    }

    private static uint UpdateCrc(uint crc, byte value)
    {
        uint next = (crc ^ value) & 0xFF;
        for (int bit = 0; bit < 8; bit++)
        {
            next = (next & 1) != 0 ? 0xEDB88320u ^ (next >> 1) : next >> 1;
        }

        return (crc >> 8) ^ next;
    }
}
