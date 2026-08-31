import Foundation

public enum ClientArchitecture: String, Codable, Sendable {
    case x86_64
    case arm64

    public static var current: ClientArchitecture {
        #if arch(arm64)
        return .arm64
        #else
        return .x86_64
        #endif
    }
}

public enum ArtifactKind: String, Codable, Sendable {
    case dmg
    case pkg
}

public struct ConsumeRequest: Codable, Sendable, Equatable {
    public let token: String
    public let platform: String
    public let architecture: String
    public let assistantVersion: String

    public init(token: String, architecture: ClientArchitecture, assistantVersion: String) {
        self.token = token
        self.platform = "macos"
        self.architecture = architecture.rawValue
        self.assistantVersion = assistantVersion
    }
}

public struct SignedManifestEnvelope: Codable, Sendable, Equatable {
    public let keyId: String
    public let payload: String
    public let signature: String
}

public struct RustDeskArtifact: Codable, Sendable, Equatable {
    public let kind: ArtifactKind
    public let url: String
    public let sha256: String
    public let version: String
    public let bundleIdentifier: String
    public let teamIdentifier: String
}

public struct SupportManifest: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let sessionId: String
    public let action: String
    public let attended: Bool
    public let platform: String
    public let architecture: String
    public let issuedAt: String
    public let expiresAt: String
    public let artifact: RustDeskArtifact
}

public struct ValidatedManifest: Sendable, Equatable {
    public let sessionID: UUID
    public let issuedAt: Date
    public let expiresAt: Date
    public let artifactURL: URL
    public let artifact: RustDeskArtifact
}
