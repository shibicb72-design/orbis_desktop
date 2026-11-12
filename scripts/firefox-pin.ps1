# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Shared helpers, dot-sourced by the scripts in this folder.
# Windows PowerShell 5.1 compatible. Keep this file ASCII.

function Read-FirefoxPin {
    # Reads and validates upstream/firefox.json. Throws on anything unexpected.
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Pin file not found: $Path"
    }
    $pin = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json

    $repository = [string]$pin.repository
    $tag = [string]$pin.tag
    $commit = [string]$pin.commit

    if ([string]::IsNullOrWhiteSpace($repository)) { throw "Pin file has no 'repository': $Path" }
    $m = [regex]::Match($tag, '^FIREFOX_(\d+)_(\d+)(?:_(\d+))?_(?:RELEASE|BUILD\d+)\z')
    if (-not $m.Success) {
        throw "Pin file 'tag' is not a Firefox release tag (FIREFOX_<major>_<minor>[_<patch>]_RELEASE or _BUILD<n>): '$tag'"
    }
    if ($commit -cnotmatch '^[0-9a-f]{40}\z') {
        throw "Pin file 'commit' must be a full 40-character lower-case hex SHA-1: '$commit'"
    }

    $version = $m.Groups[1].Value + '.' + $m.Groups[2].Value
    if ($m.Groups[3].Success) { $version += '.' + $m.Groups[3].Value }

    New-Object PSObject -Property @{
        Repository = $repository
        Tag        = $tag
        Commit     = $commit
        Version    = $version
    }
}

function ConvertTo-FirefoxVersion {
    # '160.0' -> [version]'160.0.0.0'. Padding avoids [version]'160.0' -lt [version]'160.0.0'.
    param([Parameter(Mandatory = $true)][string]$Text)

    if ($Text -notmatch '^\d+(\.\d+){1,3}\z') {
        throw "Not a plain Firefox release version: '$Text'"
    }
    $parts = @($Text.Split('.'))
    while ($parts.Count -lt 4) { $parts += '0' }
    New-Object System.Version ($parts -join '.')
}
