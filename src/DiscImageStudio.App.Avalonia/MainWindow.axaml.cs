using Avalonia.Controls;
using Avalonia.Interactivity;
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
                        Patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif"],
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
}
