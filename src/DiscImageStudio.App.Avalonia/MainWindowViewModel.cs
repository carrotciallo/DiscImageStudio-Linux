using System.Collections.ObjectModel;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using DiscImageStudio.BluRay;
using DiscImageStudio.Cd;
using DiscImageStudio.Cli;
using DiscImageStudio.Core;
using DiscImageStudio.Dvd;

namespace DiscImageStudio.Gui;

/// <summary>
/// Avalonia front-end over the same module catalog as the command-line host:
/// generation and preview jobs run through DiscModuleCatalog, and burning is
/// delegated to the CLI host's BurnCommands so the tool invocations and the
/// media-safety gates exist exactly once. This covers the core loop
/// (image → generate → readback preview → burn); the WPF app's project-file
/// and calibration-session workspaces are not replicated here.
/// </summary>
public partial class MainWindowViewModel : ObservableObject
{
    private static readonly DiscModuleCatalog Modules = new(
    [
        new CdDiscModule(),
        new DvdDiscModule(),
        new BluRayDiscModule((path, token) => BluRayImageLoader.Load(path, token)),
    ]);

    private CancellationTokenSource? _jobCancellation;

    [ObservableProperty]
    private string _imagePath = string.Empty;

    [ObservableProperty]
    private int _discTypeIndex = 1;

    [ObservableProperty]
    private string _cdOutput = Path.Combine(Environment.CurrentDirectory, "disc.wav");

    [ObservableProperty]
    private string _dvdSectors = "2297888";

    [ObservableProperty]
    private string _dvdOutput = Path.Combine(Environment.CurrentDirectory, "disc.iso");

    [ObservableProperty]
    private double _dvdToneDitherPercent = 75;

    [ObservableProperty]
    private double _dvdToneBrightness;

    [ObservableProperty]
    private string _bdSectors = "12219392";

    [ObservableProperty]
    private string _bdOutput = Path.Combine(Environment.CurrentDirectory, "disc-bd.iso");

    [ObservableProperty]
    private bool _isBusy;

    [ObservableProperty]
    private string _logText = string.Empty;

    [ObservableProperty]
    private string _statusText = "就绪";

    [ObservableProperty]
    private string _innerRadiusMm = "24";

    [ObservableProperty]
    private string _outerRadiusMm = "58";

    [ObservableProperty]
    private Bitmap? _sourcePreview;

    [ObservableProperty]
    private Bitmap? _resultPreview;

    [ObservableProperty]
    private string _burnSource = string.Empty;

    [ObservableProperty]
    private int _selectedDriveIndex = -1;

    [ObservableProperty]
    private bool _burnBlank;

    [ObservableProperty]
    private bool _burnVerify;

    [ObservableProperty]
    private bool _burnReallyWrite;

    [ObservableProperty]
    private string _burnLogText = string.Empty;

    [ObservableProperty]
    private string _designImagePath = string.Empty;

    [ObservableProperty]
    private Bitmap? _designBitmap;

    [ObservableProperty]
    private double _designTranslateXMm;

    [ObservableProperty]
    private double _designTranslateYMm;

    [ObservableProperty]
    private double _designScale = 1.0;

    [ObservableProperty]
    private double _designRotationDeg;

    /// <summary>Layer size at scale 1.0 in millimetres: at import, the image's larger
    /// dimension spans the content ring diameter (2 x 58 mm), mirroring the WPF app.</summary>
    public double DesignBaseWidthMm { get; private set; }

    public double DesignBaseHeightMm { get; private set; }

    // The design surface shows 120 mm across 480 px, i.e. 4 px per mm.
    public double DesignDisplayWidth => DesignBaseWidthMm * DesignScale * 4.0;

    public double DesignDisplayHeight => DesignBaseHeightMm * DesignScale * 4.0;

    public double DesignDisplayLeft => 240.0 + DesignTranslateXMm * 4.0 - DesignDisplayWidth / 2.0;

    public double DesignDisplayTop => 240.0 + DesignTranslateYMm * 4.0 - DesignDisplayHeight / 2.0;

    public double DesignScalePercent
    {
        get => DesignScale * 100.0;
        set => DesignScale = Math.Clamp(value, 5.0, 800.0) / 100.0;
    }

    partial void OnDesignScaleChanged(double value)
    {
        OnPropertyChanged(nameof(DesignScalePercent));
        RaiseDesignLayout();
    }

    partial void OnDesignTranslateXMmChanged(double value) => RaiseDesignLayout();

