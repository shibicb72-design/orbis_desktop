# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

<#
.SYNOPSIS
Opens, updates or closes the "firefox-update" GitHub issue from a currency report.

.DESCRIPTION
Reads the JSON report written by check-firefox-currency.ps1 -ReportFile and
keeps one issue in step with it, through the GitHub CLI (gh). Used by
.github/workflows/firefox-currency.yml with the workflow's GITHUB_TOKEN.

The issue is found by its exact title among open issues labelled
firefox-update. Other issues with that label are never touched.

status behind or stale:
  no open issue  -> create it (and the label, if missing);
  open issue     -> if the body changed, replace it and add one comment;
                    otherwise do nothing (no daily noise).
status current:
  open issue     -> close it with a comment.

.PARAMETER ReportFile
Report from check-firefox-currency.ps1 -ReportFile.

.PARAMETER Repository
owner/name. Default: $env:GITHUB_REPOSITORY.

.PARAMETER RunUrl
Link to the workflow run, used in comments.

.PARAMETER Today
Date (yyyy-MM-dd) used to mark the deadline as passed. Default: today (UTC).

.PARAMETER DryRun
Print the title, body and planned action; call nothing.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sync-currency-issue.ps1 -ReportFile report.json -DryRun
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ReportFile,
    [string]$Repository = $env:GITHUB_REPOSITORY,
    [string]$RunUrl = '',
    [string]$Today = '',
    [switch]$DryRun
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Title = 'Firefox pin is out of date'
$Label = 'firefox-update'

function Invoke-Gh {
    # Runs gh with the arguments as given and returns its stdout as one string; throws on a
    # non-zero exit code. No param() block, so "--repo" and the like reach gh unchanged.
    $out = & gh @args
    if ($LASTEXITCODE -ne 0) { throw "gh $($args[0]) $($args[1]) failed (exit $LASTEXITCODE)" }
    ($out | ForEach-Object { "$_" }) -join "`n"
}

function New-IssueBody {
    param($Report, [string]$Today)

    # Every value below comes from the report, whose fields check-firefox-currency.ps1 has validated
    # (versions, dates, tag, SHA) or built itself. No exception text, so feed hiccups do not change it.
    $first = if ($Report.firstNewVersion) { $Report.firstNewVersion } else { 'unknown' }
    $release = if ($Report.releaseDate) { $Report.releaseDate } else { 'unknown' }
    $deadline = if ($Report.deadline) { $Report.deadline } else { 'unknown' }
    if ($Report.deadline -and $Today -and ([string]::CompareOrdinal($Today, $Report.deadline) -gt 0)) {
        $deadline += ' (passed)'
    }
    $lines = @(
        '<!-- Written by .github/workflows/firefox-currency.yml (scripts/sync-currency-issue.ps1). Edits are overwritten. -->',
        '',
        ('`{0}`' -f $Report.message),
        '',
        '| | |',
        '|---|---|',
        ('| Latest Firefox | {0} |' -f $Report.latestVersion),
        ('| First release the pin lacks | {0} |' -f $first),
        ('| Mozilla release date of {0} | {1} |' -f $first, $release),
        ('| Orbis deadline (release + 3 days) | {0} |' -f $deadline),
        ('| Pinned | {0} (`{1}`, `{2}`) |' -f $Report.pinnedVersion, $Report.pinnedTag, $Report.pinnedCommit),
        ('| Major versions behind | {0} |' -f $Report.majorsBehind),
        ''
    )
    if ($Report.majorsBehind -gt 2) {
        $lines += @('**Out of Microsoft Store policy 10.2.1:** the engine is more than 2 major versions behind Firefox.', '')
    } elseif ($Report.majorsBehind -eq 2) {
        $lines += @('**Warning, Microsoft Store policy 10.2.1:** the engine is 2 major versions behind Firefox, the most the policy allows. The next Firefox release puts Orbis out of policy.', '')
    }
    $lines += @(
        ('Release date source: {0}' -f $Report.releaseDateFrom),
        '',
        'The deadline counts from the first release the pin lacks; later releases do not move it. "(passed)" uses the UTC date of the run.',
        '',
        'Move the pin as described in `docs/UPDATING.md`. This issue closes itself when the daily check passes.'
    )
    ($lines -join "`n")
}

