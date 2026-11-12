# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

<#
.SYNOPSIS
Copies the Orbis overlay (branding, mozconfig, policy files) into a Firefox checkout.

.DESCRIPTION
What goes where (paths relative to the checkout):

  overlay\browser\branding\orbis\**   -> browser\branding\orbis\**   (read by --with-branding)
  mozconfig                           -> mozconfig                   (read by mach)
  overlay\distribution\policies.json  -> orbis-dist\distribution\policies.json
  overlay\orbis.cfg                   -> orbis-dist\orbis.cfg
  overlay\defaults\pref\autoconfig.js -> orbis-dist\defaults\pref\autoconfig.js

orbis-dist\ mirrors the install-folder layout; the packaging step (PR 5) puts it into the MSIX. A policy file
that is not in this branch is reported and skipped.

Safety rules. The script refuses, and copies nothing, when:
- the checkout is not on drive C:, is inside this repository, or does not look like a Firefox checkout
  (no mach, no browser\branding\unofficial);
- upstream\firefox.json exists and the checkout's HEAD is not the pinned commit;
- any destination resolves outside the checkout, or passes through a junction or symbolic link;
- any destination is a file Firefox itself tracks in git (the Firefox source is never edited by hand);
- browser\branding\orbis or orbis-dist exists but was not created by this script (no .orbis-overlay marker).

Running it again gives the same result: the two folders it owns are emptied and refilled, so files removed
from the overlay disappear from the checkout too. Nothing else in the checkout is deleted.

Exit code 0: copied (or, with -DryRun, would copy). Exit code 1: refused or failed.

.PARAMETER Checkout
Firefox checkout. Default: %USERPROFILE%\orbis_desktop_src\firefox

