using System.Security;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Sinbar.Support.Assistant;

internal static class ContractTestProgram
{
    private static readonly DateTimeOffset Now =
        new(2026, 8, 31, 12, 0, 0, TimeSpan.Zero);

    private static int Main()
    {
        try
        {
            TestProtocolParser();
            TestSignedManifestContract();
            Console.WriteLine("PASS: Windows protocol and signed-manifest contract tests");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"FAIL: {exception}");
            return 1;
        }
    }

    private static void TestProtocolParser()
    {
        string token = new('A', SecurityPolicy.TokenLength);
        ProtocolRequest parsed = ProtocolRequest.Parse($"sinbarsupport://start?token={token}");
        Assert(parsed.Token == token, "Valid token was not parsed.");

        foreach (string invalid in new[]
        {
            $"sinbarsupport://start/?token={token}",
            $"SINBARSUPPORT://start?token={token}",
            $"sinbarsupport://start?token={token}&origin=https://support.sinbarconsultants.com",
            $"sinbarsupport://start?token={token}&token={token}",
            $"sinbarsupport://start?token={new string('A', 42)}",
            $"sinbarsupport://start?token={new string('A', 44)}",
            "https://support.sinbarconsultants.com/",
            $"sinbarsupport://run?token={token}",
            $"sinbarsupport://start?token={token}#fragment",
            $"sinbarsupport://start?token={new string('A', 42)}%41",
        })
        {
            ExpectThrows<SecurityException>(() => ProtocolRequest.Parse(invalid));
        }

        // Alternate encodings with non-zero unused bits must not be accepted
        // as aliases for the same bytes.
        ExpectThrows<SecurityException>(() => Base64Url.Decode("AB", 1, "test value"));
    }

    private static void TestSignedManifestContract()
    {
        using ECDsa signer = ECDsa.Create(ECCurve.NamedCurves.nistP256);
        string publicKey = EncodePublicKey(signer.ExportParameters(false));
        SignedManifestVerifier verifier = new(publicKey, new FixedTimeProvider(Now));

        string validPayload = BuildPayload();
        string validEnvelope = SignEnvelope(signer, validPayload);
        SupportManifest manifest = verifier.Verify(validEnvelope, "x86_64");
        Assert(manifest.Action == SecurityPolicy.RequiredAction, "Valid action was not accepted.");

        ExpectThrows<SecurityException>(() =>
            verifier.Verify(SignEnvelope(signer, BuildPayload(action: "run-command")), "x86_64"));
        ExpectThrows<SecurityException>(() =>
            verifier.Verify(SignEnvelope(signer, BuildPayload(
                url: "https://evil.example/rustdesk.msi")), "x86_64"));
        ExpectThrows<SecurityException>(() =>
            verifier.Verify(SignEnvelope(signer, BuildPayload(
                sha256: new string('0', 64))), "x86_64"));
        ExpectThrows<SecurityException>(() =>
            verifier.Verify(SignEnvelope(signer, BuildPayload(
                publisher: "OTHER")), "x86_64"));
        ExpectThrows<SecurityException>(() =>
            verifier.Verify(SignEnvelope(signer, BuildPayload(
                expiresAt: "2026-08-31T12:10:00Z")), "x86_64"));
        ExpectThrows<SecurityException>(() =>
            verifier.Verify(SignEnvelope(signer, BuildPayload(
                architecture: "arm64")), "x86_64"));

        using JsonDocument envelopeDocument = JsonDocument.Parse(validEnvelope);
        string signature = envelopeDocument.RootElement.GetProperty("signature").GetString()!;
        string changedSignature = (signature[0] == 'A' ? "B" : "A") + signature[1..];
        string tamperedEnvelope = validEnvelope.Replace(signature, changedSignature, StringComparison.Ordinal);
        Assert(tamperedEnvelope.Length == validEnvelope.Length, "Signature tamper must preserve length.");
        ExpectThrows<SecurityException>(() => verifier.Verify(tamperedEnvelope, "x86_64"));

        string duplicatePayload = validPayload.Replace(
            "\"schemaVersion\":1,",
            "\"schemaVersion\":1,\"schemaVersion\":1,",
            StringComparison.Ordinal);
        ExpectThrows<SecurityException>(() =>
            verifier.Verify(SignEnvelope(signer, duplicatePayload), "x86_64"));

        string unknownPayload = validPayload.Replace(
            "\"schemaVersion\":1,",
            "\"schemaVersion\":1,\"unexpected\":true,",
            StringComparison.Ordinal);
        ExpectThrows<SecurityException>(() =>
            verifier.Verify(SignEnvelope(signer, unknownPayload), "x86_64"));

        string unknownEnvelope = validEnvelope.Replace(
            "{\"keyId\":",
            "{\"unexpected\":true,\"keyId\":",
            StringComparison.Ordinal);
        ExpectThrows<SecurityException>(() => verifier.Verify(unknownEnvelope, "x86_64"));

        SignedManifestVerifier lateVerifier = new(
            publicKey,
            new FixedTimeProvider(Now.AddMinutes(5)));
        ExpectThrows<SecurityException>(() => lateVerifier.EnsureCurrent(manifest, "x86_64"));
    }

    private static string BuildPayload(
        string action = "ensure-and-launch-rustdesk",
        string architecture = "x86_64",
        string? url = null,
        string? sha256 = null,
        string publisher = "PURSLANE",
        string expiresAt = "2026-08-31T12:04:00Z")
    {
        object payload = new
        {
            schemaVersion = 1,
            sessionId = "ea2d83c4-5669-4b6a-9c62-2c2dccb1fcc9",
            action,
            attended = true,
            platform = "windows",
            architecture,
            issuedAt = "2026-08-31T12:00:00Z",
            expiresAt,
            artifact = new
            {
                kind = "msi",
                url = url ?? SecurityPolicy.X64Artifact.Url,
                sha256 = sha256 ?? SecurityPolicy.X64Artifact.Sha256,
                version = "1.4.9",
                publisherSubjectContains = publisher,
            },
        };

        return JsonSerializer.Serialize(payload);
    }

    private static string SignEnvelope(ECDsa signer, string payloadJson)
    {
        byte[] payload = Encoding.UTF8.GetBytes(payloadJson);
        byte[] signature = signer.SignData(
            payload,
            HashAlgorithmName.SHA256,
            DSASignatureFormat.IeeeP1363FixedFieldConcatenation);

        return JsonSerializer.Serialize(new
        {
            keyId = SecurityPolicy.ManifestKeyId,
            payload = Base64UrlEncode(payload),
            signature = Base64UrlEncode(signature),
        });
    }

    private static string EncodePublicKey(ECParameters parameters)
    {
        byte[] key = new byte[65];
        key[0] = 0x04;
        parameters.Q.X!.CopyTo(key, 1);
        parameters.Q.Y!.CopyTo(key, 33);
        return Base64UrlEncode(key);
    }

    private static string Base64UrlEncode(byte[] value) =>
        Convert.ToBase64String(value).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    private static void ExpectThrows<T>(Action action) where T : Exception
    {
        try
        {
            action();
        }
        catch (T)
        {
            return;
        }

        throw new InvalidOperationException($"Expected {typeof(T).Name} was not thrown.");
    }

    private static void Assert(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    private sealed class FixedTimeProvider(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }
}
