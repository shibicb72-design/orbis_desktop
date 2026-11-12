# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

<#
.SYNOPSIS
Makes an unsigned Orbis MSIX from the packaged build with mach repackage msix, then checks what is inside.

.DESCRIPTION
Option A of docs\BUILD.md: the input is a folder, not the zip, so that Orbis's policy files are in the package.

1. Checks: every path on drive C: and outside this repository; the Firefox checkout has patch 0004 applied (the
   MSIX template's Mozilla distribution.ini is gone); the build's zip and the checkout's orbis-dist exist.
2. Stages a new folder: the zip's orbis\ folder plus orbis-dist (orbis.cfg, defaults\pref\autoconfig.js,
   distribution\policies.json), the same layout as the test install in docs\BUILD.md.
3. Runs ./mach repackage msix in MozillaBuild's shell with the values from packaging\msix-config.json and the
   version computed from application.ini (docs\MSIX.md, "Version").
4. Unpacks the MSIX with makeappx and checks it: AppxManifest.xml identity, publisher and display names equal
   the config, the capabilities are exactly the config's list, the logo assets are byte-identical to the
   config's assets folder, the three policy files are in the install folder and identical to orbis-dist, and
   there is no distribution.ini anywhere in the package. The assets check is two-way: the package also has no
   asset file that the config's folder lacks.
5. Reports, without failing, every "Mozilla" or "Firefox" left in the package's file names and in the version
   resources (CompanyName, ProductName, ...) of its .exe and .dll files (docs\BRANDING.md, open items).
6. Prints the MSIX's SHA-256 and writes it to <output>.sha256 next to the package. With -CheckOnly it compares
   with that file instead and fails on a mismatch or a missing file. The .sha256 guards against installing a
   stale or wrong file, not against tampering: anything that can change the package can change it too.

While packaging/msix-config.json still holds TODO-STORE placeholders, the script prints a warning block;
-RequireStoreIdentity refuses them instead.

It never signs, installs or trusts anything: no certificate, no Add-AppxPackage, no Developer Mode.
Writes under -WorkDir (stage, unpack check, mach log), -Output and <output>.sha256. A stage or check folder from
an earlier run is deleted only if it holds this script's marker file. mach itself also writes its temporary
copy of the package to %USERPROFILE%\.mozbuild\cache\mach-msix\msix-temp-<channel>\ and replaces it on every
run; this script leaves that folder alone.

Exit code 0: MSIX written and every check passed. 1: refused or a check failed.

.PARAMETER Checkout
Firefox checkout. Default: %USERPROFILE%\orbis_desktop_src\firefox

.PARAMETER Zip
The build's application zip. Default: the single orbis-*.en-US.win64.zip in <objdir>\dist next to the checkout
(%USERPROFILE%\orbis_desktop_src\obj-orbis\dist).

.PARAMETER WorkDir
Folder for the stage, the unpack check and the logs. Default: %USERPROFILE%\orbis_desktop_src\msix-work, or
...\msix-work-unsigned-test with -AllowUnsignedInstall, so that a test build never overwrites the Store build's
folder.

.PARAMETER Output
The .msix to write. Default: %USERPROFILE%\orbis_desktop_src\msix\<identityName>_<version>_x64.msix

.PARAMETER Config
Default: packaging\msix-config.json in this repository.

.PARAMETER CheckOnly
Skip staging and mach; only unpack and check the existing -Output, and compare its SHA-256 with <output>.sha256
(never rewritten by -CheckOnly).

.PARAMETER AllowUnsignedInstall
For a local test only, never for the Store: passes --unsigned to mach, which appends Microsoft's
"unsigned package" OID to the publisher, so that an administrator can install it with
Add-AppxPackage -AllowUnsigned (docs\MSIX.md, "Local install test"). Output name ends in _unsigned-test.msix;
the default work folder is msix-work-unsigned-test.

