import CryptoKit
import Foundation

public struct SignedManifestVerifier: Sendable {
    private let configuration: RuntimeConfiguration

    public init(configuration: RuntimeConfiguration) {
        self.configuration = configuration
    }

    public func verify(envelopeData: Data, now: Date = Date()) throws -> ValidatedManifest {
        guard envelopeData.count <= 131_072 else {
            throw SupportError.invalidServerResponse("signed envelope is too large")
        }

        _ = try StrictJSON.object(
            from: envelopeData,
            exactKeys: ["keyId", "payload", "signature"],
            context: "signed envelope"
        )
        let envelope = try JSONDecoder().decode(SignedManifestEnvelope.self, from: envelopeData)
        guard envelope.keyId == configuration.manifestKeyID else {
            throw SupportError.invalidSignature
        }

        let payload = try Base64URL.decode(envelope.payload)
        let signatureData = try Base64URL.decode(envelope.signature, maximumCharacters: 128)
        guard signatureData.count == 64 else {
            throw SupportError.invalidSignature
        }

        do {
            let publicKey = try P256.Signing.PublicKey(
                x963Representation: configuration.manifestPublicKeyX963
            )
            let signature = try P256.Signing.ECDSASignature(rawRepresentation: signatureData)
            guard publicKey.isValidSignature(signature, for: payload) else {
                throw SupportError.invalidSignature
            }
        } catch let error as SupportError {
            throw error
        } catch {
            throw SupportError.invalidSignature
        }

        let payloadObject = try StrictJSON.object(
            from: payload,
            exactKeys: [
                "schemaVersion", "sessionId", "action", "attended", "platform",
                "architecture", "issuedAt", "expiresAt", "artifact",
            ],
            context: "manifest"
        )
        _ = try StrictJSON.nestedObject(
            payloadObject["artifact"],
            exactKeys: [
                "kind", "url", "sha256", "version", "bundleIdentifier", "teamIdentifier",
            ],
            context: "artifact"
        )
        let manifest = try JSONDecoder().decode(SupportManifest.self, from: payload)
        return try validate(manifest: manifest, now: now)
    }

    private func validate(manifest: SupportManifest, now: Date) throws -> ValidatedManifest {
        guard manifest.schemaVersion == 1 else {
            throw SupportError.rejectedManifest("unsupported schema version")
        }
        guard let sessionID = UUID(uuidString: manifest.sessionId),
              sessionID.uuidString.lowercased() == manifest.sessionId.lowercased() else {
            throw SupportError.rejectedManifest("invalid session identifier")
        }
        guard manifest.action == "ensure-and-launch-rustdesk",
              manifest.attended else {
            throw SupportError.rejectedManifest("only attended RustDesk launch is allowed")
        }
        guard manifest.platform == "macos",
              manifest.architecture == ClientArchitecture.current.rawValue else {
            throw SupportError.rejectedManifest("platform or architecture mismatch")
        }

        let issuedAt = try Self.parseUTC(manifest.issuedAt)
        let expiresAt = try Self.parseUTC(manifest.expiresAt)
        guard issuedAt <= expiresAt,
              issuedAt.timeIntervalSince(now) <= 60,
              expiresAt > now,
              expiresAt.timeIntervalSince(issuedAt) <= 300 else {
            throw SupportError.rejectedManifest("manifest timestamps are invalid or expired")
        }

        guard manifest.artifact.sha256.range(
            of: "^[0-9a-f]{64}$",
            options: .regularExpression
        ) != nil else {
            throw SupportError.rejectedManifest("artifact SHA-256 is invalid")
        }
        guard manifest.artifact.version.range(
            of: "^[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$",
            options: .regularExpression
        ) != nil else {
            throw SupportError.rejectedManifest("artifact version is invalid")
        }
        guard manifest.artifact.bundleIdentifier == configuration.rustDeskBundleIdentifier,
              manifest.artifact.teamIdentifier == configuration.rustDeskTeamIdentifier else {
            throw SupportError.rejectedManifest("RustDesk publisher identity does not match local pins")
        }

        guard let pinnedArtifact = configuration.rustDeskArtifacts[.current],
              manifest.artifact.kind == pinnedArtifact.kind,
              manifest.artifact.url == pinnedArtifact.url.absoluteString,
              manifest.artifact.sha256 == pinnedArtifact.sha256,
              manifest.artifact.version == pinnedArtifact.version else {
            throw SupportError.rejectedManifest("artifact does not match the local release catalog")
        }

        guard let artifactURL = URL(string: manifest.artifact.url),
              artifactURL.scheme == "https",
              artifactURL.host?.lowercased() == "support.sinbarconsultants.com",
              artifactURL.user == nil,
              artifactURL.password == nil,
              artifactURL.port == nil,
              artifactURL.query == nil,
              artifactURL.fragment == nil,
              artifactURL.path.hasPrefix(configuration.artifactPathPrefix),
              artifactURL.path.range(of: "^[A-Za-z0-9._/-]+$", options: .regularExpression) != nil,
              !artifactURL.path.contains("..") else {
            throw SupportError.rejectedManifest("artifact URL is outside the pinned HTTPS origin")
        }

        let expectedExtension = manifest.artifact.kind.rawValue
        guard artifactURL.pathExtension.lowercased() == expectedExtension else {
            throw SupportError.rejectedManifest("artifact type and extension do not match")
        }

        return ValidatedManifest(
            sessionID: sessionID,
            issuedAt: issuedAt,
            expiresAt: expiresAt,
            artifactURL: artifactURL,
            artifact: manifest.artifact
        )
    }

    private static func parseUTC(_ value: String) throws -> Date {
        guard value.range(
            of: "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\\.[0-9]{1,9})?Z$",
            options: .regularExpression
        ) != nil else {
            throw SupportError.rejectedManifest("timestamp is not strict UTC RFC3339")
        }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: value) {
            return date
        }
        formatter.formatOptions = [.withInternetDateTime]
        guard let date = formatter.date(from: value) else {
            throw SupportError.rejectedManifest("timestamp cannot be decoded")
        }
        return date
    }
}
