# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

<#
.SYNOPSIS
Offline test of check-firefox-currency.ps1 and sync-currency-issue.ps1 -DryRun.

.DESCRIPTION
Runs the currency check with test pins against local feed files (file:// URLs)
and a throw-away local git repository as the "Firefox" remote, then checks the
exit codes, the JSON report and the issue text. Needs git; no network, no gh,
no GitHub. Everything is written to a new folder under %TEMP%, which is deleted
at the end.

Prints one PASS or FAIL line per case. Exit code 0 when every case passes.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tests\test-firefox-currency.ps1
#>
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$check = Join-Path $repoRoot 'scripts\check-firefox-currency.ps1'
$sync = Join-Path $repoRoot 'scripts\sync-currency-issue.ps1'

$work = Join-Path ([IO.Path]::GetTempPath()) ('orbis-currency-test-' + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $work
$script:failures = 0

function Write-Utf8 ([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding $false))
}
function Get-FileUrl ([string]$Name) { ([Uri](Join-Path $work $Name)).AbsoluteUri }

function New-Feed ([string]$Name, [string]$Latest, [string]$LastReleaseDate = '2026-11-10') {
    $lrd = if ($LastReleaseDate) { ",`"LAST_RELEASE_DATE`":`"$LastReleaseDate`"" } else { '' }
    Write-Utf8 (Join-Path $work $Name) ("{`"LATEST_FIREFOX_VERSION`":`"$Latest`",`"NEXT_RELEASE_DATE`":`"2026-12-08`"$lrd}")
    Get-FileUrl $Name
}

function New-Pin ([string]$Tag, [string]$Commit, [string]$Repository) {
    $path = Join-Path $work ("pin-" + [guid]::NewGuid().ToString('N') + '.json')
    Write-Utf8 $path ("{`"repository`":`"$($Repository -replace '\\', '\\')`",`"tag`":`"$Tag`",`"commit`":`"$Commit`"}")
    $path
}

function Assert-Case ([string]$Name, [bool]$Ok, [string]$Detail) {
    if ($Ok) { Write-Host "PASS  $Name" } else { Write-Host "FAIL  $Name : $Detail"; $script:failures++ }
}

function Invoke-Check ([string]$Pin, [string]$Feed, [string]$Major, [string]$Stability) {
    $ErrorActionPreference = 'Continue'   # stderr lines are output here, not errors
    $report = Join-Path $work 'report.json'
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $check -PinFile $Pin -VersionsUrl $Feed `
        -MajorHistoryUrl $Major -StabilityHistoryUrl $Stability -ReportFile $report 2>&1 | ForEach-Object { "$_" }
    $r = $null
    if (Test-Path -LiteralPath $report) { $r = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json }
    New-Object PSObject -Property @{ Code = $LASTEXITCODE; Out = ($out -join "`n"); Report = $r; Path = $report }
}

function Invoke-SyncDryRun ([string]$Report, [string]$Today) {
    $ErrorActionPreference = 'Continue'
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $sync -ReportFile $Report -Today $Today -DryRun 2>&1 |
        ForEach-Object { "$_" }
    New-Object PSObject -Property @{ Code = $LASTEXITCODE; Out = ($out -join "`n") }
}

try {
    # A local git repository stands in for mozilla-firefox/firefox.
    $remote = Join-Path $work 'remote'
    $null = New-Item -ItemType Directory -Path $remote
    $saved = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & git -C $remote init -q 2>&1 | Out-Null
    & git -C $remote -c user.name=test -c user.email=test@example.invalid commit -q --allow-empty -m test 2>&1 | Out-Null
    & git -C $remote tag FIREFOX_160_0_RELEASE 2>&1 | Out-Null
    $commit = (& git -C $remote rev-parse HEAD).Trim()
    $ErrorActionPreference = $saved
    if ($commit -notmatch '^[0-9a-f]{40}\z') { throw "Could not create the test git repository in $remote" }
    $other = '0000000000000000000000000000000000000001'

    Write-Utf8 (Join-Path $work 'major.json') '{"157.0":"2026-09-29","158.0":"2026-10-13","159.0":"2026-10-27","160.0":"2026-11-10"}'
    Write-Utf8 (Join-Path $work 'stability.json') '{"115.45.0":"2026-11-10","159.0.1":"2026-11-03","160.0.1":"2026-11-17","160.0.2":"2026-11-24"}'
    $major = Get-FileUrl 'major.json'
    $stab = Get-FileUrl 'stability.json'
    $missing = Get-FileUrl 'does-not-exist.json'
    $feed160 = New-Feed 'feed160.json' '160.0'

    # 1. Pin equals the release, _RELEASE tag at the pinned commit.
    $r = Invoke-Check (New-Pin 'FIREFOX_160_0_RELEASE' $commit $remote) $feed160 $major $stab
    Assert-Case 'current pin: exit 0, status current' ($r.Code -eq 0 -and $r.Report.status -eq 'current' -and $r.Out -match '^OK: pinned 160\.0') "$($r.Code) $($r.Out)"
    $s = Invoke-SyncDryRun $r.Path '2026-11-12'
    Assert-Case 'current pin: sync would close the issue' ($s.Code -eq 0 -and $s.Out -match 'would close') $s.Out

    # 2. One major behind.
    $r = Invoke-Check (New-Pin 'FIREFOX_159_0_1_RELEASE' $other $remote) $feed160 $major $stab
    $ok = $r.Code -eq 1 -and $r.Report.status -eq 'behind' -and $r.Report.majorsBehind -eq 1 -and $r.Report.firstNewVersion -eq '160.0' -and
          $r.Report.releaseDate -eq '2026-11-10' -and $r.Report.deadline -eq '2026-11-13' -and $r.Report.releaseDateFrom -eq $major -and
          $r.Report.nextReleaseDate -eq '2026-12-08' -and $r.Out -match 'next release date in feed: 2026-12-08'
    Assert-Case '159.0.1 vs 160.0: behind, 1 major, released 2026-11-10, deadline 2026-11-13' $ok "$($r.Code) $($r.Out)"
    $s = Invoke-SyncDryRun $r.Path '2026-11-12'
    $ok = $s.Code -eq 0 -and $s.Out -match '\| Latest Firefox \| 160\.0 \|' -and $s.Out -match '\| First release the pin lacks \| 160\.0 \|' -and
          $s.Out -match '\| Mozilla release date of 160\.0 \| 2026-11-10 \|' -and
          $s.Out -match '\| Orbis deadline \(release \+ 3 days\) \| 2026-11-13 \|' -and $s.Out -match '\| Major versions behind \| 1 \|' -and
          $s.Out -notmatch '10\.2\.1' -and $s.Out -notmatch '2026-11-13 \(passed\)'
    Assert-Case '159.0.1 vs 160.0: issue body has version, dates, majors, no Store warning' $ok $s.Out
    $s = Invoke-SyncDryRun $r.Path '2026-11-14'
    Assert-Case '159.0.1 vs 160.0: deadline marked passed on 2026-11-14' ($s.Out -match '2026-11-13 \(passed\)') $s.Out

    # 2b. The deadline counts from the first release the pin lacks, not the latest.
    $r = Invoke-Check (New-Pin 'FIREFOX_159_0_RELEASE' $other $remote) $feed160 $major $stab
    $ok = $r.Code -eq 1 -and $r.Report.firstNewVersion -eq '159.0.1' -and $r.Report.releaseDate -eq '2026-11-03' -and $r.Report.deadline -eq '2026-11-06'
    Assert-Case '159.0 vs 160.0: clock starts at 159.0.1 (2026-11-03), deadline 2026-11-06' $ok "$($r.Code) $($r.Out)"
    $r = Invoke-Check (New-Pin 'FIREFOX_160_0_RELEASE' $commit $remote) (New-Feed 'feed16002.json' '160.0.2') $major $stab
    $ok = $r.Code -eq 1 -and $r.Report.latestVersion -eq '160.0.2' -and $r.Report.firstNewVersion -eq '160.0.1' -and
          $r.Report.releaseDate -eq '2026-11-17' -and $r.Report.deadline -eq '2026-11-20'
    Assert-Case '160.0 vs 160.0.2 (160.0.1 on 11-17, 160.0.2 on 11-24): deadline 2026-11-20' $ok "$($r.Code) $($r.Out)"
    $s = Invoke-SyncDryRun $r.Path '2026-11-20'
    Assert-Case '160.0 vs 160.0.2: not passed on 2026-11-20' ($s.Out -match '\| 2026-11-20 \|' -and $s.Out -notmatch '2026-11-20 \(passed\)') $s.Out
    $s = Invoke-SyncDryRun $r.Path '2026-11-21'
    Assert-Case '160.0 vs 160.0.2: passed on 2026-11-21' ($s.Out -match '\| 2026-11-20 \(passed\) \|') $s.Out

    # 3. Two majors behind: Store 10.2.1 warning.
    $r = Invoke-Check (New-Pin 'FIREFOX_158_0_RELEASE' $other $remote) $feed160 $major $stab
    $s = Invoke-SyncDryRun $r.Path '2026-11-12'
    $ok = $r.Code -eq 1 -and $r.Report.majorsBehind -eq 2 -and $r.Out -match 'WARNING: Microsoft Store policy 10\.2\.1' -and
          $s.Out -match 'Warning, Microsoft Store policy 10\.2\.1'
    Assert-Case '158.0 vs 160.0: 2 majors, Store 10.2.1 warning' $ok "$($r.Out)`n$($s.Out)"

    # 4. Three majors behind: out of policy.
    $r = Invoke-Check (New-Pin 'FIREFOX_157_0_RELEASE' $other $remote) $feed160 $major $stab
    $s = Invoke-SyncDryRun $r.Path '2026-11-12'
    Assert-Case '157.0 vs 160.0: 3 majors, out of Store policy' ($r.Report.majorsBehind -eq 3 -and $s.Out -match 'Out of Microsoft Store policy 10\.2\.1') $s.Out

    # 5. Dot release: date from the stability history.
    $r = Invoke-Check (New-Pin 'FIREFOX_160_0_RELEASE' $commit $remote) (New-Feed 'feed16001.json' '160.0.1') $major $stab
    $ok = $r.Code -eq 1 -and $r.Report.majorsBehind -eq 0 -and $r.Report.releaseDate -eq '2026-11-17' -and $r.Report.deadline -eq '2026-11-20' -and $r.Report.releaseDateFrom -eq $stab
    Assert-Case '160.0 vs 160.0.1: behind, 0 majors, date from stability history' $ok "$($r.Code) $($r.Out)"

    # 6. Version not in the history yet: LAST_RELEASE_DATE.
    $r = Invoke-Check (New-Pin 'FIREFOX_160_0_2_RELEASE' $other $remote) (New-Feed 'feed161.json' '161.0' '2026-12-08') $major $stab
    $ok = $r.Code -eq 1 -and $r.Report.releaseDate -eq '2026-12-08' -and $r.Report.deadline -eq '2026-12-11' -and $r.Report.releaseDateFrom -match '^LAST_RELEASE_DATE'
    Assert-Case '160.0.2 vs 161.0 not in history: LAST_RELEASE_DATE fallback' $ok "$($r.Code) $($r.Out)"

    # 6b. NEXT_RELEASE_DATE injection: a workflow command, an @mention, an image and a backtick.
    Write-Utf8 (Join-Path $work 'feedevil.json') '{"LATEST_FIREFOX_VERSION":"160.0","LAST_RELEASE_DATE":"2026-11-10","NEXT_RELEASE_DATE":"2026-12-08\n::error::injected @someone ![x](https://example.invalid/x.png) `"}'
    $r = Invoke-Check (New-Pin 'FIREFOX_159_0_1_RELEASE' $other $remote) (Get-FileUrl 'feedevil.json') $major $stab
    $s = Invoke-SyncDryRun $r.Path '2026-11-12'
    $bad = '::error|injected|@someone|example\.invalid|next release date'
    $ok = $r.Code -eq 1 -and $null -eq $r.Report.nextReleaseDate -and $r.Out -notmatch $bad -and
          $r.Report.message -notmatch $bad -and $s.Code -eq 0 -and $s.Out -notmatch $bad
    Assert-Case 'NEXT_RELEASE_DATE injection: dropped from log, report and issue body' $ok "$($r.Out)`n$($s.Out)"

    # 7. History feeds unreachable and no LAST_RELEASE_DATE: still exit 1, date unknown.
    $r = Invoke-Check (New-Pin 'FIREFOX_159_0_RELEASE' $other $remote) (New-Feed 'feednolrd.json' '160.0' '') $missing $missing
    $s = Invoke-SyncDryRun $r.Path '2026-11-12'
    $ok = $r.Code -eq 1 -and $null -eq $r.Report.releaseDate -and $null -eq $r.Report.deadline -and $s.Out -match '\| Mozilla release date of unknown \| unknown \|' -and
          $s.Out -match 'Release date source: unknown: release history unavailable' -and $s.Out -notmatch 'does-not-exist'
    Assert-Case 'history unreachable: still behind (exit 1), date unknown' $ok "$($r.Code) $($r.Out)`n$($s.Out)"

    # 8. Release candidate left over after release day.
    $r = Invoke-Check (New-Pin 'FIREFOX_160_0_BUILD1' $commit $remote) $feed160 $major $stab
    Assert-Case '160.0 BUILD1 after release: stale, exit 1, clock from 160.0 (2026-11-10)' ($r.Code -eq 1 -and $r.Report.status -eq 'stale' -and $r.Out -match '^STALE: 160\.0 has been released' -and $r.Report.firstNewVersion -eq '160.0' -and $r.Report.deadline -eq '2026-11-13') "$($r.Code) $($r.Out)"

    # 9. _RELEASE tag at another commit.
    $r = Invoke-Check (New-Pin 'FIREFOX_160_0_RELEASE' $other $remote) $feed160 $major $stab
    Assert-Case '160.0 RELEASE at wrong commit: stale, exit 1' ($r.Code -eq 1 -and $r.Report.status -eq 'stale' -and $r.Out -match 'STALE: remote tag') "$($r.Code) $($r.Out)"

    # 10. Ahead of Mozilla.
    $r = Invoke-Check (New-Pin 'FIREFOX_161_0_BUILD1' $other $remote) $feed160 $major $stab
    Assert-Case '161.0 BUILD1 vs 160.0: ahead, exit 0' ($r.Code -eq 0 -and $r.Report.status -eq 'current' -and $r.Out -match 'is ahead') "$($r.Code) $($r.Out)"

    # 11. Check errors: exit 2 and no report, so the workflow touches no issue.
    $r = Invoke-Check (New-Pin 'FIREFOX_159_0_RELEASE' $other $remote) $missing $major $stab
    Assert-Case 'feed unreachable: exit 2, no report' ($r.Code -eq 2 -and $null -eq $r.Report -and $r.Out -match '^ERROR: currency check failed') "$($r.Code) $($r.Out)"
    Write-Utf8 (Join-Path $work 'badfeed.json') '{"LATEST_FIREFOX_VERSION":"161.0b2"}'
    $r = Invoke-Check (New-Pin 'FIREFOX_159_0_RELEASE' $other $remote) (Get-FileUrl 'badfeed.json') $major $stab
    Assert-Case 'beta version in feed: exit 2, no report' ($r.Code -eq 2 -and $null -eq $r.Report) "$($r.Code) $($r.Out)"
    $r = Invoke-Check (New-Pin 'FIREFOX_160_0_RELEASE' $commit (Join-Path $work 'no-such-remote')) $feed160 $major $stab
    Assert-Case 'git remote unreachable: exit 2, no report' ($r.Code -eq 2 -and $null -eq $r.Report) "$($r.Code) $($r.Out)"
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}

if ($script:failures) { Write-Host "$($script:failures) case(s) failed"; exit 1 }
Write-Host 'All cases passed'
exit 0
