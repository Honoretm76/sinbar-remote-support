using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace Sinbar.Support.Assistant;

internal sealed class SignedManifestVerifier
{
    private static readonly Regex StrictUtcTimestamp = new(
        @"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking,
        TimeSpan.FromMilliseconds(100));

    private static readonly Regex LowercaseSha256 = new(
        @"\A[0-9a-f]{64}\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking,
        TimeSpan.FromMilliseconds(100));

    private static readonly JsonSerializerOptions StrictJson = new()
    {
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        NumberHandling = JsonNumberHandling.Strict,
    };

    private readonly byte[] publicKey;
    private readonly TimeProvider timeProvider;

    internal SignedManifestVerifier(string publicKeyX963Base64Url, TimeProvider? timeProvider = null)
    {
        publicKey = Base64Url.Decode(publicKeyX963Base64Url, 65, "manifest public key");
        if (publicKey[0] != 0x04)
        {
            throw new SecurityException("The manifest public key is not an uncompressed P-256 key.");
        }

        this.timeProvider = timeProvider ?? TimeProvider.System;
    }

    internal SupportManifest Verify(string envelopeJson, string expectedArchitecture)
    {
        if (string.IsNullOrWhiteSpace(envelopeJson) ||
            System.Text.Encoding.UTF8.GetByteCount(envelopeJson) > SecurityPolicy.MaximumEnvelopeBytes)
        {
            throw new SecurityException("The signed support manifest envelope is invalid.");
        }

        byte[] envelopeBytes = System.Text.Encoding.UTF8.GetBytes(envelopeJson);
        RejectDuplicateProperties(envelopeBytes);

        SignedManifestEnvelope envelope;
        try
        {
            envelope = JsonSerializer.Deserialize<SignedManifestEnvelope>(envelopeBytes, StrictJson)
                ?? throw new JsonException("Envelope is null.");
        }
        catch (JsonException exception)
        {
            throw new SecurityException("The signed support manifest envelope is invalid.", exception);
        }

        if (!string.Equals(envelope.KeyId, SecurityPolicy.ManifestKeyId, StringComparison.Ordinal))
        {
            throw new SecurityException("The support manifest signing key is not trusted.");
        }

        byte[] payload = Base64Url.DecodeBounded(envelope.Payload, 8 * 1024, "manifest payload");
        byte[] signature = Base64Url.Decode(envelope.Signature, 64, "manifest signature");

        using ECDsa verifier = CreateVerifier(publicKey);
        if (!verifier.VerifyData(
                payload,
                signature,
                HashAlgorithmName.SHA256,
                DSASignatureFormat.IeeeP1363FixedFieldConcatenation))
        {
            throw new SecurityException("The support manifest signature is invalid.");
        }

        RejectDuplicateProperties(payload);

        SupportManifest manifest;
        try
        {
            manifest = JsonSerializer.Deserialize<SupportManifest>(payload, StrictJson)
                ?? throw new JsonException("Manifest is null.");
        }
        catch (JsonException exception)
        {
            throw new SecurityException("The signed support manifest payload is invalid.", exception);
        }

        ValidateManifest(manifest, expectedArchitecture);
        return manifest;
    }

    internal void EnsureCurrent(SupportManifest manifest, string expectedArchitecture) =>
        ValidateManifest(manifest, expectedArchitecture);

