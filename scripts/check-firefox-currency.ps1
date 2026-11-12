# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

<#
.SYNOPSIS
Fails when Mozilla's latest Firefox release is newer than the pinned one.

.DESCRIPTION
Reads LATEST_FIREFOX_VERSION from Mozilla's product-details feed and compares
it with the version in the tag of upstream/firefox.json. This is the check
behind Orbis's update promise: run it daily.

When the pinned version equals the latest release, the pin must be the
FIREFOX_<v>_RELEASE tag, and git ls-remote must show that tag at the pinned
commit. A leftover release-candidate (_BUILD) pin, or a _RELEASE tag at a
different commit, is stale.

Exit code 0: the pin is current (or ahead).
Exit code 1: the pin is behind or stale; update it (docs/UPDATING.md).
Exit code 2: the check itself failed (network, git, bad feed, bad pin file).

.PARAMETER PinFile
Pin file to use. Default: upstream\firefox.json in this repository.

.PARAMETER VersionsUrl
Feed to read. Default: https://product-details.mozilla.org/1.0/firefox_versions.json

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check-firefox-currency.ps1
#>
[CmdletBinding()]
param(
    [string]$PinFile = '',
    [string]$VersionsUrl = 'https://product-details.mozilla.org/1.0/firefox_versions.json'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
# $PSScriptRoot is empty in param() defaults under Windows PowerShell 5.1, so resolve paths here.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir 'firefox-pin.ps1')
if (-not $PinFile) { $PinFile = Join-Path $repoRoot 'upstream\firefox.json' }

try {
    $pin = Read-FirefoxPin -Path $PinFile

    # Windows PowerShell 5.1 may default to old TLS versions.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $feed = Invoke-RestMethod -Uri $VersionsUrl -UseBasicParsing -TimeoutSec 60

    if (-not ($feed.PSObject.Properties.Name -contains 'LATEST_FIREFOX_VERSION')) {
        throw "Feed has no LATEST_FIREFOX_VERSION: $VersionsUrl"
    }
    $latestText = [string]$feed.LATEST_FIREFOX_VERSION
    $latest = ConvertTo-FirefoxVersion $latestText
    $pinned = ConvertTo-FirefoxVersion $pin.Version

    $next = ''
    if ($feed.PSObject.Properties.Name -contains 'NEXT_RELEASE_DATE') {
        $next = "; next release date in feed: $($feed.NEXT_RELEASE_DATE)"
    }

    if ($latest -gt $pinned) {
        [Console]::Error.WriteLine(("BEHIND: Mozilla's latest Firefox is {0}, newer than the pinned {1} ({2}){3}. See docs/UPDATING.md." -f $latestText, $pin.Version, $pin.Tag, $next))
        exit 1
    }
    if ($latest -lt $pinned) {
        Write-Host ("OK: pinned {0} ({1}) is ahead of Mozilla's latest release {2}{3}" -f $pin.Version, $pin.Tag, $latestText, $next)
        exit 0
    }

    # Same version as the release: the pin must be the _RELEASE tag, and that tag must be the pinned
    # commit. A release-candidate (_BUILD) pin left over after release day is stale.
    if ($pin.Tag -notmatch '_RELEASE$') {
        [Console]::Error.WriteLine(("STALE: {0} has been released, but the pin is still the release candidate {1}. Switch to the _RELEASE tag. See docs/UPDATING.md." -f $latestText, $pin.Tag))
        exit 1
    }
    $releaseRef = "refs/tags/$($pin.Tag)"
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'   # git may write to stderr; judge by the exit code
    $savedPrompt = $env:GIT_TERMINAL_PROMPT
    $env:GIT_TERMINAL_PROMPT = '0'
    try {
        $lines = @(& git ls-remote $pin.Repository $releaseRef "$releaseRef^{}" 2>&1 | ForEach-Object { "$_" })
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $saved
        $env:GIT_TERMINAL_PROMPT = $savedPrompt
    }
    if ($code -ne 0) {
        throw ("git ls-remote {0} {1} failed (exit {2})`n{3}" -f $pin.Repository, $releaseRef, $code, ($lines -join "`n"))
    }
    $direct = $null; $peeled = $null
    foreach ($line in $lines) {
        $f = $line -split "`t"
        if ($f.Count -ne 2) { continue }
        if ($f[1] -eq $releaseRef) { $direct = $f[0] }
        if ($f[1] -eq "$releaseRef^{}") { $peeled = $f[0] }
    }
    $remoteCommit = if ($peeled) { $peeled } else { $direct }
    if (-not $remoteCommit) {
        [Console]::Error.WriteLine(("STALE: tag {0} is not on {1}, but Mozilla lists {2} as released. See docs/UPDATING.md." -f $pin.Tag, $pin.Repository, $latestText))
        exit 1
    }
    if ($remoteCommit -ne $pin.Commit) {
        [Console]::Error.WriteLine(("STALE: remote tag {0} points at {1}, but the pin says {2}. See docs/UPDATING.md." -f $pin.Tag, $remoteCommit, $pin.Commit))
        exit 1
    }
    Write-Host ("OK: pinned {0} ({1} = {2}) equals Mozilla's latest release {3}{4}" -f $pin.Version, $pin.Tag, $pin.Commit, $latestText, $next)
    exit 0
} catch {
    [Console]::Error.WriteLine("ERROR: currency check failed: " + $_.Exception.Message)
    exit 2
}
