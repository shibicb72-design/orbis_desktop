# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

<#
.SYNOPSIS
Shallow-fetches exactly the pinned Firefox tag and checks it out.

.DESCRIPTION
Reads upstream/firefox.json (repository, tag, commit). Fetches only that tag
with depth 1 into -Destination, which must be on C: and outside this
repository. Refuses to continue, and does not check anything out, if the tag
does not resolve to the pinned commit, either on the remote (checked before
the download) or after the fetch.

Running it again on the same folder is safe: the same tag is fetched again
(nothing new to download) and the same commit stays checked out.

Exit code 0: checkout is at the pinned commit. Exit code 1: refused or failed.

.PARAMETER Destination
Folder for the Firefox checkout. Default: %USERPROFILE%\orbis_desktop_src\firefox

.PARAMETER PinFile
Pin file to use. Default: upstream\firefox.json in this repository.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\fetch-firefox.ps1
#>
[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $env:USERPROFILE 'orbis_desktop_src\firefox'),
    [string]$PinFile = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
# $PSScriptRoot is empty in param() defaults under Windows PowerShell 5.1, so resolve paths here.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir 'firefox-pin.ps1')
if (-not $PinFile) { $PinFile = Join-Path $repoRoot 'upstream\firefox.json' }

function Invoke-Git {
    # Runs git and throws on a non-zero exit code. Captures output unless -Stream.
    param([Parameter(Mandatory = $true)][string[]]$GitArgs, [switch]$Stream)

    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'   # git writes progress to stderr; do not treat that as an error
    try {
        if ($Stream) {
            & git @GitArgs
            $out = @()
        } else {
            $out = @(& git @GitArgs 2>&1 | ForEach-Object { "$_" })
        }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $saved
    }
    if ($code -ne 0) {
        throw ("git {0} failed (exit {1})`n{2}" -f ($GitArgs -join ' '), $code, ($out -join "`n"))
    }
    return $out
}

