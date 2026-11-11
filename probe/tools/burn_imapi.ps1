<#
Burn an ISO image with Windows' own IMAPI2 at a chosen write speed (isoburn.exe cannot set one).

Without -Burn it only reports the recorder, the media, its blank state and the supported write
speeds, and writes nothing. With -Burn it writes the image as one closed session at the
nearest speed the drive lists.

  powershell -ExecutionPolicy Bypass -File tools\burn_imapi.ps1 -Drive H: -Iso iso\x.iso
  powershell -ExecutionPolicy Bypass -File tools\burn_imapi.ps1 -Drive H: -Iso iso\x.iso -Speed 8 -Burn

-Speed is in multiples of the medium's 1x (CD 75 sectors/s, DVD 675 sectors/s).
-Reload closes the tray again after the eject (tray-loading drives such as the GH70N), so the
burned disc can be read straight away. Without it, push the tray back in before measuring.

While writing it prints a line every 30 s with an estimate from the write speed. That estimate
is time only: IMAPI2's progress events would have to run inside the burn, and a burn can't be
retried on the same disc, so this stays out of the way of the write.

Closing a CD needs some room beyond FreeSectorsOnMedia: on a 359,847-sector CD-R a 359,800-sector
image was refused at the start of Write ("stream too large"), 359,600 sectors went through.
#>
param(
    [string]$Drive = "H:",
    [string]$Iso,
    [double]$Speed = 0,
    [switch]$Burn,
    [switch]$Reload
)
$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class IsoStream {
    [DllImport("shlwapi.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    static extern void SHCreateStreamOnFileEx(string file, uint mode, uint attrs, bool create, IntPtr template, out IStream stream);
    public static IStream Open(string path) {
        IStream s;
        SHCreateStreamOnFileEx(path, 0x20 /* STGM_READ | STGM_SHARE_DENY_WRITE */, 0, false, IntPtr.Zero, out s);
        return s;
    }
}
"@

function Start-WriteHeartbeat([double]$EstimateSeconds, [int]$EverySeconds = 30) {
    # Write() blocks this thread, so another runspace does the talking. It touches no IMAPI2 object.
    $beat = [powershell]::Create()
    [void]$beat.AddScript({
        param($estimate, $every)
        $clock = { param($s) $t = [int][math]::Floor($s); "{0}:{1:00}" -f [math]::Floor($t / 60), ($t % 60) }
        $t0 = Get-Date
        while ($true) {
            Start-Sleep -Seconds $every
            $done = ((Get-Date) - $t0).TotalSeconds
            $left = $estimate - $done
            $state = if ($estimate -le 0) { "no estimate" }
                     elseif ($left -gt 0) { "about $(& $clock $left) left" }
                     else { "past the estimate, closing the disc can take a while" }
            [Console]::WriteLine("  still writing: $(& $clock $done) so far, $state")
        }
    }).AddArgument($EstimateSeconds).AddArgument($EverySeconds)
    [void]$beat.BeginInvoke()
    $beat
}

$master = New-Object -ComObject IMAPI2.MsftDiscMaster2
$recorder = $null
foreach ($id in $master) {
    $r = New-Object -ComObject IMAPI2.MsftDiscRecorder2
    $r.InitializeDiscRecorder($id)
    if ($r.VolumePathNames -contains ($Drive.TrimEnd('\') + '\')) { $recorder = $r }
}
if (-not $recorder) { throw "no IMAPI2 recorder at $Drive" }
"Recorder: $($recorder.VendorId.Trim()) $($recorder.ProductId.Trim()) rev $($recorder.ProductRevision) at $Drive"

$fmt = New-Object -ComObject IMAPI2.MsftDiscFormat2Data
if (-not $fmt.IsRecorderSupported($recorder)) { throw "recorder not supported for data writing" }
$fmt.Recorder = $recorder
$fmt.ClientName = "discprobe"
if (-not $fmt.IsCurrentMediaSupported($recorder)) { throw "no writable medium in $Drive" }

# IMAPI_MEDIA_PHYSICAL_TYPE: 2 CD-R, 3 CD-RW, 6 DVD+R, 8 DVD-R, ...
$type = $fmt.CurrentPhysicalMediaType
$isCd = $type -in 1, 2, 3
$unit = if ($isCd) { 75 } else { 675 }
"Media type $type ($(if ($isCd) {'CD'} else {'DVD'})), blank: $($fmt.MediaHeuristicallyBlank), " +
    "free sectors: $($fmt.FreeSectorsOnMedia), total: $($fmt.TotalSectorsOnMedia)"
$speeds = @($fmt.SupportedWriteSpeedDescriptors | ForEach-Object {
    "{0:0.#}x ({1} sectors/s, {2})" -f ($_.WriteSpeed / $unit), $_.WriteSpeed, $(if ($_.RotationTypeIsPureCAV) {'CAV'} else {'CLV/ZCLV'})
})
"Supported write speeds: " + ($speeds -join "; ")

if (-not $Iso) { return }
$path = (Resolve-Path $Iso).Path
$sectors = (Get-Item $path).Length / 2048
"Image: $path, $sectors sectors"
if ($sectors -gt $fmt.FreeSectorsOnMedia) { throw "image is larger than the free space on the medium" }
if (-not $Burn) { "Dry run: nothing written (add -Burn to write)."; return }
if (-not $fmt.MediaHeuristicallyBlank) { throw "medium is not blank; refusing to write" }

if ($Speed -gt 0) {
    # Ask for the nearest speed the drive lists: its 8x can be 5410 sectors/s on DVD, and asking
    # for 5400 falls to the 4x below.
    $want = $Speed * $unit
    $nearest = $fmt.SupportedWriteSpeedDescriptors | Sort-Object { [math]::Abs($_.WriteSpeed - $want) } | Select-Object -First 1
    $fmt.SetWriteSpeed($(if ($nearest) { $nearest.WriteSpeed } else { [int]$want }), $false)
}
"Requested write speed: $(if ($Speed -gt 0) {"${Speed}x"} else {'drive default'}); " +
    "drive reports {0:0.#}x" -f ($fmt.CurrentWriteSpeed / $unit)
$fmt.ForceMediaToBeClosed = $true
$stream = [IsoStream]::Open($path)
$t0 = Get-Date
"Writing ... (started $($t0.ToString('HH:mm:ss')))"
$estimate = if ($fmt.CurrentWriteSpeed -gt 0) { $sectors / $fmt.CurrentWriteSpeed } else { 0 }
if ($estimate -gt 0) { "The drive does not report progress here. Estimate from the write speed: about {0:0} min." -f ($estimate / 60) }
$beat = Start-WriteHeartbeat $estimate
try { $fmt.Write($stream) } finally { $beat.Stop(); $beat.Dispose() }
"Done in {0:0.0} min" -f ((Get-Date) - $t0).TotalMinutes
$recorder.EjectMedia()
$closed = $false
if ($Reload) {
    Start-Sleep -Seconds 2
    # Slot and slim drives can't pull the tray in. The burn is already done, so this must not fail the script.
    try { $recorder.CloseTray(); $closed = $true } catch { }
}
if ($closed) { "Tray closed again. Give the drive a few seconds to read the disc." }
else { "The drive ejected the disc. Push the tray back in and wait a few seconds before measuring it." }
