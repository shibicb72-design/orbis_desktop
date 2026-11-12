# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

<#
.SYNOPSIS
Fails when Mozilla's latest Firefox release is newer than the pinned one.

.DESCRIPTION
Reads LATEST_FIREFOX_VERSION from Mozilla's product-details feed and compares
it with the version in the tag of upstream/firefox.json. This is the check
behind Orbis's update promise: .github/workflows/firefox-currency.yml runs it
daily.

When the pinned version equals the latest release, the pin must be the
FIREFOX_<v>_RELEASE tag, and git ls-remote must show that tag at the pinned
commit. A leftover release-candidate (_BUILD) pin, or a _RELEASE tag at a
different commit, is stale.

When the pin is behind or stale, the script also prints the first release the
pin lacks (the earliest release in Mozilla's history feeds newer than the pin;
for a stale pin, the pinned version), its release date, the Orbis deadline
(that date + 3 days) and how many major versions the pin is behind. A newer
release does not move the deadline. If no history entry fits, the feed's
LAST_RELEASE_DATE is used (an earlier or equal date: the safe side). A failed
history lookup does not change the exit code; the date is then "unknown".

Exit code 0: the pin is current (or ahead).
Exit code 1: the pin is behind or stale; update it (docs/UPDATING.md).
Exit code 2: the check itself failed (network, git, bad feed, bad pin file).

.PARAMETER PinFile
Pin file to use. Default: upstream\firefox.json in this repository.

.PARAMETER VersionsUrl
Feed to read. Default: https://product-details.mozilla.org/1.0/firefox_versions.json

.PARAMETER MajorHistoryUrl
Release dates of x.0 versions. Default: https://product-details.mozilla.org/1.0/firefox_history_major_releases.json

.PARAMETER StabilityHistoryUrl
Release dates of dot releases. Default: https://product-details.mozilla.org/1.0/firefox_history_stability_releases.json

