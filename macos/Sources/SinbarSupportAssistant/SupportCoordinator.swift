import AppKit
import Foundation
import SinbarSupportCore

final class SupportCoordinator: @unchecked Sendable {
    typealias StatusHandler = @Sendable (String) -> Void
    typealias ConsentHandler = @MainActor @Sendable (ValidatedManifest) -> Bool

    private let configuration: RuntimeConfiguration
    private let client: PinnedHTTPSClient
    private let verifier: SignedManifestVerifier
    private let status: StatusHandler
    private let consent: ConsentHandler

    init(
        configuration: RuntimeConfiguration,
        status: @escaping StatusHandler,
        consent: @escaping ConsentHandler
    ) {
        self.configuration = configuration
        self.client = PinnedHTTPSClient(configuration: configuration)
        self.verifier = SignedManifestVerifier(configuration: configuration)
        self.status = status
        self.consent = consent
    }

    func run(launch: SupportLaunch) async throws {
        status("Authenticating your one-time Sinbar support request…")
        let envelopeData = try await client.consume(token: launch.token)
        let manifest = try verifier.verify(envelopeData: envelopeData)

        status("Verified. Waiting for your approval…")
        guard await consent(manifest) else {
            throw SupportError.userCancelled
        }

        if try installedRustDeskIsApproved(version: manifest.artifact.version) {
            status("Opening verified RustDesk for attended support…")
            try await launchRustDesk()
            return
        }

        status("Downloading verified RustDesk from Sinbar…")
        let staged = try await client.downloadArtifact(from: manifest.artifactURL)
        defer { staged.remove() }

        guard try staged.sha256() == manifest.artifact.sha256 else {
            throw SupportError.artifactFailure("downloaded SHA-256 does not match")
        }

        status("Installing verified RustDesk…")
        try await PrivilegedHelperClient(configuration: configuration).install(
            artifactURL: staged.fileURL,
            signedEnvelope: envelopeData
        )

        guard try installedRustDeskIsApproved(version: manifest.artifact.version) else {
            throw SupportError.installationFailure("post-install verification failed")
        }
        status("Opening RustDesk for attended support…")
        try await launchRustDesk()
    }

    private func installedRustDeskIsApproved(version: String) throws -> Bool {
        let appURL = HelperServiceConstants.installedRustDeskURL
        guard FileManager.default.fileExists(atPath: appURL.path) else { return false }
        try CodeSignatureVerifier.verifyRustDeskApp(at: appURL, configuration: configuration)
        guard let bundle = Bundle(url: appURL),
              bundle.bundleIdentifier == configuration.rustDeskBundleIdentifier,
              bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String == version else {
            return false
        }
        return true
    }

    @MainActor
    private func launchRustDesk() async throws {
        let appURL = HelperServiceConstants.installedRustDeskURL
        let launchConfiguration = NSWorkspace.OpenConfiguration()
        launchConfiguration.activates = true
        launchConfiguration.addsToRecentItems = false
        do {
            _ = try await NSWorkspace.shared.openApplication(
                at: appURL,
                configuration: launchConfiguration
            )
        } catch {
            throw SupportError.installationFailure("verified RustDesk could not be opened")
        }
    }
}