    partial void OnDesignTranslateYMmChanged(double value) => RaiseDesignLayout();

    private void RaiseDesignLayout()
    {
        OnPropertyChanged(nameof(DesignDisplayWidth));
        OnPropertyChanged(nameof(DesignDisplayHeight));
        OnPropertyChanged(nameof(DesignDisplayLeft));
        OnPropertyChanged(nameof(DesignDisplayTop));
    }

    /// <summary>Loads the design-page image and resets its placement.</summary>
    public void LoadDesignImage(string path)
    {
        DesignImagePath = path;
        DesignBitmap = LoadBitmap(path);
        if (DesignBitmap is null)
        {
            DesignBaseWidthMm = 0;
            DesignBaseHeightMm = 0;
        }
        else
        {
            double width = DesignBitmap.PixelSize.Width;
            double height = DesignBitmap.PixelSize.Height;
            double mmPerPixel = 116.0 / Math.Max(width, height);
            DesignBaseWidthMm = width * mmPerPixel;
            DesignBaseHeightMm = height * mmPerPixel;
        }

        DesignTranslateXMm = 0;
        DesignTranslateYMm = 0;
        DesignScale = 1.0;
        DesignRotationDeg = 0;
        RaiseDesignLayout();
    }

    [RelayCommand]
    private void ResetDesign()
    {
        DesignTranslateXMm = 0;
        DesignTranslateYMm = 0;
        DesignScale = 1.0;
        DesignRotationDeg = 0;
    }

    [RelayCommand]
    private void FitDesign()
    {
        if (DesignBaseWidthMm <= 0 || DesignBaseHeightMm <= 0)
        {
            return;
        }

        // Cover the whole 120 mm disc square with the image's smaller side.
        DesignScale = 120.0 / Math.Min(DesignBaseWidthMm, DesignBaseHeightMm);
        DesignTranslateXMm = 0;
        DesignTranslateYMm = 0;
    }

    public ObservableCollection<string> DriveItems { get; } = [];

    private readonly List<string> _driveNodes = [];

    public bool IsCd => DiscTypeIndex == 0;

    public bool IsDvd => DiscTypeIndex == 1;

    public bool IsBd => DiscTypeIndex == 2;

    partial void OnDiscTypeIndexChanged(int value)
    {
        OnPropertyChanged(nameof(IsCd));
        OnPropertyChanged(nameof(IsDvd));
        OnPropertyChanged(nameof(IsBd));
    }

    partial void OnImagePathChanged(string value)
    {
        SourcePreview = LoadBitmap(value);
    }

    public MainWindowViewModel()
    {
        RefreshDrives();
    }

    [RelayCommand]
    private async Task GenerateAsync()
    {
        if (string.IsNullOrWhiteSpace(ImagePath) || !File.Exists(ImagePath))
        {
            AppendLog("error: 先选择一个存在的源图像文件。");
            return;
        }

        (string command, string[] args) = DiscTypeIndex switch
        {
            0 => ("cd-generate", new string[] { "--input", ImagePath, "--output", CdOutput }),
            2 => ("bd-generate", new string[] { "--input", ImagePath, "--output", BdOutput, "--total-sectors", BdSectors }),
            _ => ("solve", new string[] { "--image", ImagePath, "--iso-output", DvdOutput, "--total-sectors", DvdSectors,
                    "--tone-dither", (DvdToneDitherPercent / 100.0).ToString("0.00", System.Globalization.CultureInfo.InvariantCulture),
                    "--tone-brightness", DvdToneBrightness.ToString("0", System.Globalization.CultureInfo.InvariantCulture) }),
        };
        int exit = await RunJobAsync(command, args);
        if (exit == 0)
        {
            // Hand the produced file straight to the burn page: the CUE for CD
            // audio, the ISO for DVD / BD.
            string produced = DiscTypeIndex switch
            {
                0 => Path.ChangeExtension(Path.GetFullPath(CdOutput), ".cue"),
                2 => Path.GetFullPath(BdOutput),
                _ => Path.GetFullPath(DvdOutput),
            };
            if (File.Exists(produced))
            {
                BurnSource = produced;
                AppendLog($"输出：{produced}（{new FileInfo(produced).Length:N0} 字节），已自动填入刻录页。");
            }
        }
    }