.PARAMETER ReportFile
If set, write the result as JSON to this file on exit code 0 or 1 (status,
versions, majorsBehind, releaseDate, deadline, message). An existing file is
deleted first, so after exit code 2 there is no report.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check-firefox-currency.ps1
#>
[CmdletBinding()]
param(
    [string]$PinFile = '',
    [string]$VersionsUrl = 'https://product-details.mozilla.org/1.0/firefox_versions.json',
    [string]$MajorHistoryUrl = 'https://product-details.mozilla.org/1.0/firefox_history_major_releases.json',
    [string]$StabilityHistoryUrl = 'https://product-details.mozilla.org/1.0/firefox_history_stability_releases.json',
    [string]$ReportFile = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
# $PSScriptRoot is empty in param() defaults under Windows PowerShell 5.1, so resolve paths here.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
. (Join-Path $scriptDir 'firefox-pin.ps1')
if (-not $PinFile) { $PinFile = Join-Path $repoRoot 'upstream\firefox.json' }

function Get-ReleaseDate {
    # The release that starts the 3-day clock: the earliest Mozilla release newer than the pin
    # (-IncludePinned: the pinned version itself, for a stale pin), up to and including the latest.
    # Read from both history feeds; falls back to the feed's LAST_RELEASE_DATE. Never throws.
    # Exception text goes to stderr only, never into Source: the issue body must not change
    # because a feed had a hiccup.
    param($Pinned, $Latest, [string]$LatestText, [bool]$IncludePinned, $Feed)

    $best = $null
    $failed = $false
    foreach ($url in @($MajorHistoryUrl, $StabilityHistoryUrl)) {
        try {
            $history = Invoke-RestMethod -Uri $url -UseBasicParsing -TimeoutSec 60
        } catch {
            [Console]::Error.WriteLine("Release history unavailable: $url : $($_.Exception.Message)")
            $failed = $true
            continue
        }
        foreach ($p in $history.PSObject.Properties) {
            $name = [string]$p.Name
            $date = [string]$p.Value
            if ($name -notmatch '^\d+(\.\d+){1,3}\z' -or $date -notmatch '^\d{4}-\d{2}-\d{2}\z') { continue }
            $v = ConvertTo-FirefoxVersion $name
            if ($v -gt $Latest) { continue }
            if ($IncludePinned) { if ($v -lt $Pinned) { continue } } elseif ($v -le $Pinned) { continue }
            if (-not $best -or [string]::CompareOrdinal($date, $best.Date) -lt 0 -or
                ($date -eq $best.Date -and $v -lt $best.V)) {
                $best = @{ Version = $name; Date = $date; V = $v; Source = $url }
            }
        }
    }
    if ($best) { return $best }
    $last = ''
    if ($Feed.PSObject.Properties.Name -contains 'LAST_RELEASE_DATE') { $last = [string]$Feed.LAST_RELEASE_DATE }
    if ($last -match '^\d{4}-\d{2}-\d{2}\z') {
        return @{ Version = $LatestText; Date = $last
                  Source = "LAST_RELEASE_DATE in $VersionsUrl (no newer release in the release history)" }
    }
    $why = if ($failed) { 'release history unavailable' } else { 'no newer release in the release history' }
    return @{ Version = $null; Date = $null; Source = "unknown: $why" }
}

function Complete-Check {
    # Prints the verdict, writes the report and exits.
    param([int]$Code, [string]$Status, [string]$Message, $Feed, [string]$LatestText, $Pin, $NextReleaseDate)

    $report = [ordered]@{
        status          = $Status
        message         = $Message
        latestVersion   = $LatestText
        pinnedVersion   = $Pin.Version
        pinnedTag       = $Pin.Tag
        pinnedCommit    = $Pin.Commit
        majorsBehind    = 0
        firstNewVersion = $null
        releaseDate     = $null
        releaseDateFrom = $null
        deadline        = $null
        nextReleaseDate = $NextReleaseDate
    }
    if ($Code -eq 0) {
        Write-Host $Message
    } else {
        [Console]::Error.WriteLine($Message)
        $latest = ConvertTo-FirefoxVersion $LatestText
        $pinned = ConvertTo-FirefoxVersion $Pin.Version
        $behind = $latest.Major - $pinned.Major
        if ($behind -gt 0) { $report.majorsBehind = $behind }
        $release = Get-ReleaseDate -Pinned $pinned -Latest $latest -LatestText $LatestText -IncludePinned ($Status -eq 'stale') -Feed $Feed
        $report.firstNewVersion = $release.Version
        $report.releaseDate = $release.Date
        $report.releaseDateFrom = $release.Source
        if ($release.Date) {
            $report.deadline = [datetime]::ParseExact($release.Date, 'yyyy-MM-dd',
                [Globalization.CultureInfo]::InvariantCulture).AddDays(3).ToString('yyyy-MM-dd')
        }
        $firstText = if ($release.Version) { $release.Version } else { 'unknown' }
        $dateText = if ($release.Date) { $release.Date } else { 'unknown' }
        $deadlineText = if ($report.deadline) { $report.deadline } else { 'unknown' }
        [Console]::Error.WriteLine(("First release the pin lacks: {0}, released {1}; Orbis deadline (release + 3 days) {2}; pin is {3} major version(s) behind." -f $firstText, $dateText, $deadlineText, $report.majorsBehind))
        if ($report.majorsBehind -ge 2) {
            [Console]::Error.WriteLine("WARNING: Microsoft Store policy 10.2.1 allows at most 2 major versions behind Firefox.")
        }
    }
    if ($ReportFile) {
        [IO.File]::WriteAllText($ReportFile, (New-Object PSObject -Property $report | ConvertTo-Json),
            (New-Object Text.UTF8Encoding $false))
    }
    exit $Code
}

try {
    if ($ReportFile) {
        $ReportFile = [IO.Path]::GetFullPath($ReportFile)
        if (Test-Path -LiteralPath $ReportFile) { Remove-Item -LiteralPath $ReportFile -Force }
    }
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

    # NEXT_RELEASE_DATE goes into the log and the issue body: accept a plain date only, so a feed
    # value cannot become a workflow command, a Markdown link or an @mention.
    $next = ''
    $nextDate = $null
    if ($feed.PSObject.Properties.Name -contains 'NEXT_RELEASE_DATE' -and
        ([string]$feed.NEXT_RELEASE_DATE) -match '^\d{4}-\d{2}-\d{2}\z') {
        $nextDate = [string]$feed.NEXT_RELEASE_DATE
        $next = "; next release date in feed: $nextDate"
    }
    $done = @{ Feed = $feed; LatestText = $latestText; Pin = $pin; NextReleaseDate = $nextDate }

    if ($latest -gt $pinned) {
        Complete-Check @done -Code 1 -Status 'behind' -Message ("BEHIND: Mozilla's latest Firefox is {0}, newer than the pinned {1} ({2}){3}. See docs/UPDATING.md." -f $latestText, $pin.Version, $pin.Tag, $next)
    }
    if ($latest -lt $pinned) {
        Complete-Check @done -Code 0 -Status 'current' -Message ("OK: pinned {0} ({1}) is ahead of Mozilla's latest release {2}{3}" -f $pin.Version, $pin.Tag, $latestText, $next)
    }

    # Same version as the release: the pin must be the _RELEASE tag, and that tag must be the pinned
    # commit. A release-candidate (_BUILD) pin left over after release day is stale.
    if ($pin.Tag -notmatch '_RELEASE\z') {
        Complete-Check @done -Code 1 -Status 'stale' -Message ("STALE: {0} has been released, but the pin is still the release candidate {1}. Switch to the _RELEASE tag. See docs/UPDATING.md." -f $latestText, $pin.Tag)
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
        Complete-Check @done -Code 1 -Status 'stale' -Message ("STALE: tag {0} is not on {1}, but Mozilla lists {2} as released. See docs/UPDATING.md." -f $pin.Tag, $pin.Repository, $latestText)
    }
    if ($remoteCommit -ne $pin.Commit) {
        Complete-Check @done -Code 1 -Status 'stale' -Message ("STALE: remote tag {0} points at {1}, but the pin says {2}. See docs/UPDATING.md." -f $pin.Tag, $remoteCommit, $pin.Commit)
    }
    Complete-Check @done -Code 0 -Status 'current' -Message ("OK: pinned {0} ({1} = {2}) equals Mozilla's latest release {3}{4}" -f $pin.Version, $pin.Tag, $pin.Commit, $latestText, $next)
} catch {
    [Console]::Error.WriteLine("ERROR: currency check failed: " + $_.Exception.Message)
    exit 2
}
