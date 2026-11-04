using System.IO;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Platform.Storage;

namespace DiscImageStudio.Gui;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
    }

    private async void BrowseImage_Click(object? sender, RoutedEventArgs e)
    {
        IReadOnlyList<IStorageFile> files = await StorageProvider.OpenFilePickerAsync(
            new FilePickerOpenOptions
            {
                Title = "选择源图像",
                AllowMultiple = false,
                FileTypeFilter =
                [
                    new FilePickerFileType("图像")
                    {
                        Patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.webp"],
                    },
                ],
            });
        if (files.Count > 0 && DataContext is MainWindowViewModel viewModel)
        {
            viewModel.ImagePath = files[0].Path.LocalPath;
        }
    }

    private async void BrowseBurnSource_Click(object? sender, RoutedEventArgs e)
    {
        IReadOnlyList<IStorageFile> files = await StorageProvider.OpenFilePickerAsync(
            new FilePickerOpenOptions
            {
                Title = "选择要刻录的 ISO 或 CUE",
                AllowMultiple = false,
                FileTypeFilter =
                [
                    new FilePickerFileType("光盘镜像")
                    {
                        Patterns = ["*.iso", "*.cue"],
                    },
                ],
            });
        if (files.Count > 0 && DataContext is MainWindowViewModel viewModel)
        {
            viewModel.BurnSource = files[0].Path.LocalPath;
        }
    }
    private bool _designDragging;
    private Point _designLastPoint;

    private async void BrowseDesignImage_Click(object? sender, RoutedEventArgs e)
    {
        IReadOnlyList<IStorageFile> files = await StorageProvider.OpenFilePickerAsync(
            new FilePickerOpenOptions
            {
                Title = "选择设计图片",
                AllowMultiple = false,
                FileTypeFilter =
                [
                    new FilePickerFileType("图像")
                    {
                        Patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif", "*.webp"],
                    },
                ],
            });
        if (files.Count > 0 && DataContext is MainWindowViewModel viewModel)
        {
            viewModel.LoadDesignImage(files[0].Path.LocalPath);
        }
    }

    private void Design_PointerPressed(object? sender, PointerPressedEventArgs e)
    {
        if (DataContext is not MainWindowViewModel viewModel || viewModel.DesignBitmap is null)
        {
            return;
        }

        _designDragging = true;
        _designLastPoint = e.GetPosition(DesignSurface);
        e.Pointer.Capture(DesignSurface);
    }

    private void Design_PointerMoved(object? sender, PointerEventArgs e)
    {
        if (!_designDragging || DataContext is not MainWindowViewModel viewModel)
        {
            return;
        }

        Point point = e.GetPosition(DesignSurface);
        // The surface runs at 4 px per millimetre.
        viewModel.DesignTranslateXMm += (point.X - _designLastPoint.X) / 4.0;
        viewModel.DesignTranslateYMm += (point.Y - _designLastPoint.Y) / 4.0;
        _designLastPoint = point;
    }

    private void Design_PointerReleased(object? sender, PointerReleasedEventArgs e)
    {
        _designDragging = false;
        e.Pointer.Capture(null);
    }

    private void Design_PointerWheelChanged(object? sender, PointerWheelEventArgs e)
    {
        if (DataContext is not MainWindowViewModel viewModel || viewModel.DesignBitmap is null)
        {
            return;
        }

        double factor = e.Delta.Y > 0 ? 1.1 : 1.0 / 1.1;
        viewModel.DesignScale = Math.Clamp(viewModel.DesignScale * factor, 0.05, 8.0);
    }

    private void ExportDesign_Click(object? sender, RoutedEventArgs e)
    {
        if (DataContext is not MainWindowViewModel viewModel || viewModel.DesignBitmap is null)
        {
            return;
        }

        try
        {
            // Compose the layer onto a transparent square whose side spans the
            // 120 mm disc, mirroring the WPF app's DesignComposer contract.
            const int size = 4096;
            double pixelsPerMm = size / 120.0;
            double widthPx = viewModel.DesignBaseWidthMm * viewModel.DesignScale * pixelsPerMm;
            double heightPx = viewModel.DesignBaseHeightMm * viewModel.DesignScale * pixelsPerMm;
            Canvas canvas = new() { Width = size, Height = size, Background = Brushes.Transparent };
            Image image = new()
            {
                Source = viewModel.DesignBitmap,
                Width = widthPx,
                Height = heightPx,
                RenderTransformOrigin = new RelativePoint(0.5, 0.5, RelativeUnit.Relative),
                RenderTransform = new RotateTransform(viewModel.DesignRotationDeg),
            };
            Canvas.SetLeft(image, size / 2.0 + viewModel.DesignTranslateXMm * pixelsPerMm - widthPx / 2.0);
            Canvas.SetTop(image, size / 2.0 + viewModel.DesignTranslateYMm * pixelsPerMm - heightPx / 2.0);
            canvas.Children.Add(image);
            canvas.Measure(new Size(size, size));
            canvas.Arrange(new Rect(0, 0, size, size));
            using RenderTargetBitmap bitmap = new(new PixelSize(size, size), new Vector(96, 96));
            bitmap.Render(canvas);
            string path = Path.Combine(Path.GetTempPath(), "discimage-design.png");
            bitmap.Save(path);
            viewModel.ImagePath = path;
            viewModel.StatusText = "设计图已导出，已设为生成源图";
            MainTabs.SelectedIndex = 1;
        }
        catch (Exception exception)
        {
            if (DataContext is MainWindowViewModel vm)
            {
                vm.StatusText = $"导出设计图失败：{exception.Message}";
            }
        }
    }
}