.PARAMETER RequireStoreIdentity
Refuse (exit 1) while identityName, publisher or publisherDisplayName still holds a TODO-STORE placeholder.
Use it for every build meant for upload.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\make-msix.ps1
#>
[CmdletBinding()]
param(
    [string]$Checkout = '',
    [string]$Zip = '',
    [string]$WorkDir = '',
    [string]$Output = '',
    [string]$Config = '',
    [switch]$CheckOnly,
    [switch]$AllowUnsignedInstall,
    [switch]$RequireStoreIdentity
)

Set-StrictMode -Version 2.0
$script:cmdlet = $PSCmdlet
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $scriptDir)).TrimEnd('\')
$src = Join-Path $env:USERPROFILE 'orbis_desktop_src'
if (-not $Checkout) { $Checkout = Join-Path $src 'firefox' }
if (-not $WorkDir) {
    if ($AllowUnsignedInstall) { $WorkDir = Join-Path $src 'msix-work-unsigned-test' }
    else { $WorkDir = Join-Path $src 'msix-work' }
}
if (-not $Config) { $Config = Join-Path $repoRoot 'packaging\msix-config.json' }
$Marker = '.orbis-make-msix'
$failures = New-Object System.Collections.ArrayList

function Get-FullPathOnC {
    param([string]$Path, [string]$What)
    $p = [System.IO.Path]::GetFullPath($script:cmdlet.GetUnresolvedProviderPathFromPSPath($Path)).TrimEnd('\')
    if (-not $p.StartsWith('C:\', [StringComparison]::OrdinalIgnoreCase) -or $p.Length -le 3) {
        throw "REFUSED: $What must be on drive C: '$p'"
    }
    $r = $repoRoot + '\'
    if (($p + '\').StartsWith($r, [StringComparison]::OrdinalIgnoreCase)) {
        throw "REFUSED: $What must be outside the Orbis repository: '$p'"
    }
    $cur = $p
    while ($cur) {
        if (Test-Path -LiteralPath $cur) {
            if ((Get-Item -LiteralPath $cur -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw "REFUSED: '$cur' ($What) is a junction or symbolic link"
            }
        }
        $parent = Split-Path -Parent $cur
        if (-not $parent -or $parent -eq $cur) { break }
        $cur = $parent
    }
    return $p
}

function New-OwnFolder {
    # A new, empty folder with the marker. An existing folder is deleted only if it holds the marker.
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        if (-not (Test-Path -LiteralPath (Join-Path $Path $Marker))) {
            throw "REFUSED: '$Path' exists and was not made by this script (no $Marker); move it away first"
        }
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $Path $Marker) -Value 'made by scripts/make-msix.ps1' -Encoding ascii
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Add-Failure {
    param([string]$Text)
    [void]$failures.Add($Text)
    Write-Host "FAIL: $Text"
}

function Find-MakeAppx {
    $roots = @((Join-Path $env:USERPROFILE '.mozbuild\vs\Windows Kits\10\bin'),
               'C:\Program Files (x86)\Windows Kits\10\bin')
    foreach ($root in $roots) {
        if (Test-Path -LiteralPath $root) {
            $found = @(Get-ChildItem -LiteralPath $root -Directory | Sort-Object Name -Descending |
                ForEach-Object { Join-Path $_.FullName 'x64\makeappx.exe' } |
                Where-Object { Test-Path -LiteralPath $_ })
            if ($found.Count -gt 0) { return $found[0] }
        }
    }
    throw 'makeappx.exe not found (Windows SDK from mach bootstrap or Windows Kits)'
}

function Get-MsixVersion {
    # Firefox X.Y[.Z] and Orbis revision R (0-99) -> X.Y.(Z*100+R).0. The last part stays 0 (Store rule).
    param([string]$AppVersion, [int]$Revision)
    if ($AppVersion -notmatch '^(\d+)\.(\d+)(?:\.(\d+))?$') {
        throw "application.ini Version '$AppVersion' is not a release version X.Y or X.Y.Z"
    }
    $z = 0
    if ($Matches[3]) { $z = [int]$Matches[3] }
    if ($Revision -lt 0 -or $Revision -gt 99) { throw "orbisRevision must be 0 to 99, not $Revision" }
    $third = $z * 100 + $Revision
    if ([int]$Matches[1] -gt 65535 -or [int]$Matches[2] -gt 65535 -or $third -gt 65535) {
        throw "version part over 65535 for $AppVersion revision $Revision"
    }
    return '{0}.{1}.{2}.0' -f $Matches[1], $Matches[2], $third
}

try {
    # --- Config ------------------------------------------------------------------------------------
    $cfg = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
    foreach ($k in 'identityName', 'publisher', 'publisherDisplayName', 'displayName', 'channel', 'arch',
                   'orbisRevision', 'capabilities', 'assets') {
        if ($null -eq $cfg.$k) { throw "$Config has no '$k'" }
    }
    $placeholders = @('identityName', 'publisher', 'publisherDisplayName' | Where-Object { $cfg.$_ -match 'TODO' })
    if ($placeholders.Count -gt 0) {
        $list = ($placeholders | ForEach-Object { "$_='$($cfg.$_)'" }) -join ', '
        if ($RequireStoreIdentity) {
            throw "REFUSED: -RequireStoreIdentity, but the config still has placeholders: $list (docs\MSIX.md)"
        }
        $bar = '!' * 78
        Write-Warning $bar
        Write-Warning 'STORE IDENTITY IS STILL A PLACEHOLDER. THIS PACKAGE CANNOT BE UPLOADED TO THE STORE.'
        Write-Warning "  $list"
        Write-Warning '  Fill in the Partner Center values (docs\MSIX.md) and build with -RequireStoreIdentity.'
        Write-Warning $bar
    }
    $displayNoSpaces = $cfg.displayName -replace ' ', ''
    # mach builds the identity as <vendor>.<identity-name without spaces>, and uses --identity-name as the tile
    # name and the install folder name. So the config's identity must end in ".<displayName without spaces>".
    $suffix = '.' + $displayNoSpaces
    if (-not $cfg.identityName.EndsWith($suffix, [StringComparison]::Ordinal) -or
        $cfg.identityName.Length -le $suffix.Length) {
        throw ("identityName '{0}' must be '<prefix>{1}': mach repackage msix makes the identity from --vendor " +
               "and --identity-name (docs\MSIX.md)") -f $cfg.identityName, $suffix
    }
    $vendor = $cfg.identityName.Substring(0, $cfg.identityName.Length - $suffix.Length)
    if ($cfg.identityName -notmatch '^[-.A-Za-z0-9]{3,50}$') {
        throw "identityName '$($cfg.identityName)' is not a valid package name ([-.A-Za-z0-9], 3 to 50 characters)"
    }
    if ($cfg.arch -ne 'x86_64') { throw "only arch x86_64 is built (config says '$($cfg.arch)')" }
    $assetsDir = Join-Path $repoRoot ($cfg.assets -replace '/', '\')
    if (-not (Test-Path -LiteralPath $assetsDir -PathType Container)) { throw "assets folder '$assetsDir' not found" }

    # --- Paths -------------------------------------------------------------------------------------
    $co = Get-FullPathOnC $Checkout 'the checkout'
    $work = Get-FullPathOnC $WorkDir 'the work folder'
    if (-not (Test-Path -LiteralPath (Join-Path $co 'mach') -PathType Leaf)) { throw "'$co' has no mach" }
    $templateIni = Join-Path $co 'browser\installer\windows\msix\distribution\distribution.ini'
    if (Test-Path -LiteralPath $templateIni) {
        throw ("REFUSED: '$templateIni' exists: patch 0004 is not applied, and mach would put Mozilla's " +
               "distribution.ini (id=mozilla-MSIX) into the package. Run scripts\apply-patches.ps1 first.")
    }
    $orbisDist = Join-Path $co 'orbis-dist'
    $policyFiles = @('orbis.cfg', 'defaults\pref\autoconfig.js', 'distribution\policies.json')
    foreach ($f in $policyFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $orbisDist $f) -PathType Leaf)) {
            throw "'$orbisDist\$f' not found: run scripts\apply-overlay.ps1 first"
        }
    }
    if (-not (Test-Path -LiteralPath $work)) { New-Item -ItemType Directory -Path $work | Out-Null }
    $stage = Join-Path $work 'stage'
    $check = Join-Path $work 'unpacked'

    if (-not $CheckOnly) {
        if (-not $Zip) {
            $dist = Join-Path (Split-Path -Parent $co) 'obj-orbis\dist'
            $zips = @(Get-ChildItem -LiteralPath $dist -Filter 'orbis-*.en-US.win64.zip' -File |
                Where-Object { $_.Name -notlike '*xpt_artifacts*' })
            if ($zips.Count -ne 1) { throw "expected one orbis-*.en-US.win64.zip in '$dist', found $($zips.Count)" }
            $Zip = $zips[0].FullName
        }
        $Zip = Get-FullPathOnC $Zip 'the zip'

        # --- Stage: zip + orbis-dist -------------------------------------------------------------
        New-OwnFolder $stage
        Write-Host "Expanding $Zip"
        Expand-Archive -LiteralPath $Zip -DestinationPath $stage
        $inst = Join-Path $stage 'orbis'
        if (-not (Test-Path -LiteralPath (Join-Path $inst 'orbis.exe'))) { throw "no orbis\orbis.exe in $Zip" }
        foreach ($f in $policyFiles) {
            $d = Join-Path $inst $f
            if (Test-Path -LiteralPath $d) { throw "the zip already has $f; docs\BUILD.md says it should not" }
            New-Item -ItemType Directory -Path (Split-Path -Parent $d) -Force | Out-Null
            Copy-Item -LiteralPath (Join-Path $orbisDist $f) -Destination $d
        }
        if (Test-Path -LiteralPath (Join-Path $inst 'distribution\distribution.ini')) {
            throw 'the staged distribution folder has a distribution.ini'
        }
    } else {
        $inst = Join-Path $stage 'orbis'
    }

    # --- Version -----------------------------------------------------------------------------------
    $appIni = Get-Content -LiteralPath (Join-Path $inst 'application.ini')
    $appVersion = (($appIni | Where-Object { $_ -match '^Version=' }) -replace '^Version=', '').Trim()
    $version = Get-MsixVersion $appVersion ([int]$cfg.orbisRevision)
    if (-not $Output) {
        $tail = ''
        if ($AllowUnsignedInstall) { $tail = '_unsigned-test' }
        $Output = Join-Path $src ('msix\{0}_{1}_x64{2}.msix' -f $cfg.identityName, $version, $tail)
    }
    # mach --unsigned appends this OID to the publisher (Microsoft's marker for an unsigned package).
    $wantPublisher = $cfg.publisher
    if ($AllowUnsignedInstall) { $wantPublisher += ', OID.2.25.311729368913984317654407730594956997722=1' }
    $out = Get-FullPathOnC $Output 'the output'
    Write-Host "Firefox version $appVersion, Orbis revision $($cfg.orbisRevision) -> MSIX version $version"

    if (-not $CheckOnly) {
        New-Item -ItemType Directory -Path (Split-Path -Parent $out) -Force | Out-Null
        $makeappx = Find-MakeAppx
        # --- mach repackage msix in MozillaBuild's shell ---------------------------------------------
        $q = { param($s) "'" + ($s -replace "'", "'\''") + "'" }
        $fwd = { param($s) $s -replace '\\', '/' }
        $machArgs = @('repackage', 'msix', '--input', (& $fwd $inst), '--arch', $cfg.arch, '--channel', $cfg.channel,
            '--version', $version, '--vendor', $vendor, '--identity-name', $cfg.displayName,
            '--publisher', $cfg.publisher, '--publisher-display-name', $cfg.publisherDisplayName,
            '--makeappx', (& $fwd $makeappx), '--output', (& $fwd $out), '--verbose')
        if ($AllowUnsignedInstall) { $machArgs += '--unsigned' }
        $log = Join-Path $work 'repackage-msix.log'
        $sh = "cd " + (& $q (& $fwd $co)) + " || exit 1`nexport MACH_HIDE_DEV_DRIVE_SUGGESTION=1`n" +
              "./mach " + (($machArgs | ForEach-Object { & $q $_ }) -join ' ') + " > " + (& $q (& $fwd $log)) +
              " 2>&1 < /dev/null`n"
        $shPath = Join-Path $work 'repackage-msix.sh'
        [System.IO.File]::WriteAllText($shPath, $sh)
        foreach ($v in 'CYGWIN', 'INCLUDE', 'LIB', 'GITDIR', 'PYTHON', 'PYTHONPATH', 'MSYSTEM_PREFIX', 'MINGW_PREFIX') {
            Remove-Item "Env:$v" -ErrorAction SilentlyContinue
        }
        $env:MOZILLABUILD = 'C:\mozilla-build\'
        $env:MSYSTEM = 'MSYS'
        $env:MSYS2_PATH_TYPE = 'inherit'
        $env:CHERE_INVOKING = '1'
        $env:MOZCONFIG = Join-Path $co 'mozconfig'
        Write-Host "Running mach repackage msix (log: $log)"
        Push-Location $work
        try {
            & 'C:\mozilla-build\msys2\usr\bin\bash.exe' -l (& $fwd $shPath)
            $code = $LASTEXITCODE
        } finally {
            Pop-Location
        }
        if ($code -ne 0) { throw "mach repackage msix failed with exit code $code; see $log" }
    }
    if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw "no MSIX at '$out'" }
    $size = (Get-Item -LiteralPath $out).Length
    Write-Host ("MSIX: {0} ({1:N0} bytes, {2:N1} MB)" -f $out, $size, ($size / 1MB))

    # --- Unpack and check ----------------------------------------------------------------------------
    New-OwnFolder $check
    $makeappx = Find-MakeAppx
    $unpackLog = Join-Path $work 'makeappx-unpack.log'
    & $makeappx unpack /p $out /d (Join-Path $check 'pkg') /o > $unpackLog 2>&1
    if ($LASTEXITCODE -ne 0) { throw "makeappx unpack failed; see $unpackLog" }
    $pkg = Join-Path $check 'pkg'
    $manifestPath = Join-Path $pkg 'AppxManifest.xml'
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $work 'AppxManifest.xml') -Force
    [xml]$mf = Get-Content -LiteralPath $manifestPath -Raw
    $ns = New-Object System.Xml.XmlNamespaceManager($mf.NameTable)
    $ns.AddNamespace('m', 'http://schemas.microsoft.com/appx/manifest/foundation/windows10')
    $ns.AddNamespace('uap', 'http://schemas.microsoft.com/appx/manifest/uap/windows10')
    $id = $mf.SelectSingleNode('/m:Package/m:Identity', $ns)
    $props = $mf.SelectSingleNode('/m:Package/m:Properties', $ns)
    $app = $mf.SelectSingleNode('/m:Package/m:Applications/m:Application', $ns)
    $ve = $mf.SelectSingleNode('/m:Package/m:Applications/m:Application/uap:VisualElements', $ns)
    $caps = @($mf.SelectNodes('/m:Package/m:Capabilities/*', $ns) | ForEach-Object { $_.GetAttribute('Name') })
    $seen = [ordered]@{
        'Identity Name' = $id.GetAttribute('Name'); 'Identity Publisher' = $id.GetAttribute('Publisher')
        'Identity Version' = $id.GetAttribute('Version'); 'ProcessorArchitecture' = $id.GetAttribute('ProcessorArchitecture')
        'DisplayName' = $props.DisplayName; 'PublisherDisplayName' = $props.PublisherDisplayName
        'Description' = $props.Description; 'Application Executable' = $app.GetAttribute('Executable')
        'VisualElements DisplayName' = $ve.GetAttribute('DisplayName'); 'Capabilities' = ($caps -join ', ')
    }
    $seen.GetEnumerator() | ForEach-Object { Write-Host ("  {0}: {1}" -f $_.Key, $_.Value) }
    $want = @{ 'Identity Name' = $cfg.identityName; 'Identity Publisher' = $wantPublisher
               'Identity Version' = $version; 'ProcessorArchitecture' = 'x64'
               'DisplayName' = $cfg.displayName; 'PublisherDisplayName' = $cfg.publisherDisplayName
               'VisualElements DisplayName' = $cfg.displayName
               'Capabilities' = (@($cfg.capabilities) -join ', ') }
    foreach ($k in $want.Keys) {
        if ($seen[$k] -cne $want[$k]) { Add-Failure "manifest $k is '$($seen[$k])', config wants '$($want[$k])'" }
    }
    $instRel = 'VFS\ProgramFiles\' + $cfg.displayName + ' Package Root'
    if ($seen['Application Executable'] -ne ($instRel + '\orbis.exe')) {
        Add-Failure "Application Executable is '$($seen['Application Executable'])'"
    }
    # Comments (the MPL header) are not checked: only what Windows reads.
    $mfText = [regex]::Replace((Get-Content -LiteralPath $manifestPath -Raw), '<!--.*?-->', '', 'Singleline')
    # Allowed: the background-task class ID (MOZ_BACKGROUNDTASK_ACTIVATABLE_CLASS_ID in the build), an internal
    # identifier no user sees (docs\MSIX.md, open items).
    $mfText = $mfText.Replace('Mozilla.MsixComServer.BackgroundTaskHost', '')
    foreach ($bad in 'Mozilla', 'Firefox') {
        if ($mfText -match $bad) { Add-Failure "AppxManifest.xml contains '$bad'" }
    }

    # Logo assets, two-way: every file of the config's assets folder, byte-identical, and nothing else.
    $wantAssets = @(Get-ChildItem -LiteralPath $assetsDir -File)
    foreach ($a in $wantAssets) {
        $p = Join-Path $pkg ('Assets\' + $a.Name)
        if (-not (Test-Path -LiteralPath $p)) { Add-Failure "Assets\$($a.Name) missing" }
        elseif ((Get-Sha256 $p) -ne (Get-Sha256 $a.FullName)) { Add-Failure "Assets\$($a.Name) differs from $($cfg.assets)" }
    }
    $wantNames = @($wantAssets | ForEach-Object { $_.Name })
    $pkgAssets = @(Get-ChildItem -LiteralPath (Join-Path $pkg 'Assets') -Recurse -File)
    foreach ($a in $pkgAssets) {
        $rel = $a.FullName.Substring($pkg.Length + 1)
        if ($rel -ne ('Assets\' + $a.Name) -or $wantNames -notcontains $a.Name) {
            Add-Failure "$rel is in the package but not in $($cfg.assets)"
        }
    }
    Write-Host ("  Assets: {0} in the package, {1} in {2}" -f $pkgAssets.Count, $wantAssets.Count, $cfg.assets)

    # Policy files in the install folder, identical to orbis-dist.
    $instDir = Join-Path $pkg $instRel
    foreach ($f in $policyFiles) {
        $p = Join-Path $instDir $f
        if (-not (Test-Path -LiteralPath $p)) { Add-Failure "$instRel\$f missing" }
        elseif ((Get-Sha256 $p) -ne (Get-Sha256 (Join-Path $orbisDist $f))) { Add-Failure "$instRel\$f differs from orbis-dist" }
        else { Write-Host "  OK: $instRel\$f" }
    }
    # No distribution.ini anywhere, and nothing else in distribution\ but policies.json.
    $inis = @(Get-ChildItem -LiteralPath $pkg -Recurse -File -Filter 'distribution.ini')
    foreach ($i in $inis) { Add-Failure "package has $($i.FullName.Substring($pkg.Length + 1))" }
    $distFiles = @(Get-ChildItem -LiteralPath (Join-Path $instDir 'distribution') -Recurse -File |
        ForEach-Object { $_.FullName.Substring($instDir.Length + 1) })
    Write-Host ("  distribution folder: " + ($distFiles -join ', '))
    if (($distFiles -join '|') -ne 'distribution\policies.json') { Add-Failure "distribution folder has: $($distFiles -join ', ')" }
    $hits = @(Get-ChildItem -LiteralPath $pkg -Recurse -File -Include '*.ini', '*.json', '*.cfg', '*.js' |
        Where-Object { $_.Length -lt 1MB } | Select-String -SimpleMatch 'mozilla-MSIX' -List)
    foreach ($h in $hits) { Add-Failure "'mozilla-MSIX' in $($h.Path.Substring($pkg.Length + 1))" }

    # Report only, never a failure: Mozilla or Firefox in file names and in version resources.
    $allFiles = @(Get-ChildItem -LiteralPath $pkg -Recurse -File)
    $nameHits = @($allFiles | ForEach-Object { $_.FullName.Substring($pkg.Length + 1) } |
        Where-Object { $_ -match 'mozilla|firefox' })
    Write-Host ("  REPORT: {0} file name(s) contain Mozilla or Firefox" -f $nameHits.Count)
    foreach ($n in $nameHits) { Write-Host "    $n" }
    $verFields = 'CompanyName', 'ProductName', 'FileDescription', 'LegalCopyright', 'LegalTrademarks',
                 'InternalName', 'OriginalFilename', 'Comments'
    $verHits = New-Object System.Collections.ArrayList
    foreach ($b in @($allFiles | Where-Object { $_.Extension -eq '.exe' -or $_.Extension -eq '.dll' })) {
        $vi = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($b.FullName)
        $found = @($verFields | Where-Object { $vi.$_ -match 'mozilla|firefox' } |
            ForEach-Object { "{0}='{1}'" -f $_, $vi.$_ })
        if ($found.Count -gt 0) {
            [void]$verHits.Add(('{0}: {1}' -f $b.FullName.Substring($pkg.Length + 1), ($found -join '; ')))
        }
    }
    Write-Host ("  REPORT: {0} binaries with Mozilla or Firefox in the version resource" -f $verHits.Count)
    foreach ($v in $verHits) { Write-Host "    $v" }

    Write-Host "  $($allFiles.Count) files in the package; AppxManifest.xml copied to $work"
    if ($failures.Count -gt 0) { throw ("{0} check(s) failed" -f $failures.Count) }
    $hash = Get-Sha256 $out
    $shaFile = $out + '.sha256'
    if ($CheckOnly) {
        # Compare, never rewrite: the .sha256 was written when this package was built.
        if (-not (Test-Path -LiteralPath $shaFile -PathType Leaf)) {
            throw "no '$shaFile' to compare with; rebuild the package (without -CheckOnly)"
        }
        $recorded = ((Get-Content -LiteralPath $shaFile -TotalCount 1) -split '\s+')[0]
        if ($recorded -ne $hash) {
            throw "SHA-256 of '$out' is $hash, but '$shaFile' says $recorded (stale or wrong file)"
        }
        Write-Host "SHA-256: $hash (matches $shaFile)"
    } else {
        [System.IO.File]::WriteAllText($shaFile, ("{0} *{1}`r`n" -f $hash, (Split-Path -Leaf $out)))
        Write-Host "SHA-256: $hash (written to $shaFile)"
    }
    if ($placeholders.Count -gt 0) { Write-Warning 'Built with TODO-STORE placeholders: not for upload.' }
    Write-Host "OK: $out"
    exit 0
} catch {
    [Console]::Error.WriteLine("FAILED: " + $_.Exception.Message)
    exit 1
}
