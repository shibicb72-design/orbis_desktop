# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

<#
.SYNOPSIS
Applies patches\*.patch to the pinned Firefox checkout with git apply, after checking that they all apply.

.DESCRIPTION
The patches are applied in file-name order, as one series. The script refuses, and changes nothing, when:
- the checkout is not on drive C:, is inside this repository, passes through a junction or symbolic link, or
  is not a Firefox git checkout (no mach, no .git);
- the checkout's HEAD is not the commit pinned in upstream\firefox.json;
- the checkout has changes to tracked files (a dirty tree). Untracked files, such as the overlay's
  browser\branding\orbis, mozconfig and orbis-dist, are allowed;
- git apply --check fails for the series.

If the tracked changes are exactly the patches already applied (the patched files, with the patches reversed in
a scratch copy, are byte-identical to HEAD, and no other tracked file is changed), the script reports that and
exits 0 without writing. So running it twice is safe.

Undo: git -C <checkout> checkout -- <the files the patches touch>, listed in docs\PATCHES.md.

Exit code 0: applied, already applied, or (with -Check) would apply. Exit code 1: refused or failed.

.PARAMETER Checkout
Firefox checkout. Default: %USERPROFILE%\orbis_desktop_src\firefox

.PARAMETER Check
Run every check, including git apply --check, but write nothing.

.PARAMETER PinFile
Pin file. Default: upstream\firefox.json in this repository.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\apply-patches.ps1 -Check
#>
[CmdletBinding()]
param(
    [string]$Checkout = '',
    [switch]$Check,
    [string]$PinFile = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $scriptDir)).TrimEnd('\')
. (Join-Path $scriptDir 'firefox-pin.ps1')
if (-not $Checkout) { $Checkout = Join-Path $env:USERPROFILE 'orbis_desktop_src\firefox' }
if (-not $PinFile) { $PinFile = Join-Path $repoRoot 'upstream\firefox.json' }

function Invoke-Git {
    # Runs git in the checkout with fixed line-ending settings. Returns @{ Code; Out }. Never throws on exit code.
    param([Parameter(Mandatory = $true)][string[]]$GitArgs)
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = @(& git -c core.autocrlf=false -c core.safecrlf=false -C $script:co @GitArgs 2>&1 | ForEach-Object { "$_" })
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $saved
    }
    return @{ Code = $code; Out = $out }
}

