# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

<#
.SYNOPSIS
Draws the TODO placeholder images for overlay\browser\branding\orbis.

.DESCRIPTION
For every PNG, ICO, BMP and JPG image in Firefox's browser\branding\unofficial template, writes a
newly drawn image with the same file name and pixel size into the Orbis branding folder: a blue disc
with a white "O", and the word "TODO" where there is room. Only the file names and sizes are read
from the template; no Mozilla artwork is copied. Mac-only files (.icns, Assets.car, dsstore) are skipped.

Run it again to regenerate; the output is overwritten. Replace the images with the real Orbis artwork
in PR 9 (see docs\BRANDING.md).

.PARAMETER Template
Firefox's unofficial branding folder. Default: %USERPROFILE%\orbis_desktop_src\firefox\browser\branding\unofficial

.PARAMETER Destination
Default: overlay\browser\branding\orbis in this repository.
#>
[CmdletBinding()]
param(
    [string]$Template = (Join-Path $env:USERPROFILE 'orbis_desktop_src\firefox\browser\branding\unofficial'),
    [string]$Destination = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
if (-not $Destination) { $Destination = Join-Path $repoRoot 'overlay\browser\branding\orbis' }
$Template = [System.IO.Path]::GetFullPath($Template).TrimEnd('\')
$Destination = [System.IO.Path]::GetFullPath($Destination).TrimEnd('\')
if (-not $Destination.StartsWith('C:\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Destination must be on drive C: '$Destination'"
}
if (-not (Test-Path -LiteralPath $Template -PathType Container)) { throw "Template folder not found: '$Template'" }

function New-PlaceholderBitmap {
    param([int]$Width, [int]$Height, [bool]$Opaque)
    $bmp = New-Object System.Drawing.Bitmap($Width, $Height, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    if ($Opaque) { $g.Clear([System.Drawing.Color]::FromArgb(255, 20, 24, 40)) } else { $g.Clear([System.Drawing.Color]::Transparent) }

    $side = [Math]::Min($Width, $Height)
    $d = [Math]::Max(1, [int]($side * 0.86))
    $x = [int](($Width - $d) / 2); $y = [int](($Height - $d) / 2)
    $disc = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 43, 79, 191))
    $g.FillEllipse($disc, $x, $y, $d, $d)

    $fmt = New-Object System.Drawing.StringFormat
    $fmt.Alignment = [System.Drawing.StringAlignment]::Center
    $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
    $white = [System.Drawing.Brushes]::White
    $fontO = New-Object System.Drawing.Font('Arial', [single]([Math]::Max(1, $d * 0.5)), [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $rectO = New-Object System.Drawing.RectangleF([single]$x, [single]($y - $d * 0.06), [single]$d, [single]$d)
    $g.DrawString('O', $fontO, $white, $rectO, $fmt)
    if ($side -ge 40) {
        $fontT = New-Object System.Drawing.Font('Arial', [single]([Math]::Max(6, $d * 0.13)), [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
        $yellow = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 255, 214, 0))
        $rectT = New-Object System.Drawing.RectangleF([single]$x, [single]($y + $d * 0.62), [single]$d, [single]($d * 0.2))
        $g.DrawString('TODO', $fontT, $yellow, $rectT, $fmt)
        $fontT.Dispose(); $yellow.Dispose()
    }
    $fontO.Dispose(); $disc.Dispose(); $fmt.Dispose(); $g.Dispose()
    return $bmp
}

function Get-PngBytes {
    param([int]$Width, [int]$Height, [bool]$Opaque)
    $bmp = New-PlaceholderBitmap -Width $Width -Height $Height -Opaque $Opaque
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    return ,$ms.ToArray()
}

function Get-IcoSizes {
    param([string]$Path)
    $b = [System.IO.File]::ReadAllBytes($Path)
    $n = [BitConverter]::ToUInt16($b, 4)
    $sizes = @()
    for ($i = 0; $i -lt $n; $i++) {
        $w = [int]$b[6 + 16 * $i]; if ($w -eq 0) { $w = 256 }
        $sizes += $w
    }
    return ($sizes | Sort-Object -Unique)
}

function Write-Ico {
    # ICO with one PNG-compressed 32-bit image per size (supported since Windows Vista).
    param([string]$Path, [int[]]$Sizes)
    $pngs = @(); foreach ($s in $Sizes) { $pngs += ,(Get-PngBytes -Width $s -Height $s -Opaque $false) }
    $ms = New-Object System.IO.MemoryStream
    $w = New-Object System.IO.BinaryWriter($ms)
    $w.Write([UInt16]0); $w.Write([UInt16]1); $w.Write([UInt16]$Sizes.Count)
    $offset = 6 + 16 * $Sizes.Count
    for ($i = 0; $i -lt $Sizes.Count; $i++) {
        $s = $Sizes[$i]; $dim = if ($s -ge 256) { 0 } else { $s }
        $w.Write([byte]$dim); $w.Write([byte]$dim); $w.Write([byte]0); $w.Write([byte]0)
        $w.Write([UInt16]1); $w.Write([UInt16]32)
        $w.Write([UInt32]$pngs[$i].Length); $w.Write([UInt32]$offset)
        $offset += $pngs[$i].Length
    }
    foreach ($p in $pngs) { $w.Write([byte[]]$p) }
    $w.Flush()
    [System.IO.File]::WriteAllBytes($Path, $ms.ToArray())
    $w.Dispose()
}

$written = 0
Get-ChildItem -LiteralPath $Template -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Template.Length + 1)
    $ext = $_.Extension.ToLowerInvariant()
    if (@('.png', '.ico', '.bmp', '.jpg') -notcontains $ext) { return }
    $out = Join-Path $Destination $rel
    $dir = Split-Path -Parent $out
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    if ($ext -eq '.ico') {
        Write-Ico -Path $out -Sizes (Get-IcoSizes -Path $_.FullName)
    } else {
        $img = [System.Drawing.Image]::FromFile($_.FullName)
        $width = $img.Width; $height = $img.Height
        $img.Dispose()
        if ($ext -eq '.png') {
            [System.IO.File]::WriteAllBytes($out, (Get-PngBytes -Width $width -Height $height -Opaque $false))
        } else {
            $bmp = New-PlaceholderBitmap -Width $width -Height $height -Opaque $true
            if ($ext -eq '.bmp') {
                # NSIS wizard bitmaps: 24-bit, no alpha.
                $flat = $bmp.Clone((New-Object System.Drawing.Rectangle(0, 0, $width, $height)), [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
                $flat.Save($out, [System.Drawing.Imaging.ImageFormat]::Bmp); $flat.Dispose()
            } else {
                $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Jpeg)
            }
            $bmp.Dispose()
        }
    }
    $written++
    Write-Host ("  {0}" -f $rel)
}
Write-Host "OK: $written placeholder images in $Destination"