.PARAMETER DryRun
Check everything and list the copies, but write nothing.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\apply-overlay.ps1
#>
[CmdletBinding()]
param(
    [string]$Checkout = (Join-Path $env:USERPROFILE 'orbis_desktop_src\firefox'),
    [switch]$DryRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $scriptDir)).TrimEnd('\')
$Marker = '.orbis-overlay'

function Test-PathInside {
    # True if $Path equals $Root or is below it. Both must be full paths.
    param([string]$Path, [string]$Root)
    $p = $Path.TrimEnd('\') + '\'
    $r = $Root.TrimEnd('\') + '\'
    return $p.StartsWith($r, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-NoReparsePoint {
    # Every existing folder from $Root down to $Path must be a plain folder (no junction or symlink).
    param([string]$Path, [string]$Root)
    $cur = $Path
    while ($cur.Length -ge $Root.Length) {
        if (Test-Path -LiteralPath $cur) {
            $item = Get-Item -LiteralPath $cur -Force
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "REFUSED: '$cur' is a junction or symbolic link"
            }
        }
        if ($cur.Length -eq $Root.Length) { break }
        $cur = Split-Path -Parent $cur
    }
}

try {
    # --- The checkout --------------------------------------------------------------------------
    $co = $PSCmdlet.GetUnresolvedProviderPathFromPSPath($Checkout)
    $co = [System.IO.Path]::GetFullPath($co).TrimEnd('\')
    if (-not $co.StartsWith('C:\', [StringComparison]::OrdinalIgnoreCase) -or $co.Length -le 3) {
        throw "REFUSED: the checkout must be a folder on drive C: '$co'"
    }
    if ((Test-PathInside $co $repoRoot) -or (Test-PathInside $repoRoot $co)) {
        throw "REFUSED: the checkout must be outside the Orbis repository '$repoRoot': '$co'"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $co 'mach') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $co 'browser\branding\unofficial') -PathType Container)) {
        throw "REFUSED: '$co' does not look like a Firefox checkout (no mach or browser\branding\unofficial)"
    }
    Assert-NoReparsePoint -Path $co -Root $co
    $isGit = Test-Path -LiteralPath (Join-Path $co '.git')

    $pinFile = Join-Path $repoRoot 'upstream\firefox.json'
    if ((Test-Path -LiteralPath $pinFile) -and $isGit) {
        $pin = Get-Content -LiteralPath $pinFile -Raw | ConvertFrom-Json
        $head = (& git -C $co rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0) { throw "git rev-parse failed in '$co'" }
        if ($head -ne $pin.commit) {
            throw "REFUSED: the checkout is at $head but upstream\firefox.json pins $($pin.commit)"
        }
        Write-Host "Checkout $co is at the pinned commit $head"
    } else {
        Write-Host "Checkout $co (pin not checked: no upstream\firefox.json in this branch or no git checkout)"
    }

    # --- What to copy --------------------------------------------------------------------------
    $overlay = Join-Path $repoRoot 'overlay'
    $owned = @('browser\branding\orbis', 'orbis-dist')
    $copies = New-Object System.Collections.ArrayList

    $brandSrc = Join-Path $overlay 'browser\branding\orbis'
    if (-not (Test-Path -LiteralPath $brandSrc -PathType Container)) { throw "Missing $brandSrc" }
    Get-ChildItem -LiteralPath $brandSrc -Recurse -File -Force | ForEach-Object {
        [void]$copies.Add(@($_.FullName, ('browser\branding\orbis\' + $_.FullName.Substring($brandSrc.Length + 1))))
    }
    $mozconfig = Join-Path $repoRoot 'mozconfig'
    if (-not (Test-Path -LiteralPath $mozconfig -PathType Leaf)) { throw "Missing $mozconfig" }
    [void]$copies.Add(@($mozconfig, 'mozconfig'))
    foreach ($rel in @('distribution\policies.json', 'orbis.cfg', 'defaults\pref\autoconfig.js')) {
        $src = Join-Path $overlay $rel
        if (Test-Path -LiteralPath $src -PathType Leaf) {
            [void]$copies.Add(@($src, ('orbis-dist\' + $rel)))
        } else {
            Write-Host "  skipped (not in this branch): overlay\$rel"
        }
    }

    # --- Check every destination before writing anything -----------------------------------------
    foreach ($c in $copies) {
        $dest = [System.IO.Path]::GetFullPath((Join-Path $co $c[1]))
        if (-not (Test-PathInside $dest $co) -or $dest -ieq $co) {
            throw "REFUSED: destination '$dest' is outside the checkout '$co'"
        }
        Assert-NoReparsePoint -Path (Split-Path -Parent $dest) -Root $co
        $c[1] = $dest
    }
    if ($isGit) {
        $tracked = @(& git -C $co ls-files -- 'mozconfig' 'browser/branding/orbis' 'orbis-dist')
        if ($LASTEXITCODE -ne 0) { throw "git ls-files failed in '$co'" }
        if ($tracked.Count -gt 0) {
            throw ("REFUSED: these destinations are Firefox files tracked in git: " + ($tracked -join ', '))
        }
    }
    foreach ($o in $owned) {
        $dir = Join-Path $co $o
        if ((Test-Path -LiteralPath $dir) -and -not (Test-Path -LiteralPath (Join-Path $dir $Marker))) {
            throw "REFUSED: '$dir' exists but was not created by this script (no $Marker file)"
        }
    }

    # --- Copy --------------------------------------------------------------------------------------
    foreach ($c in $copies) {
        Write-Host ("  {0} -> {1}" -f $c[0].Substring($repoRoot.Length + 1), $c[1].Substring($co.Length + 1))
    }
    if ($DryRun) {
        Write-Host ("OK (dry run): {0} files would be copied into {1}" -f $copies.Count, $co)
        exit 0
    }
    foreach ($o in $owned) {
        $dir = Join-Path $co $o
        if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force }
    }
    foreach ($c in $copies) {
        $parent = Split-Path -Parent $c[1]
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Copy-Item -LiteralPath $c[0] -Destination $c[1] -Force
    }
    foreach ($o in $owned) {
        $dir = Join-Path $co $o
        if (Test-Path -LiteralPath $dir) {
            Set-Content -LiteralPath (Join-Path $dir $Marker) -Encoding ASCII -Value 'Created by orbis_desktop scripts\apply-overlay.ps1. The script empties and refills this folder.'
        }
    }
    Write-Host ("OK: copied {0} files into {1}" -f $copies.Count, $co)
    exit 0
} catch {
    [Console]::Error.WriteLine("FAILED: " + $_.Exception.Message)
    exit 1
}
