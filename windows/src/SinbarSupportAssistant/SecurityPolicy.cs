namespace Sinbar.Support.Assistant;

internal static class SecurityPolicy
{
    internal const string AssistantVersion = "2.0.0";
    internal const string ProtocolScheme = "sinbarsupport";
    internal const string ProtocolHost = "start";
    internal const string ManifestKeyId = "sinbar-support-manifest-p256-v1";
    internal const string ApiOrigin = "https://support.sinbarconsultants.com";
    internal const string SessionConsumePath = "/api/v1/support/sessions/consume";
    internal const string RequiredAction = "ensure-and-launch-rustdesk";
    internal const string RequiredPlatform = "windows";
    internal const string RequiredArtifactKind = "msi";
    internal const string RequiredRustDeskVersion = "1.4.9";
    internal const string RequiredPublisherSubjectFragment = "PURSLANE";
    internal const int TokenLength = 43;
    // The verified envelope is handed to the elevated process as base64url,
    // never as an arbitrary filesystem path. Keep it comfortably below the
    // Windows command-line limit after encoding.
    internal const int MaximumEnvelopeBytes = 16 * 1024;
    internal const int MaximumArtifactBytes = 100 * 1024 * 1024;
    internal static readonly TimeSpan MaximumManifestLifetime = TimeSpan.FromMinutes(5);
    internal static readonly TimeSpan MaximumClockSkew = TimeSpan.FromMinutes(1);

    internal static readonly ArtifactPin X64Artifact = new(
        Architecture: "x86_64",
        Url: "https://support.sinbarconsultants.com/download/vendor/rustdesk/1.4.9/windows/rustdesk-1.4.9-x86_64.msi",
        Sha256: "c87d2f4cef2a5acd6003b6507dcfbf5d5168a256db082cd90b54d35193224aaa");

    internal static readonly ArtifactPin Arm64Artifact = new(
        Architecture: "arm64",
        Url: "https://support.sinbarconsultants.com/download/vendor/rustdesk/1.4.9/windows/rustdesk-1.4.9-aarch64.msi",
        Sha256: "30bc8925e62c7ade52371758c2b944036ed2386f6c554e9e59f3bcfef06c7cd9");

    internal static ArtifactPin ArtifactFor(string architecture) => architecture switch
    {
        "x86_64" => X64Artifact,
        "arm64" => Arm64Artifact,
        _ => throw new SecurityException("This Windows architecture is not supported."),
    };
}

internal sealed record ArtifactPin(string Architecture, string Url, string Sha256);