function Test-PathInside {
    # True if $Path equals $Root or is below it. Both must be full paths.
    param([string]$Path, [string]$Root)
    $p = $Path.TrimEnd('\') + '\'
    $r = $Root.TrimEnd('\') + '\'
    return $p.StartsWith($r, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-NoReparsePointOnPath {
    # The folder and every folder above it, up to the drive root, must be plain folders.
    param([string]$Path)
    $cur = $Path
    while ($cur) {
        if (Test-Path -LiteralPath $cur) {
            $item = Get-Item -LiteralPath $cur -Force
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "REFUSED: '$cur' is a junction or symbolic link"
            }
        }
        $parent = Split-Path -Parent $cur
        if (-not $parent -or $parent -eq $cur) { break }
        $cur = $parent
    }
}

function Get-PatchFiles {
    # Files named in the "diff --git a/X b/X" lines of a patch.
    param([string]$Path)
    $names = @()
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $m = [regex]::Match($line, '^diff --git a/(\S+) b/(\S+)')
        if ($m.Success) { $names += $m.Groups[2].Value }
    }
    return $names
}

function Test-ExactlyPatched {
    # True when every touched file in the checkout is exactly HEAD plus the patches: copies the files to a scratch
    # repository, reverses the patches there, and compares Git blob hashes with HEAD. Writes nothing in the checkout.
    param([string[]]$Touched, [string[]]$PatchPaths)
    $scratch = Join-Path ([System.IO.Path]::GetTempPath()) ('orbis-apply-patches-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $scratch | Out-Null
    try {
        & git -C $scratch init -q 2>&1 | Out-Null
        foreach ($f in ($Touched | Sort-Object -Unique)) {
            $src = Join-Path $script:co ($f -replace '/', '\')
            # A file that a patch deletes (0004) is missing: leave it out of the scratch copy. Reversing that
            # patch recreates it, and reversing fails if no patch deletes it, so a file missing for any other
            # reason still makes this return false.
            if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { continue }
            $dst = Join-Path $scratch ($f -replace '/', '\')
            New-Item -ItemType Directory -Path (Split-Path -Parent $dst) -Force | Out-Null
            Copy-Item -LiteralPath $src -Destination $dst
        }
        $saved = $script:co
        $script:co = $scratch
        try {
            $rev = Invoke-Git (@('apply', '--reverse', '--whitespace=nowarn') + $PatchPaths)
        } finally {
            $script:co = $saved
        }
        if ($rev.Code -ne 0) { return $false }
        foreach ($f in ($Touched | Sort-Object -Unique)) {
            $want = Invoke-Git @('rev-parse', "HEAD:$f")
            $got = @(& git hash-object --no-filters -- (Join-Path $scratch ($f -replace '/', '\')) 2>&1)
            if ($want.Code -ne 0 -or $LASTEXITCODE -ne 0) { return $false }
            if (($want.Out -join '').Trim() -ne ($got -join '').Trim()) { return $false }
        }
        return $true
    } finally {
        Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
    }
}

try {
    # --- The checkout --------------------------------------------------------------------------
    $co = $PSCmdlet.GetUnresolvedProviderPathFromPSPath($Checkout)
    $co = [System.IO.Path]::GetFullPath($co).TrimEnd('\')
    $script:co = $co
    if (-not $co.StartsWith('C:\', [StringComparison]::OrdinalIgnoreCase) -or $co.Length -le 3) {
        throw "REFUSED: the checkout must be a folder on drive C: '$co'"
    }
    if ((Test-PathInside $co $repoRoot) -or (Test-PathInside $repoRoot $co)) {
        throw "REFUSED: the checkout must be outside the Orbis repository '$repoRoot': '$co'"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $co 'mach') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $co '.git'))) {
        throw "REFUSED: '$co' is not a Firefox git checkout (no mach or no .git)"
    }
    Assert-NoReparsePointOnPath -Path $co

    $pin = Read-FirefoxPin -Path $PinFile
    $r = Invoke-Git @('rev-parse', 'HEAD')
    if ($r.Code -ne 0) { throw ("git rev-parse failed in '$co'`n" + ($r.Out -join "`n")) }
    $head = ($r.Out -join '').Trim()
    if ($head -ne $pin.Commit) {
        throw "REFUSED: the checkout is at $head but $PinFile pins $($pin.Commit) ($($pin.Tag))"
    }
    Write-Host "Checkout $co is at the pinned commit $head ($($pin.Tag))"

    # --- The patches ---------------------------------------------------------------------------
    $patchDir = Join-Path $repoRoot 'patches'
    $patches = @(Get-ChildItem -LiteralPath $patchDir -Filter '*.patch' -File | Sort-Object Name)
    if ($patches.Count -eq 0) { throw "No patches in $patchDir" }
    $touched = @()
    foreach ($p in $patches) {
        $files = @(Get-PatchFiles $p.FullName)
        if ($files.Count -eq 0) { throw "$($p.Name) has no 'diff --git' header" }
        Write-Host ("  {0}: {1}" -f $p.Name, ($files -join ', '))
        $touched += $files
    }
    $patchPaths = @($patches | ForEach-Object { $_.FullName })

    # --- Clean tree, or exactly our patches already applied --------------------------------------
    $r = Invoke-Git @('status', '--porcelain=v1', '--untracked-files=no')
    if ($r.Code -ne 0) { throw ("git status failed`n" + ($r.Out -join "`n")) }
    $dirty = @($r.Out | Where-Object { $_ } | ForEach-Object { $_.Substring(3).Trim('"') })
    if ($dirty.Count -gt 0) {
        $others = @($dirty | Where-Object { $touched -notcontains $_ })
        if ($others.Count -eq 0 -and (Test-ExactlyPatched -Touched $touched -PatchPaths $patchPaths)) {
            Write-Host ("OK: all {0} patches are already applied; nothing written" -f $patches.Count)
            exit 0
        }
        throw ("REFUSED: the checkout has changes to tracked files (not exactly our patches): " + ($dirty -join ', '))
    }

    # --- Check, then apply ---------------------------------------------------------------------
    $r = Invoke-Git (@('apply', '--check', '--whitespace=nowarn') + $patchPaths)
    if ($r.Code -ne 0) { throw ("REFUSED: git apply --check failed; nothing applied`n" + ($r.Out -join "`n")) }
    if ($Check) {
        Write-Host ("OK (check only): all {0} patches apply cleanly to {1}" -f $patches.Count, $co)
        exit 0
    }
    $r = Invoke-Git (@('apply', '--whitespace=nowarn') + $patchPaths)
    if ($r.Code -ne 0) { throw ("git apply failed after a passing --check`n" + ($r.Out -join "`n")) }
    Write-Host ("OK: applied {0} patches to {1}" -f $patches.Count, $co)
    exit 0
} catch {
    [Console]::Error.WriteLine("FAILED: " + $_.Exception.Message)
    exit 1
}
