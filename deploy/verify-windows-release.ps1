[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$SignerCertificateSha256,
    [Parameter(Mandatory = $true)][string]$SignerSubject,
    [Parameter(Mandatory = $true)][string]$Output
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$installerPath = (Resolve-Path -LiteralPath $Installer).Path
if ([IO.Path]::GetFileName($installerPath) -cne 'Sinbar-Support-Assistant-Setup.exe') {
    throw 'Unexpected Windows installer filename.'
}

$signature = Get-AuthenticodeSignature -LiteralPath $installerPath
if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
    throw "Authenticode status is $($signature.Status), not Valid."
}
if ($null -eq $signature.SignerCertificate) {
    throw 'No Authenticode signer certificate was returned.'
}

$actualFingerprint = $signature.SignerCertificate.GetCertHashString('SHA256').ToLowerInvariant()
if ($actualFingerprint -cne $SignerCertificateSha256.ToLowerInvariant()) {
    throw 'Authenticode signer SHA-256 fingerprint does not match the production pin.'
}
if ($signature.SignerCertificate.Subject.IndexOf($SignerSubject, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
    throw 'Authenticode signer subject does not match the production pin.'
}

$signTool = Get-Command signtool.exe -ErrorAction Stop
& $signTool.Source verify /pa /all /tw /v $installerPath
if ($LASTEXITCODE -ne 0) {
    throw 'SignTool verification or RFC 3161 timestamp verification failed.'
}

$digest = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
$receipt = [ordered]@{
    schemaVersion = 1
    platform = 'windows'
    artifact = 'Sinbar-Support-Assistant-Setup.exe'
    sha256 = $digest
    verifiedAt = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    authenticodeStatus = 'Valid'
    signerCertificateSha256 = $actualFingerprint
    signerSubject = $signature.SignerCertificate.Subject
    timestampVerified = $true
}

$json = $receipt | ConvertTo-Json -Depth 3
[IO.File]::WriteAllText([IO.Path]::GetFullPath($Output), $json + "`n", [Text.UTF8Encoding]::new($false))
Write-Host "PASS: Windows Authenticode signature, pinned signer, and timestamp verified."
