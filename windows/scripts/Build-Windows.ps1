#requires -Version 7.4
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_-]{87}$')]
    [string] $ManifestPublicKeyX963Base64Url,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Fa-f0-9]{64}$')]
    [string] $RustDeskPublisherSpkiSha256,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Fa-f0-9]{40}$')]
    [string] $CodeSigningCertificateThumbprint,

    [string] $TimestampUrl = 'http://timestamp.digicert.com',

    [string] $DotNet = 'dotnet',

    [string] $SignTool = 'signtool.exe',

    [string] $InnoCompiler = 'iscc.exe'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if (-not $IsWindows) {
    throw 'The signed Windows release must be built on Windows.'
}

$root = Split-Path -Parent $PSScriptRoot
$project = Join-Path $root 'src\SinbarSupportAssistant\SinbarSupportAssistant.csproj'
$contractTests = Join-Path $root 'tests\ContractTests\ContractTests.csproj'
$installerScript = Join-Path $root 'installer\SinbarSupportAssistant.iss'
$artifactRoot = Join-Path $root 'artifacts'
$thumbprint = $CodeSigningCertificateThumbprint.ToUpperInvariant()
$rustDeskSpkiPin = $RustDeskPublisherSpkiSha256.ToLowerInvariant()

function Assert-Command([string] $Command) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Command"
    }
}

function Assert-PublicKey([string] $Encoded) {
    $padded = $Encoded.Replace('-', '+').Replace('_', '/') + '='
    $decoded = [Convert]::FromBase64String($padded)
    if ($decoded.Length -ne 65 -or $decoded[0] -ne 4) {
        throw 'Manifest public key must be a 65-byte uncompressed P-256 X9.63 point.'
    }

    # Import the point through the platform crypto provider so a correctly
    # sized but off-curve point cannot be embedded in a production build.
    $point = [System.Security.Cryptography.ECPoint]::new()
    $point.X = [byte[]] $decoded[1..32]
    $point.Y = [byte[]] $decoded[33..64]
    $parameters = [System.Security.Cryptography.ECParameters]::new()
    $parameters.Curve = [System.Security.Cryptography.ECCurve]::NamedCurves.nistP256
    $parameters.Q = $point
    $ecdsa = [System.Security.Cryptography.ECDsa]::Create()
    try {
        $ecdsa.ImportParameters($parameters)
    }
    catch {
        throw "Manifest public key is not a valid P-256 curve point: $($_.Exception.Message)"
    }
    finally {
        $ecdsa.Dispose()
    }
}

function Sign-And-Verify([string] $Path) {
    & $SignTool sign `
        /sha1 $thumbprint `
        /fd SHA256 `
        /tr $TimestampUrl `
        /td SHA256 `
        /d 'Sinbar Support Assistant' `
        $Path

    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed: $Path"
    }

    & $SignTool verify /pa /all /v $Path
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode verification failed: $Path"
    }

    $signature = Get-AuthenticodeSignature -FilePath $Path
    if ($signature.Status -ne 'Valid' -or
        $signature.SignerCertificate.Thumbprint -ne $thumbprint) {
        throw "The wrong certificate signed: $Path"
    }
}

Assert-Command $DotNet
Assert-Command $SignTool
Assert-Command $InnoCompiler
Assert-PublicKey $ManifestPublicKeyX963Base64Url

$innoPath = (Get-Command $InnoCompiler).Source
$innoVersion = (Get-Item $innoPath).VersionInfo.FileVersionRaw
if ($innoVersion -lt [Version] '6.7.1') {
    throw "Inno Setup 6.7.1 or later is required; found $innoVersion."
}

$certificate = Get-ChildItem -Path Cert:\CurrentUser\My, Cert:\LocalMachine\My |
    Where-Object Thumbprint -eq $thumbprint |
    Where-Object HasPrivateKey |
    Select-Object -First 1

if (-not $certificate) {
    throw "The code-signing certificate/private key was not found: $thumbprint"
}

Remove-Item -Recurse -Force $artifactRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null

& $DotNet run --project $contractTests --configuration Release `
    -p:ManifestPublicKeyX963Base64Url=$ManifestPublicKeyX963Base64Url `
    -p:RustDeskPublisherSpkiSha256=$rustDeskSpkiPin
if ($LASTEXITCODE -ne 0) {
    throw 'Contract tests failed.'
}

foreach ($runtime in @('win-x64', 'win-arm64')) {
    $output = Join-Path $artifactRoot $runtime
    & $DotNet publish $project `
        --configuration Release `
        --runtime $runtime `
        --self-contained true `
        -p:PublishSingleFile=true `
        -p:ManifestPublicKeyX963Base64Url=$ManifestPublicKeyX963Base64Url `
        -p:RustDeskPublisherSpkiSha256=$rustDeskSpkiPin `
        --output $output

    if ($LASTEXITCODE -ne 0) {
        throw "Publish failed for $runtime."
    }

    Sign-And-Verify (Join-Path $output 'SinbarSupportAssistant.exe')
}

$quotedSignTool = '$q' + (Get-Command $SignTool).Source + '$q'
$innoSignCommand = (
    "$quotedSignTool sign /sha1 $thumbprint /fd SHA256 " +
    "/tr $TimestampUrl /td SHA256 /d `$qSinbar Support Assistant`$q `$f"
)

& $InnoCompiler `
    '--no-ide-signtools' `
    "--signtool=SinbarCodeSign=$innoSignCommand" `
    "/DArtifactRoot=$artifactRoot" `
    $installerScript

if ($LASTEXITCODE -ne 0) {
    throw 'Inno Setup compilation failed.'
}

$setup = Join-Path $artifactRoot 'installer\Sinbar-Support-Assistant-Setup.exe'
& $SignTool verify /pa /all /v $setup
if ($LASTEXITCODE -ne 0) {
    throw 'Final installer Authenticode verification failed.'
}

$setupSignature = Get-AuthenticodeSignature -FilePath $setup
if ($setupSignature.Status -ne 'Valid' -or
    $setupSignature.SignerCertificate.Thumbprint -ne $thumbprint) {
    throw 'The final installer was not signed by the required Sinbar certificate.'
}

$hash = (Get-FileHash -Algorithm SHA256 -Path $setup).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    schemaVersion = 1
    version = '2.0.0'
    platform = 'windows'
    path = '/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe'
    bytes = (Get-Item $setup).Length
    sha256 = $hash
    authenticodePublisher = $certificate.Subject
    authenticodeCertificateThumbprint = $thumbprint
}

$manifestPath = Join-Path $artifactRoot 'installer\Sinbar-Support-Assistant-Setup.manifest.json'
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8NoBOM $manifestPath

Write-Host "PASS: signed Windows release created"
Write-Host "installer=$setup"
Write-Host "sha256=$hash"
Write-Host "manifest=$manifestPath"