    private void ValidateManifest(SupportManifest manifest, string expectedArchitecture)
    {
        if (manifest.SchemaVersion != 1 ||
            !Guid.TryParseExact(manifest.SessionId, "D", out Guid sessionId) ||
            sessionId == Guid.Empty ||
            !string.Equals(manifest.Action, SecurityPolicy.RequiredAction, StringComparison.Ordinal) ||
            !manifest.Attended ||
            !string.Equals(manifest.Platform, SecurityPolicy.RequiredPlatform, StringComparison.Ordinal) ||
            !string.Equals(manifest.Architecture, expectedArchitecture, StringComparison.Ordinal))
        {
            throw new SecurityException("The support manifest requested an unauthorized action or target.");
        }

        DateTimeOffset issuedAt = ParseStrictUtc(manifest.IssuedAt, "issuedAt");
        DateTimeOffset expiresAt = ParseStrictUtc(manifest.ExpiresAt, "expiresAt");
        DateTimeOffset now = timeProvider.GetUtcNow();

        if (issuedAt > now + SecurityPolicy.MaximumClockSkew ||
            issuedAt < now - SecurityPolicy.MaximumManifestLifetime - SecurityPolicy.MaximumClockSkew ||
            expiresAt <= now ||
            expiresAt <= issuedAt ||
            expiresAt - issuedAt > SecurityPolicy.MaximumManifestLifetime)
        {
            throw new SecurityException("The support manifest has expired or has an invalid lifetime.");
        }

        RustDeskArtifact artifact = manifest.Artifact
            ?? throw new SecurityException("The RustDesk artifact is missing.");
        ArtifactPin pin = SecurityPolicy.ArtifactFor(expectedArchitecture);

        if (!string.Equals(artifact.Kind, SecurityPolicy.RequiredArtifactKind, StringComparison.Ordinal) ||
            !string.Equals(artifact.Version, SecurityPolicy.RequiredRustDeskVersion, StringComparison.Ordinal) ||
            !string.Equals(artifact.PublisherSubjectContains, SecurityPolicy.RequiredPublisherSubjectFragment, StringComparison.Ordinal) ||
            !LowercaseSha256.IsMatch(artifact.Sha256 ?? string.Empty) ||
            !string.Equals(artifact.Sha256, pin.Sha256, StringComparison.Ordinal) ||
            !string.Equals(artifact.Url, pin.Url, StringComparison.Ordinal))
        {
            throw new SecurityException("The RustDesk artifact does not match the locally pinned release.");
        }

        if (!Uri.TryCreate(artifact.Url, UriKind.Absolute, out Uri? artifactUri) ||
            artifactUri.Scheme != Uri.UriSchemeHttps ||
            !string.Equals(artifactUri.Host, "support.sinbarconsultants.com", StringComparison.Ordinal) ||
            !artifactUri.IsDefaultPort ||
            !string.IsNullOrEmpty(artifactUri.UserInfo) ||
            !string.IsNullOrEmpty(artifactUri.Query) ||
            !string.IsNullOrEmpty(artifactUri.Fragment))
        {
            throw new SecurityException("The RustDesk artifact URL is not trusted.");
        }
    }

    private static DateTimeOffset ParseStrictUtc(string value, string fieldName)
    {
        if (!StrictUtcTimestamp.IsMatch(value ?? string.Empty) ||
            !DateTimeOffset.TryParseExact(
                value,
                "yyyy-MM-dd'T'HH:mm:ss'Z'",
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal,
                out DateTimeOffset parsed))
        {
            throw new SecurityException($"The manifest {fieldName} timestamp is invalid.");
        }

        return parsed;
    }

    private static ECDsa CreateVerifier(byte[] key)
    {
        ECParameters parameters = new()
        {
            Curve = ECCurve.NamedCurves.nistP256,
            Q = new ECPoint
            {
                X = key[1..33],
                Y = key[33..65],
            },
        };

        return ECDsa.Create(parameters);
    }

    private static void RejectDuplicateProperties(ReadOnlySpan<byte> json)
    {
        try
        {
            Utf8JsonReader reader = new(json, new JsonReaderOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 16,
            });

            Stack<HashSet<string>> objects = new();
            while (reader.Read())
            {
                if (reader.TokenType == JsonTokenType.StartObject)
                {
                    objects.Push(new HashSet<string>(StringComparer.Ordinal));
                }
                else if (reader.TokenType == JsonTokenType.EndObject)
                {
                    objects.Pop();
                }
                else if (reader.TokenType == JsonTokenType.PropertyName)
                {
                    if (objects.Count == 0 || !objects.Peek().Add(reader.GetString() ?? string.Empty))
                    {
                        throw new SecurityException("Duplicate JSON properties are not permitted.");
                    }
                }
            }
        }
        catch (JsonException exception)
        {
            throw new SecurityException("The signed JSON is invalid.", exception);
        }
    }
}