function Test-PathInside {
    # True if $Path equals $Root or is below it. Both must be full paths.
    param([string]$Path, [string]$Root)
    $p = $Path.TrimEnd('\') + '\'
    $r = $Root.TrimEnd('\') + '\'
    return $p.StartsWith($r, [StringComparison]::OrdinalIgnoreCase)
}

try {
    $pin = Read-FirefoxPin -Path $PinFile
    Write-Host ("Pin: {0} = {1} from {2}" -f $pin.Tag, $pin.Commit, $pin.Repository)

    # --- Where the checkout may go -------------------------------------------------------------
    $dest = $PSCmdlet.GetUnresolvedProviderPathFromPSPath($Destination)
    $dest = [System.IO.Path]::GetFullPath($dest).TrimEnd('\')
    if (-not $dest.StartsWith('C:\', [StringComparison]::OrdinalIgnoreCase) -or $dest.Length -le 3) {
        throw "Destination must be a folder on drive C: (files go on C: only): '$dest'"
    }
    $repoRoot = [System.IO.Path]::GetFullPath($repoRoot).TrimEnd('\')
    if ((Test-PathInside $dest $repoRoot) -or (Test-PathInside $repoRoot $dest)) {
        throw "Destination must be outside the Orbis repository '$repoRoot' and must not contain it: '$dest'"
    }

    if (Test-Path -LiteralPath $dest) {
        if (-not (Test-Path -LiteralPath $dest -PathType Container)) {
            throw "Destination exists and is not a folder: '$dest'"
        }
        if (Test-Path -LiteralPath (Join-Path $dest '.git')) {
            $top = (Invoke-Git -GitArgs @('-C', $dest, 'rev-parse', '--show-toplevel') | Select-Object -Last 1)
            $top = [System.IO.Path]::GetFullPath($top.Replace('/', '\')).TrimEnd('\')
            if ($top -ine $dest) {
                throw "Destination is not the top of its own git repository (top is '$top'): '$dest'"
            }
            $origin = @(& git -C $dest config --get remote.origin.url)
            if ($origin.Count -eq 0 -or $origin[0] -ne $pin.Repository) {
                throw ("Destination is a git repository whose origin is '{0}', not '{1}'. Refusing to reuse it." -f ($origin -join ' '), $pin.Repository)
            }
        } elseif (@(Get-ChildItem -LiteralPath $dest -Force).Count -gt 0) {
            throw "Destination exists, is not empty and is not a git checkout. Refusing to write into it: '$dest'"
        } else {
            Invoke-Git -GitArgs @('init', '-q', $dest) | Out-Null
            Invoke-Git -GitArgs @('-C', $dest, 'remote', 'add', 'origin', $pin.Repository) | Out-Null
        }
    } else {
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
        Invoke-Git -GitArgs @('init', '-q', $dest) | Out-Null
        Invoke-Git -GitArgs @('-C', $dest, 'remote', 'add', 'origin', $pin.Repository) | Out-Null
    }

    # Settings local to this checkout only (never global): keep Mozilla's line endings as they are,
    # and allow the long paths that exist in the Firefox tree.
    Invoke-Git -GitArgs @('-C', $dest, 'config', 'core.autocrlf', 'false') | Out-Null
    Invoke-Git -GitArgs @('-C', $dest, 'config', 'core.longpaths', 'true') | Out-Null

    # --- Check the remote before downloading anything large ------------------------------------
    $tagRef = "refs/tags/$($pin.Tag)"
    $lines = Invoke-Git -GitArgs @('-C', $dest, 'ls-remote', 'origin', $tagRef, "$tagRef^{}")
    $direct = $null; $peeled = $null
    foreach ($line in $lines) {
        $f = $line -split "`t"
        if ($f.Count -ne 2) { continue }
        if ($f[1] -eq $tagRef) { $direct = $f[0] }
        if ($f[1] -eq "$tagRef^{}") { $peeled = $f[0] }
    }
    if (-not $direct) { throw "Tag $($pin.Tag) not found on $($pin.Repository)" }
    $remoteCommit = if ($peeled) { $peeled } else { $direct }
    if ($remoteCommit -ne $pin.Commit) {
        throw ("REFUSED: remote tag {0} points at {1}, but the pin says {2}. Nothing was fetched." -f $pin.Tag, $remoteCommit, $pin.Commit)
    }
    Write-Host "Remote tag matches the pin. Fetching (depth 1); the first run downloads several GB."

    # --- Fetch exactly that tag, then check the fetched commit ---------------------------------
    # No '+' in the refspec: an existing local tag with a different value makes git refuse.
    Invoke-Git -Stream -GitArgs @('-C', $dest, 'fetch', '--depth', '1', '--no-tags', 'origin', "${tagRef}:${tagRef}") | Out-Null

    $fetched = (Invoke-Git -GitArgs @('-C', $dest, 'rev-parse', '--verify', "$tagRef^{commit}") | Select-Object -Last 1).Trim()
    if ($fetched -ne $pin.Commit) {
        throw ("REFUSED: fetched tag {0} is commit {1}, but the pin says {2}. Nothing was checked out." -f $pin.Tag, $fetched, $pin.Commit)
    }

    Invoke-Git -GitArgs @('-C', $dest, 'checkout', '-q', '--detach', $pin.Commit) | Out-Null
    $head = (Invoke-Git -GitArgs @('-C', $dest, 'rev-parse', 'HEAD') | Select-Object -Last 1).Trim()
    if ($head -ne $pin.Commit) {
        throw "REFUSED: HEAD is $head after checkout, expected $($pin.Commit)"
    }

    $dirty = @(Invoke-Git -GitArgs @('-C', $dest, 'status', '--porcelain'))
    if ($dirty.Count -gt 0) {
        Write-Warning "The checkout has $($dirty.Count) changed or extra paths (for example an applied overlay)."
    }
    Write-Host "OK: $dest is at $($pin.Tag) = $head"
    exit 0
} catch {
    [Console]::Error.WriteLine("FAILED: " + $_.Exception.Message)
    exit 1
}