    [RelayCommand]
    private async Task RenderPreviewAsync()
    {
        string previewPath = Path.Combine(Path.GetTempPath(), "discimage-preview.png");
        int exit;
        if (IsCd)
        {
            exit = await RunJobAsync(
                "cd-preview-warp", ["--input", ImagePath, "--output", previewPath]);
        }
        else if (IsDvd)
        {
            if (!File.Exists(DvdOutput))
            {
                AppendLog("error: 先生成 DVD ISO 再渲染读回模拟。");
                return;
            }

            exit = await RunJobAsync(
                "simulate",
                ["--iso", DvdOutput, "--output", previewPath,
                 "--inner-radius-mm", InnerRadiusMm, "--outer-radius-mm", OuterRadiusMm]);
        }
        else
        {
            AppendLog("BD 暂无读回预览命令，可先查看左侧源图。");
            return;
        }

        if (exit == 0)
        {
            ResultPreview = LoadBitmap(previewPath);
        }
    }

    [RelayCommand]
    private void Cancel() => _jobCancellation?.Cancel();

    [RelayCommand]
    private void RefreshDrives()
    {
        DriveItems.Clear();
        _driveNodes.Clear();
        foreach ((string node, string vendor, string model) in BurnCommands.EnumerateDrives("/sys/block"))
        {
            _driveNodes.Add(node);
            DriveItems.Add($"{node} — {vendor} {model}".TrimEnd());
        }

        SelectedDriveIndex = DriveItems.Count > 0 ? 0 : -1;
        if (DriveItems.Count == 0)
        {
            DriveItems.Add("（未检测到光驱）");
        }
    }

    [RelayCommand]
    private async Task BurnAsync()
    {
        if (SelectedDriveIndex < 0 || SelectedDriveIndex >= _driveNodes.Count)
        {
            AppendBurnLog("error: 先选择一台光驱。");
            return;
        }

        if (string.IsNullOrWhiteSpace(BurnSource) || !File.Exists(BurnSource))
        {
            AppendBurnLog("error: 先选择要刻录的 ISO 或 CUE 文件。");
            return;
        }

        List<string> args = ["--device", _driveNodes[SelectedDriveIndex]];
        args.Add(Path.GetExtension(BurnSource).Equals(".cue", StringComparison.OrdinalIgnoreCase)
            ? "--cue"
            : "--image");
        args.Add(BurnSource);
        if (BurnBlank)
        {
            args.Add("--blank");
        }

        if (BurnVerify)
        {
            args.Add("--verify");
        }

        if (BurnReallyWrite)
        {
            args.Add("--yes");
        }

        AppendBurnLog(BurnReallyWrite ? "开始刻录…" : "干跑：只探测介质并打印计划。");
        int exit = await Task.Run(
            () => BurnCommands.BurnCore([.. args], AppendBurnLogFromThread, AppendBurnLogFromThread));
        AppendBurnLog(exit == 0 ? "刻录命令完成。" : $"刻录命令失败（退出码 {exit}）。");
    }

    private async Task<int> RunJobAsync(string command, string[] args)
    {
        IsBusy = true;
        StatusText = $"运行 {command}…";
        _jobCancellation = new CancellationTokenSource();
        Progress<DiscJobProgress> progress = new(item =>
        {
            if (!string.IsNullOrWhiteSpace(item.Message))
            {
                AppendLog(item.Message);
            }
        });
        try
        {
            DiscJobResult result = await Task.Run(() => Modules.ExecuteAsync(
                new DiscJobRequest(command, args), progress, _jobCancellation.Token)
                .GetAwaiter().GetResult());
            if (!string.IsNullOrWhiteSpace(result.Summary))
            {
                AppendLog(result.Summary);
            }

            StatusText = result.ExitCode == 0
                ? $"{command} 完成"
                : $"{command} 失败（退出码 {result.ExitCode}）";
            return result.ExitCode;
        }
        catch (OperationCanceledException)
        {
            AppendLog("已取消。");
            StatusText = "已取消";
            return 130;
        }
        catch (Exception exception)
        {
            AppendLog($"error: {exception.Message}");
            StatusText = "出错";
            return 1;
        }
        finally
        {
            IsBusy = false;
            _jobCancellation.Dispose();
            _jobCancellation = null;
        }
    }

    private void AppendLog(string line) => LogText += line + "\n";

    private void AppendBurnLog(string line) => BurnLogText += line + "\n";

    private void AppendBurnLogFromThread(string line)
        => Dispatcher.UIThread.Post(() => AppendBurnLog(line));

    private static Bitmap? LoadBitmap(string path)
    {
        try
        {
            return File.Exists(path) ? new Bitmap(path) : null;
        }
        catch
        {
            return null;
        }
    }
}