function Get-OpenIssues {
    $json = Invoke-Gh issue list --repo $Repository --state open --label $Label --limit 100 --json 'number,title,body'
    @($json | ConvertFrom-Json | ForEach-Object { $_ } | Where-Object { $_.title -ceq $Title })
}

try {
    [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
    $report = Get-Content -LiteralPath $ReportFile -Raw | ConvertFrom-Json
    if (-not $Today) { $Today = [datetime]::UtcNow.ToString('yyyy-MM-dd') }
    if (-not $DryRun -and -not $Repository) { throw 'No repository: pass -Repository or set GITHUB_REPOSITORY.' }
    $runNote = if ($RunUrl) { " Run: $RunUrl" } else { '' }
    # Windows PowerShell 5.1 does not escape embedded double quotes in native arguments.
    $runNote = $runNote -replace '"', "'"
    $report.message = ([string]$report.message) -replace '"', "'"

    switch ($report.status) {
        'current' {
            if ($DryRun) { Write-Host "DRY RUN: would close any open '$Title' issue labelled $Label. $($report.message)"; break }
            $open = Get-OpenIssues
            if ($open.Count -eq 0) { Write-Host 'Pin is current; no open issue.'; break }
            foreach ($issue in $open) {
                $null = Invoke-Gh issue close $issue.number --repo $Repository --reason completed --comment ("The daily check passes: ``{0}``.{1}" -f $report.message, $runNote)
                Write-Host "Closed issue #$($issue.number)."
            }
        }
        { $_ -in @('behind', 'stale') } {
            $body = New-IssueBody -Report $report -Today $Today
            if ($DryRun) {
                Write-Host "DRY RUN: would create or update the issue '$Title' (label $Label):"
                Write-Host $body
                break
            }
            $open = Get-OpenIssues
            $bodyFile = Join-Path ([IO.Path]::GetTempPath()) ('firefox-currency-issue-' + [guid]::NewGuid().ToString('N') + '.md')
            [IO.File]::WriteAllText($bodyFile, $body, (New-Object Text.UTF8Encoding $false))
            try {
                if ($open.Count -eq 0) {
                    $labels = Invoke-Gh label list --repo $Repository --search $Label --limit 100 --json name
                    if (-not @($labels | ConvertFrom-Json | ForEach-Object { $_ } | Where-Object { $_.name -ceq $Label }).Count) {
                        $null = Invoke-Gh label create $Label --repo $Repository --color 'b60205' --description 'Pinned Firefox is behind Mozilla (opened by the daily currency check)'
                    }
                    $url = Invoke-Gh issue create --repo $Repository --title $Title --label $Label --body-file $bodyFile
                    Write-Host "Opened $url"
                } else {
                    $issue = $open[0]
                    $old = ([string]$issue.body) -replace "`r`n", "`n"
                    if ($old.Trim() -ceq $body.Trim()) {
                        Write-Host "Issue #$($issue.number) is already up to date."
                    } else {
                        $null = Invoke-Gh issue edit $issue.number --repo $Repository --body-file $bodyFile
                        $null = Invoke-Gh issue comment $issue.number --repo $Repository --body ("Updated: ``{0}``.{1}" -f $report.message, $runNote)
                        Write-Host "Updated issue #$($issue.number)."
                    }
                }
            } finally {
                Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue
            }
        }
        default { throw "Unknown status in ${ReportFile}: '$($report.status)'" }
    }
    exit 0
} catch {
    [Console]::Error.WriteLine("ERROR: issue sync failed: " + $_.Exception.Message)
    exit 1
}
