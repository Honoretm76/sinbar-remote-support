#requires -Version 7.4
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $RepositoryRoot,

    [Parameter(Mandatory = $true)]
    [string] $OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$requiredEnvironment = @(
    'WINDOWS_SIGNING_PFX_BASE64',
    'WINDOWS_SIGNING_PFX_PASSWORD',
    'WINDOWS_CERT_THUMBPRINT',
    'WINDOWS_TIMESTAMP_URL',
    'MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL',
    'RUSTDESK_WINDOWS_PUBLISHER_SPKI_SHA256'
)

foreach ($name in $requiredEnvironment) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required release configuration is absent: $name"
    }
}

$thumbprint = $env:WINDOWS_CERT_THUMBPRINT.Replace(' ', '').ToUpperInvariant()
if ($thumbprint -notmatch '^[A-F0-9]{40}$') {
    throw 'WINDOWS_CERT_THUMBPRINT must be a 40-character SHA-1 certificate thumbprint.'
}

$rustDeskSignerSpki = $env:RUSTDESK_WINDOWS_PUBLISHER_SPKI_SHA256.ToLowerInvariant()
if ($rustDeskSignerSpki -notmatch '^[a-f0-9]{64}$') {
    throw 'RUSTDESK_WINDOWS_PUBLISHER_SPKI_SHA256 must be a 64-character SHA-256 pin.'
}

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$buildScript = Join-Path $repository 'windows\scripts\Build-Windows.ps1'
if (-not (Test-Path -LiteralPath $buildScript -PathType Leaf)) {
    throw "Canonical Windows build script is missing: $buildScript"
}

function Find-RequiredTool {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Command,

        [string[]] $Fallbacks = @()
    )

    $resolved = Get-Command $Command -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($resolved) {
        return $resolved.Source
    }

    foreach ($fallback in $Fallbacks) {
        $matches = Get-ChildItem -Path $fallback -File -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending
        if ($matches) {
            return $matches[0].FullName
        }
    }

    throw "Required release tool was not found: $Command"
}

$dotnet = Find-RequiredTool -Command 'dotnet.exe'
$signTool = Find-RequiredTool -Command 'signtool.exe' -Fallbacks @(
    "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe"
)
$innoCompiler = Find-RequiredTool -Command 'iscc.exe' -Fallbacks @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)

$tempRoot = if ($env:RUNNER_TEMP) {
    $env:RUNNER_TEMP
} else {
    [IO.Path]::GetTempPath()
}
$pfxPath = Join-Path $tempRoot ("sinbar-signing-{0}.pfx" -f [Guid]::NewGuid())
$importedCertificate = $null
$pfxBytes = $null

try {
    try {
        $pfxBytes = [Convert]::FromBase64String($env:WINDOWS_SIGNING_PFX_BASE64)
    } catch {
        throw 'WINDOWS_SIGNING_PFX_BASE64 is not valid base64.'
    }
    if ($pfxBytes.Length -lt 1) {
        throw 'The Authenticode PFX is empty.'
    }
    [IO.File]::WriteAllBytes($pfxPath, $pfxBytes)
    [Array]::Clear($pfxBytes, 0, $pfxBytes.Length)
    $pfxBytes = $null

    $securePassword = ConvertTo-SecureString `
        -String $env:WINDOWS_SIGNING_PFX_PASSWORD `
        -AsPlainText `
        -Force
    $imported = @(
        Import-PfxCertificate `
            -FilePath $pfxPath `
            -CertStoreLocation 'Cert:\CurrentUser\My' `
            -Password $securePassword
    )
    $importedCertificate = $imported |
        Where-Object {
            $_.Thumbprint -eq $thumbprint -and $_.HasPrivateKey
        } |
        Select-Object -First 1
    if (-not $importedCertificate) {
        throw 'Imported PFX did not contain the configured signing certificate/private key.'
    }
    $securePassword = $null
    Remove-Item -LiteralPath $pfxPath -Force
    $env:WINDOWS_SIGNING_PFX_BASE64 = $null
    $env:WINDOWS_SIGNING_PFX_PASSWORD = $null
    if ($importedCertificate.NotAfter -le [DateTime]::UtcNow.AddDays(7)) {
        throw 'Authenticode certificate expires within seven days; release stopped.'
    }

    & $buildScript `
        -ManifestPublicKeyX963Base64Url $env:MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL `
        -RustDeskPublisherSpkiSha256 $rustDeskSignerSpki `
        -CodeSigningCertificateThumbprint $thumbprint `
        -TimestampUrl $env:WINDOWS_TIMESTAMP_URL `
        -DotNet $dotnet `
        -SignTool $signTool `
        -InnoCompiler $innoCompiler
    if ($LASTEXITCODE -ne 0) {
        throw 'Canonical Windows build failed.'
    }

    $sourceInstaller = Join-Path $repository `
        'windows\artifacts\installer\Sinbar-Support-Assistant-Setup.exe'
    if (-not (Test-Path -LiteralPath $sourceInstaller -PathType Leaf)) {
        throw 'Canonical Windows build did not produce the expected installer.'
    }

    & $signTool verify /pa /all /tw /v $sourceInstaller
    if ($LASTEXITCODE -ne 0) {
        throw 'Final Authenticode/timestamp verification failed.'
    }
    $signature = Get-AuthenticodeSignature -FilePath $sourceInstaller
    if ($signature.Status -ne 'Valid' -or
        $signature.SignerCertificate.Thumbprint -ne $thumbprint) {
        throw 'Final Windows installer is unsigned or signed by the wrong certificate.'
    }

    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $destination = Join-Path $OutputDirectory 'Sinbar-Support-Assistant-Setup.exe'
    Copy-Item -LiteralPath $sourceInstaller -Destination $destination -Force
    Write-Host 'PASS: Authenticode-signed Windows release is ready'
    Write-Host "artifact=$destination"
} finally {
    if ($importedCertificate) {
        Remove-Item -LiteralPath $importedCertificate.PSPath -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $pfxPath -Force -ErrorAction SilentlyContinue
    if ($pfxBytes) {
        [Array]::Clear($pfxBytes, 0, $pfxBytes.Length)
    }
    $env:WINDOWS_SIGNING_PFX_BASE64 = $null
    $env:WINDOWS_SIGNING_PFX_PASSWORD = $null
}
