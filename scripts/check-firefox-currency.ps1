# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

<#
.SYNOPSIS
Fails when Mozilla's latest Firefox release is newer than the pinned one.

.DESCRIPTION
Reads LATEST_FIREFOX_VERSION from Mozilla's product-details feed and compares
it with the version in the tag of upstream/firefox.json. This is the check
behind Orbis's update promise: run it daily.

Exit code 0: the pin is current (or ahead).
Exit code 1: the pin is behind; update it (docs/UPDATING.md).
Exit code 2: the check itself failed (network, bad feed, bad pin file).

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
    } else {
        Write-Host ("OK: pinned {0} ({1}) equals Mozilla's latest release {2}{3}" -f $pin.Version, $pin.Tag, $latestText, $next)
    }
    exit 0
} catch {
    [Console]::Error.WriteLine("ERROR: currency check failed: " + $_.Exception.Message)
    exit 2
}
