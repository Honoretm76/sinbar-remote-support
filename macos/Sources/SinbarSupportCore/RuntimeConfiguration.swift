import Darwin
import Foundation

public struct RuntimeConfiguration: Sendable, Equatable {
    public struct PinnedArtifact: Sendable, Equatable {
        public let kind: ArtifactKind
        public let url: URL
        public let sha256: String
        public let version: String

        public init(kind: ArtifactKind, url: URL, sha256: String, version: String) {
            self.kind = kind
            self.url = url
            self.sha256 = sha256
            self.version = version
        }
    }

    public static let installedURL = URL(
        fileURLWithPath: "/Library/Application Support/Sinbar Support Assistant/config.plist",
        isDirectory: false
    )

    public let apiBaseURL: URL
    public let artifactPathPrefix: String
    public let manifestKeyID: String
    public let manifestPublicKeyX963: Data
    public let rustDeskBundleIdentifier: String
    public let rustDeskTeamIdentifier: String
    public let rustDeskArtifacts: [ClientArchitecture: PinnedArtifact]
    public let assistantBundleIdentifier: String
    public let sinbarTeamIdentifier: String
    public let helperCodeIdentifier: String
    public let assistantVersion: String
    public let maximumArtifactBytes: Int64

    public var assistantCodeSigningRequirement: String {
        "anchor apple generic and identifier \"\(assistantBundleIdentifier)\" "
            + "and certificate 1[field.1.2.840.113635.100.6.2.6] exists "
            + "and certificate leaf[field.1.2.840.113635.100.6.1.13] exists "
            + "and certificate leaf[subject.OU] = \"\(sinbarTeamIdentifier)\""
    }

    public var helperCodeSigningRequirement: String {
        "anchor apple generic and identifier \"\(helperCodeIdentifier)\" "
            + "and certificate 1[field.1.2.840.113635.100.6.2.6] exists "
            + "and certificate leaf[field.1.2.840.113635.100.6.1.13] exists "
            + "and certificate leaf[subject.OU] = \"\(sinbarTeamIdentifier)\""
    }

    public init(
        apiBaseURL: URL,
        artifactPathPrefix: String,
        manifestKeyID: String,
        manifestPublicKeyX963: Data,
        rustDeskBundleIdentifier: String,
        rustDeskTeamIdentifier: String,
        rustDeskArtifacts: [ClientArchitecture: PinnedArtifact],
        assistantBundleIdentifier: String,
        sinbarTeamIdentifier: String,
        helperCodeIdentifier: String,
        assistantVersion: String,
        maximumArtifactBytes: Int64
    ) throws {
        guard apiBaseURL.absoluteString == "https://support.sinbarconsultants.com",
              apiBaseURL.scheme == "https",
              apiBaseURL.host == "support.sinbarconsultants.com",
              apiBaseURL.user == nil,
              apiBaseURL.password == nil,
              apiBaseURL.port == nil,
              apiBaseURL.query == nil,
              apiBaseURL.fragment == nil else {
            throw SupportError.invalidConfiguration("API origin is not the production pinned origin")
        }
        guard artifactPathPrefix == "/download/vendor/rustdesk/" else {
            throw SupportError.invalidConfiguration("artifact path prefix is not approved")
        }
        guard Self.matches(manifestKeyID, pattern: "^[A-Za-z0-9._-]{1,64}$") else {
            throw SupportError.invalidConfiguration("manifest key identifier is invalid")
        }
        guard manifestPublicKeyX963.count == 65,
              manifestPublicKeyX963.first == 0x04 else {
            throw SupportError.invalidConfiguration("P-256 public key must be a 65-byte X9.63 point")
        }
        guard rustDeskBundleIdentifier == "com.carriez.rustdesk" else {
            throw SupportError.invalidConfiguration("RustDesk bundle identifier is not the approved release pin")
        }
        guard Self.matches(rustDeskTeamIdentifier, pattern: "^[A-Z0-9]{10}$") else {
            throw SupportError.invalidConfiguration("RustDesk Team Identifier must be verified and pinned")
        }
        guard Set(rustDeskArtifacts.keys) == Set([ClientArchitecture.x86_64, .arm64]) else {
            throw SupportError.invalidConfiguration("both RustDesk architectures must be pinned")
        }
        for (architecture, artifact) in rustDeskArtifacts {
            let expectedSuffix = architecture == .arm64
                ? "/rustdesk-1.4.9-aarch64.dmg"
                : "/rustdesk-1.4.9-x86_64.dmg"
            guard artifact.kind == .dmg,
                  artifact.url.scheme == "https",
                  artifact.url.host == "support.sinbarconsultants.com",
                  artifact.url.port == nil,
                  artifact.url.user == nil,
                  artifact.url.password == nil,
                  artifact.url.query == nil,
                  artifact.url.fragment == nil,
                  artifact.url.path == artifactPathPrefix + "1.4.9/macos" + expectedSuffix,
                  artifact.sha256.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil,
                  artifact.version == "1.4.9" else {
                throw SupportError.invalidConfiguration("RustDesk artifact catalog is not fully pinned")
            }
        }
        guard assistantBundleIdentifier == "com.sinbarconsultants.supportassistant",
              helperCodeIdentifier == "com.sinbarconsultants.supportassistant.installhelper" else {
            throw SupportError.invalidConfiguration("Sinbar code identifiers are not approved")
        }
        guard Self.matches(sinbarTeamIdentifier, pattern: "^[A-Z0-9]{10}$") else {
            throw SupportError.invalidConfiguration("Sinbar Team Identifier must be configured")
        }
        guard assistantVersion == "2.0.0" else {
            throw SupportError.invalidConfiguration("assistant version mismatch")
        }
        guard (1_048_576...536_870_912).contains(maximumArtifactBytes) else {
            throw SupportError.invalidConfiguration("artifact size limit is outside the approved range")
        }

        self.apiBaseURL = apiBaseURL
        self.artifactPathPrefix = artifactPathPrefix
        self.manifestKeyID = manifestKeyID
        self.manifestPublicKeyX963 = manifestPublicKeyX963
        self.rustDeskBundleIdentifier = rustDeskBundleIdentifier
        self.rustDeskTeamIdentifier = rustDeskTeamIdentifier
        self.rustDeskArtifacts = rustDeskArtifacts
        self.assistantBundleIdentifier = assistantBundleIdentifier
        self.sinbarTeamIdentifier = sinbarTeamIdentifier
        self.helperCodeIdentifier = helperCodeIdentifier
        self.assistantVersion = assistantVersion
        self.maximumArtifactBytes = maximumArtifactBytes
    }

