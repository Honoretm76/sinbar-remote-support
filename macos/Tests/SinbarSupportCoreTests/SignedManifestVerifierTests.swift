import CryptoKit
import Foundation
import XCTest
@testable import SinbarSupportCore

final class SignedManifestVerifierTests: XCTestCase {
    private let privateKey = P256.Signing.PrivateKey()
    private let now = Date(timeIntervalSince1970: 1_788_000_000)

    func testValidSignedManifestPasses() throws {
        let configuration = try makeConfiguration()
        let envelope = try makeEnvelope(configuration: configuration)
        let result = try SignedManifestVerifier(configuration: configuration)
            .verify(envelopeData: envelope, now: now)
        XCTAssertEqual(result.artifact.version, "1.4.9")
        XCTAssertEqual(result.artifact.kind, .dmg)
    }

    func testTamperedPayloadFailsBeforeParsing() throws {
        let configuration = try makeConfiguration()
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: makeEnvelope(configuration: configuration))
                as? [String: Any]
        )
        object["payload"] = Base64URL.encode(Data("{}".utf8))
        let tampered = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        XCTAssertThrowsError(
            try SignedManifestVerifier(configuration: configuration)
                .verify(envelopeData: tampered, now: now)
        )
    }

    func testUnknownEnvelopeFieldFails() throws {
        let configuration = try makeConfiguration()
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: makeEnvelope(configuration: configuration))
                as? [String: Any]
        )
        object["command"] = "anything"
        let invalid = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        XCTAssertThrowsError(
            try SignedManifestVerifier(configuration: configuration)
                .verify(envelopeData: invalid, now: now)
        )
    }

    private func makeConfiguration() throws -> RuntimeConfiguration {
        let hash = String(repeating: "a", count: 64)
        let x64URL = URL(string: "https://support.sinbarconsultants.com/download/vendor/rustdesk/1.4.9/macos/rustdesk-1.4.9-x86_64.dmg")!
        let armURL = URL(string: "https://support.sinbarconsultants.com/download/vendor/rustdesk/1.4.9/macos/rustdesk-1.4.9-aarch64.dmg")!
        return try RuntimeConfiguration(
            apiBaseURL: URL(string: "https://support.sinbarconsultants.com")!,
            artifactPathPrefix: "/download/vendor/rustdesk/",
            manifestKeyID: "test-key-1",
            manifestPublicKeyX963: privateKey.publicKey.x963Representation,
            rustDeskBundleIdentifier: "com.example.rustdesk",
            rustDeskTeamIdentifier: "ABCDEFGHIJ",
            rustDeskArtifacts: [
                .x86_64: .init(kind: .dmg, url: x64URL, sha256: hash, version: "1.4.9"),
                .arm64: .init(kind: .dmg, url: armURL, sha256: hash, version: "1.4.9"),
            ],
            assistantBundleIdentifier: "com.sinbarconsultants.supportassistant",
            sinbarTeamIdentifier: "123456789A",
            helperCodeIdentifier: "com.sinbarconsultants.supportassistant.installhelper",
            assistantVersion: "2.0.0",
            maximumArtifactBytes: 536_870_912
        )
    }

    private func makeEnvelope(configuration: RuntimeConfiguration) throws -> Data {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        let pinned = try XCTUnwrap(configuration.rustDeskArtifacts[.current])
        let payload: [String: Any] = [
            "schemaVersion": 1,
            "sessionId": "9A1C4AEC-FD8C-4BE5-ACCA-A863CFB2A433",
            "action": "ensure-and-launch-rustdesk",
            "attended": true,
            "platform": "macos",
            "architecture": ClientArchitecture.current.rawValue,
            "issuedAt": formatter.string(from: now.addingTimeInterval(-10)),
            "expiresAt": formatter.string(from: now.addingTimeInterval(120)),
            "artifact": [
                "kind": pinned.kind.rawValue,
                "url": pinned.url.absoluteString,
                "sha256": pinned.sha256,
                "version": pinned.version,
                "bundleIdentifier": configuration.rustDeskBundleIdentifier,
                "teamIdentifier": configuration.rustDeskTeamIdentifier,
            ],
        ]
        let payloadData = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        let signature = try privateKey.signature(for: payloadData).rawRepresentation
        let envelope: [String: Any] = [
            "keyId": configuration.manifestKeyID,
            "payload": Base64URL.encode(payloadData),
            "signature": Base64URL.encode(signature),
        ]
        return try JSONSerialization.data(withJSONObject: envelope, options: [.sortedKeys])
    }
}
