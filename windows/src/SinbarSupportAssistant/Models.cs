using System.Text.Json.Serialization;

namespace Sinbar.Support.Assistant;

internal sealed record SessionConsumeRequest(
    [property: JsonPropertyName("token")] string Token,
    [property: JsonPropertyName("platform")] string Platform,
    [property: JsonPropertyName("architecture")] string Architecture,
    [property: JsonPropertyName("assistantVersion")] string AssistantVersion);

internal sealed record SignedManifestEnvelope(
    [property: JsonPropertyName("keyId")] string KeyId,
    [property: JsonPropertyName("payload")] string Payload,
    [property: JsonPropertyName("signature")] string Signature);

internal sealed record SupportManifest(
    [property: JsonPropertyName("schemaVersion")] int SchemaVersion,
    [property: JsonPropertyName("sessionId")] string SessionId,
    [property: JsonPropertyName("action")] string Action,
    [property: JsonPropertyName("attended")] bool Attended,
    [property: JsonPropertyName("platform")] string Platform,
    [property: JsonPropertyName("architecture")] string Architecture,
    [property: JsonPropertyName("issuedAt")] string IssuedAt,
    [property: JsonPropertyName("expiresAt")] string ExpiresAt,
    [property: JsonPropertyName("artifact")] RustDeskArtifact Artifact);

internal sealed record RustDeskArtifact(
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("url")] string Url,
    [property: JsonPropertyName("sha256")] string Sha256,
    [property: JsonPropertyName("version")] string Version,
    [property: JsonPropertyName("publisherSubjectContains")] string PublisherSubjectContains);