    public static func loadInstalled() throws -> RuntimeConfiguration {
        try verifyRootOwnedRegularFile(installedURL)

        guard let dictionary = NSDictionary(contentsOf: installedURL) as? [String: Any] else {
            throw SupportError.invalidConfiguration("runtime configuration cannot be decoded")
        }

        let allowedKeys: Set<String> = [
            "APIBaseURL", "ArtifactPathPrefix", "ManifestKeyID",
            "ManifestP256PublicKeyX963Base64URL", "RustDeskBundleIdentifier",
            "RustDeskTeamIdentifier", "AssistantBundleIdentifier", "SinbarTeamIdentifier",
            "HelperCodeIdentifier",
            "RustDeskArtifacts", "AssistantVersion", "MaximumArtifactBytes",
        ]
        guard Set(dictionary.keys) == allowedKeys else {
            throw SupportError.invalidConfiguration("runtime configuration fields are not exact")
        }

        func requiredString(_ key: String) throws -> String {
            guard let value = dictionary[key] as? String, !value.isEmpty else {
                throw SupportError.invalidConfiguration("missing \(key)")
            }
            return value
        }

        let baseString = try requiredString("APIBaseURL")
        guard let baseURL = URL(string: baseString) else {
            throw SupportError.invalidConfiguration("APIBaseURL is invalid")
        }
        let publicKey = try Base64URL.decode(
            requiredString("ManifestP256PublicKeyX963Base64URL"),
            maximumCharacters: 128
        )
        guard let maxBytes = dictionary["MaximumArtifactBytes"] as? NSNumber else {
            throw SupportError.invalidConfiguration("MaximumArtifactBytes is invalid")
        }

        guard let artifactDictionaries = dictionary["RustDeskArtifacts"] as? [String: Any],
              Set(artifactDictionaries.keys) == Set(["x86_64", "arm64"]) else {
            throw SupportError.invalidConfiguration("RustDeskArtifacts is invalid")
        }
        var artifacts: [ClientArchitecture: PinnedArtifact] = [:]
        for architecture in [ClientArchitecture.x86_64, .arm64] {
            let object = try StrictJSON.nestedObject(
                artifactDictionaries[architecture.rawValue],
                exactKeys: ["Kind", "URL", "SHA256", "Version"],
                context: "runtime artifact"
            )
            guard let kindString = object["Kind"] as? String,
                  let kind = ArtifactKind(rawValue: kindString),
                  let urlString = object["URL"] as? String,
                  let url = URL(string: urlString),
                  let sha256 = object["SHA256"] as? String,
                  let version = object["Version"] as? String else {
                throw SupportError.invalidConfiguration("runtime artifact values are invalid")
            }
            artifacts[architecture] = PinnedArtifact(
                kind: kind,
                url: url,
                sha256: sha256,
                version: version
            )
        }

        return try RuntimeConfiguration(
            apiBaseURL: baseURL,
            artifactPathPrefix: requiredString("ArtifactPathPrefix"),
            manifestKeyID: requiredString("ManifestKeyID"),
            manifestPublicKeyX963: publicKey,
            rustDeskBundleIdentifier: requiredString("RustDeskBundleIdentifier"),
            rustDeskTeamIdentifier: requiredString("RustDeskTeamIdentifier"),
            rustDeskArtifacts: artifacts,
            assistantBundleIdentifier: requiredString("AssistantBundleIdentifier"),
            sinbarTeamIdentifier: requiredString("SinbarTeamIdentifier"),
            helperCodeIdentifier: requiredString("HelperCodeIdentifier"),
            assistantVersion: requiredString("AssistantVersion"),
            maximumArtifactBytes: maxBytes.int64Value
        )
    }

    private static func verifyRootOwnedRegularFile(_ url: URL) throws {
        var fileStatus = stat()
        guard lstat(url.path, &fileStatus) == 0,
              (fileStatus.st_mode & S_IFMT) == S_IFREG,
              fileStatus.st_uid == 0,
              (fileStatus.st_mode & 0o022) == 0 else {
            throw SupportError.invalidConfiguration("runtime configuration is missing or not root-owned")
        }
    }

    private static func matches(_ value: String, pattern: String) -> Bool {
        value.range(of: pattern, options: .regularExpression) != nil
    }
}
