using System.Reflection;

namespace Sinbar.Support.Assistant;

internal static class BuildTrust
{
    internal static readonly string ManifestPublicKeyX963Base64Url =
        ReadMetadata("SinbarManifestPublicKeyX963Base64Url");

    internal static readonly string RustDeskPublisherSpkiSha256 =
        ReadMetadata("SinbarRustDeskPublisherSpkiSha256");

    private static string ReadMetadata(string key) =>
        Assembly.GetExecutingAssembly()
            .GetCustomAttributes<AssemblyMetadataAttribute>()
            .SingleOrDefault(attribute =>
                string.Equals(attribute.Key, key, StringComparison.Ordinal))
            ?.Value
        ?? "UNCONFIGURED";
}
