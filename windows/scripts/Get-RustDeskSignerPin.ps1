#requires -Version 7.4
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string] $MsiPath,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Fa-f0-9]{64}$')]
    [string] $ExpectedSha256
)

$ErrorActionPreference = 'Stop'

if (-not $IsWindows) {
    throw 'Authenticode signer measurement must run on Windows.'
}

$resolved = (Resolve-Path -LiteralPath $MsiPath).Path
$observedFileHash = (Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash
if ($observedFileHash -ne $ExpectedSha256.ToUpperInvariant()) {
    throw 'The MSI SHA-256 does not match the independently approved artifact hash.'
}

$signature = Get-AuthenticodeSignature -LiteralPath $resolved
if ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate) {
    throw "The MSI Authenticode signature is not valid: $($signature.StatusMessage)"
}

$spki = $signature.SignerCertificate.PublicKey.ExportSubjectPublicKeyInfo()
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $spkiHash = [Convert]::ToHexString($sha256.ComputeHash($spki)).ToLowerInvariant()
}
finally {
    $sha256.Dispose()
}

[pscustomobject]@{
    Path = $resolved
    FileSha256 = $observedFileHash.ToLowerInvariant()
    SignerSubject = $signature.SignerCertificate.Subject
    SignerCertificateThumbprint = $signature.SignerCertificate.Thumbprint
    SignerSpkiSha256 = $spkiHash
}
