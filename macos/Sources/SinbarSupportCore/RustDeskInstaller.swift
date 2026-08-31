import Darwin
import Foundation

public final class RustDeskInstaller {
    private let configuration: RuntimeConfiguration
    private let fileManager = FileManager.default

    public init(configuration: RuntimeConfiguration) {
        self.configuration = configuration
    }

    public func install(
        artifactURL: URL,
        manifest: ValidatedManifest,
        callerUID: uid_t
    ) throws {
        try FileSecurity.validateDownloadedArtifact(
            at: artifactURL,
            callerUID: callerUID,
            maximumBytes: configuration.maximumArtifactBytes
        )
        let rootCopy = try FileSecurity.copyToRootOwnedStaging(
            sourceURL: artifactURL,
            callerUID: callerUID,
            maximumBytes: configuration.maximumArtifactBytes,
            fileExtension: manifest.artifact.kind.rawValue
        )
        defer { rootCopy.remove() }

        guard try FileDigest.sha256(at: rootCopy.fileURL) == manifest.artifact.sha256 else {
            throw SupportError.artifactFailure("SHA-256 does not match the signed release catalog")
        }

        switch manifest.artifact.kind {
        case .dmg:
            try installFromDMG(artifactURL: rootCopy.fileURL, manifest: manifest)
        case .pkg:
            try installFromPKG(artifactURL: rootCopy.fileURL, manifest: manifest)
        }
    }

    private func installFromDMG(artifactURL: URL, manifest: ValidatedManifest) throws {
        let mountURL = URL(
            fileURLWithPath: "/private/var/tmp/com.sinbarconsultants.supportassistant.mount.\(UUID().uuidString)",
            isDirectory: true
        )
        try fileManager.createDirectory(
            at: mountURL,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: NSNumber(value: Int16(0o700))]
        )
        defer { try? fileManager.removeItem(at: mountURL) }

        let attach = try SystemToolRunner.run(
            .hdiutil,
            arguments: [
                "attach", "-readonly", "-nobrowse", "-noautoopen",
                "-mountpoint", mountURL.path, artifactURL.path,
            ]
        )
        guard attach.exitCode == 0 else {
            throw SupportError.artifactFailure("read-only disk image mount failed")
        }
        defer {
            _ = try? SystemToolRunner.run(
                .hdiutil,
                arguments: ["detach", mountURL.path]
            )
        }

        let sourceApp = try findUniqueRustDeskApp(beneath: mountURL)
        try CodeSignatureVerifier.verifyRustDeskApp(at: sourceApp, configuration: configuration)
        try requireVersion(manifest.artifact.version, at: sourceApp)
        try atomicInstallVerifiedApp(
            from: sourceApp,
            expectedVersion: manifest.artifact.version
        )
    }

    private func installFromPKG(artifactURL: URL, manifest: ValidatedManifest) throws {
        let signature = try SystemToolRunner.run(
            .pkgutil,
            arguments: ["--check-signature", artifactURL.path]
        )
        let teamPattern = "Developer ID Installer:.*\\(\(configuration.rustDeskTeamIdentifier)\\)"
        guard signature.exitCode == 0,
              signature.output.range(of: teamPattern, options: .regularExpression) != nil else {
            throw SupportError.codeSignatureFailure("installer package publisher is not pinned")
        }

        let gatekeeper = try SystemToolRunner.run(
            .spctl,
            arguments: ["--assess", "--type", "install", "--verbose=4", artifactURL.path]
        )
        guard gatekeeper.exitCode == 0 else {
            throw SupportError.codeSignatureFailure("Gatekeeper rejected the installer package")
        }

        let expansionURL = URL(
            fileURLWithPath: "/private/var/tmp/com.sinbarconsultants.supportassistant.pkg.\(UUID().uuidString)",
            isDirectory: true
        )
        defer { try? fileManager.removeItem(at: expansionURL) }
        let expansion = try SystemToolRunner.run(
            .pkgutil,
            arguments: ["--expand-full", artifactURL.path, expansionURL.path]
        )
        guard expansion.exitCode == 0 else {
            throw SupportError.artifactFailure("installer package inspection failed")
        }

        let packagedApp = try findUniqueRustDeskApp(beneath: expansionURL)
        try CodeSignatureVerifier.verifyRustDeskApp(at: packagedApp, configuration: configuration)
        try requireVersion(manifest.artifact.version, at: packagedApp)

        let installation = try SystemToolRunner.run(
            .installer,
            arguments: ["-pkg", artifactURL.path, "-target", "/"]
        )
        guard installation.exitCode == 0 else {
            throw SupportError.installationFailure("Apple Installer rejected the RustDesk package")
        }

        try verifyInstalledApp(version: manifest.artifact.version)
    }

    private func atomicInstallVerifiedApp(
        from sourceApp: URL,
        expectedVersion: String
    ) throws {
        let destination = HelperServiceConstants.installedRustDeskURL
        let identifier = UUID().uuidString
        let transactionRoot = try prepareTransactionRoot()
        let staging = transactionRoot.appendingPathComponent(
            "RustDesk.candidate.\(identifier).app",
            isDirectory: true
        )

        var stagingMayBeRemoved = true
        defer {
            if stagingMayBeRemoved {
                try? fileManager.removeItem(at: staging)
            }
        }

        var previousVersion: String?
        var previousIdentity: FileIdentity?
        if fileManager.fileExists(atPath: destination.path) {
            try rejectSymlink(at: destination)
            try CodeSignatureVerifier.verifyRustDeskApp(at: destination, configuration: configuration)
            previousVersion = try bundleVersion(at: destination)
            previousIdentity = try fileIdentity(at: destination)
        }

        let copy = try SystemToolRunner.run(
            .ditto,
            arguments: ["--rsrc", "--extattr", sourceApp.path, staging.path]
        )
        guard copy.exitCode == 0 else {
            throw SupportError.installationFailure("verified application copy failed")
        }
        try CodeSignatureVerifier.verifyRustDeskApp(at: staging, configuration: configuration)
        try requireVersion(expectedVersion, at: staging)
        try requireSameVolume(staging, destination.deletingLastPathComponent())
        let candidateIdentity = try fileIdentity(at: staging)

        if let previousVersion, let previousIdentity {
            // RENAME_SWAP is a single filesystem transaction: after a crash, either
            // the previous verified app or the pre-verified replacement remains at
            // /Applications/RustDesk.app. There is never an intermediate missing app.
            guard renamex_np(
                staging.path,
                destination.path,
                UInt32(RENAME_SWAP)
            ) == 0 else {
                throw SupportError.installationFailure("atomic application swap failed")
            }

            // The former destination is now the protected staging entry. Never let
            // generic cleanup delete it until the replacement is fully accepted.
            stagingMayBeRemoved = false

            do {
                guard try fileIdentity(at: staging) == previousIdentity else {
                    throw SupportError.installationFailure(
                        "the application changed during atomic replacement"
                    )
                }
                try CodeSignatureVerifier.verifyRustDeskApp(at: staging, configuration: configuration)
                try requireVersion(previousVersion, at: staging)
                try CodeSignatureVerifier.verifyRustDeskApp(at: destination, configuration: configuration)
                try requireVersion(expectedVersion, at: destination)
            } catch {
                // A second atomic swap restores the previous verified app. If the
                // swap itself cannot be performed, retain both copies: the current
                // destination and the root-only recovery copy at `staging`.
                guard renamex_np(
                    staging.path,
                    destination.path,
                    UInt32(RENAME_SWAP)
                ) == 0 else {
                    throw SupportError.installationFailure(
                        "replacement verification failed; the previous app remains in protected recovery staging"
                    )
                }
                stagingMayBeRemoved = true
                try CodeSignatureVerifier.verifyRustDeskApp(
                    at: destination,
                    configuration: configuration
                )
                try requireVersion(previousVersion, at: destination)
                guard try fileIdentity(at: destination) == previousIdentity else {
                    throw SupportError.installationFailure(
                        "replacement failed and restored app identity could not be confirmed"
                    )
                }
                throw SupportError.installationFailure(
                    "replacement failed and the previous verified app was restored"
                )
            }

            // The old app is still at the root-only staging path. It is safe to
            // remove only after both sides of the swap were verified.
            try fileManager.removeItem(at: staging)
            stagingMayBeRemoved = false
        } else {
            // RENAME_EXCL refuses to overwrite a destination created concurrently.
            guard renamex_np(
                staging.path,
                destination.path,
                UInt32(RENAME_EXCL)
            ) == 0 else {
                throw SupportError.installationFailure("atomic first installation failed")
            }
            do {
                try CodeSignatureVerifier.verifyRustDeskApp(
                    at: destination,
                    configuration: configuration
                )
                try requireVersion(expectedVersion, at: destination)
            } catch {
                guard let installedIdentity = try? fileIdentity(at: destination),
                      installedIdentity == candidateIdentity else {
                    throw SupportError.installationFailure(
                        "first installation verification failed after the destination changed"
                    )
                }
                guard renamex_np(
                    destination.path,
                    staging.path,
                    UInt32(RENAME_EXCL)
                ) == 0 else {
                    throw SupportError.installationFailure(
                        "rejected first installation could not be returned to protected staging"
                    )
                }
                throw SupportError.installationFailure(
                    "first installation failed post-install verification"
                )
            }
        }
    }

    private struct FileIdentity: Equatable {
        let device: dev_t
        let inode: ino_t
    }

    private func prepareTransactionRoot() throws -> URL {
        let parent = URL(
            fileURLWithPath: "/Library/Application Support/Sinbar Support Assistant",
            isDirectory: true
        )
        var parentStatus = stat()
        guard lstat(parent.path, &parentStatus) == 0,
              (parentStatus.st_mode & S_IFMT) == S_IFDIR,
              parentStatus.st_uid == 0,
              (parentStatus.st_mode & 0o022) == 0 else {
            throw SupportError.installationFailure("trusted installation support directory is invalid")
        }

        let root = parent.appendingPathComponent("InstallTransactions", isDirectory: true)
        if mkdir(root.path, mode_t(0o700)) != 0, errno != EEXIST {
            throw SupportError.installationFailure("protected installation staging cannot be created")
        }
        guard chmod(root.path, mode_t(0o700)) == 0 else {
            throw SupportError.installationFailure("protected installation staging cannot be secured")
        }

        var rootStatus = stat()
        guard lstat(root.path, &rootStatus) == 0,
              (rootStatus.st_mode & S_IFMT) == S_IFDIR,
              rootStatus.st_uid == 0,
              (rootStatus.st_mode & 0o077) == 0 else {
            throw SupportError.installationFailure("protected installation staging is not root-only")
        }
        return root
    }

    private func requireSameVolume(_ first: URL, _ second: URL) throws {
        let firstIdentity = try fileIdentity(at: first)
        let secondIdentity = try fileIdentity(at: second)
        guard firstIdentity.device == secondIdentity.device else {
            throw SupportError.installationFailure("atomic staging is not on the Applications volume")
        }
    }

    private func fileIdentity(at url: URL) throws -> FileIdentity {
        var status = stat()
        guard lstat(url.path, &status) == 0 else {
            throw SupportError.installationFailure("application filesystem identity is unavailable")
        }
        return FileIdentity(device: status.st_dev, inode: status.st_ino)
    }

    private func verifyInstalledApp(version: String) throws {
        let installed = HelperServiceConstants.installedRustDeskURL
        try rejectSymlink(at: installed)
        try CodeSignatureVerifier.verifyRustDeskApp(at: installed, configuration: configuration)
        try requireVersion(version, at: installed)
    }

    private func requireVersion(_ expected: String, at appURL: URL) throws {
        guard try bundleVersion(at: appURL) == expected else {
            throw SupportError.codeSignatureFailure("RustDesk version does not match the pinned release")
        }
    }

    private func bundleVersion(at appURL: URL) throws -> String {
        guard let bundle = Bundle(url: appURL),
              let version = bundle.object(
                forInfoDictionaryKey: "CFBundleShortVersionString"
              ) as? String,
              version.range(
                of: "^[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$",
                options: .regularExpression
              ) != nil else {
            throw SupportError.codeSignatureFailure("RustDesk version metadata is invalid")
        }
        return version
    }

    private func findUniqueRustDeskApp(beneath root: URL) throws -> URL {
        guard let enumerator = fileManager.enumerator(
            at: root,
            includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
            options: [.skipsHiddenFiles, .skipsPackageDescendants]
        ) else {
            throw SupportError.artifactFailure("artifact contents cannot be enumerated")
        }

        var candidates: [URL] = []
        for case let candidate as URL in enumerator {
            if candidate.pathComponents.count > root.pathComponents.count + 4 {
                enumerator.skipDescendants()
                continue
            }
            guard candidate.lastPathComponent == "RustDesk.app" else { continue }
            let values = try candidate.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard values.isDirectory == true, values.isSymbolicLink != true else {
                throw SupportError.artifactFailure("RustDesk.app is not a regular application directory")
            }
            let canonical = candidate.resolvingSymlinksInPath().standardizedFileURL.path
            let rootPath = root.resolvingSymlinksInPath().standardizedFileURL.path + "/"
            guard canonical.hasPrefix(rootPath) else {
                throw SupportError.artifactFailure("application escaped the mounted artifact")
            }
            candidates.append(candidate)
            enumerator.skipDescendants()
        }

        guard candidates.count == 1, let app = candidates.first else {
            throw SupportError.artifactFailure("artifact must contain exactly one RustDesk.app")
        }
        return app
    }

    private func rejectSymlink(at url: URL) throws {
        var targetStatus = stat()
        guard lstat(url.path, &targetStatus) == 0,
              (targetStatus.st_mode & S_IFMT) == S_IFDIR else {
            throw SupportError.installationFailure("the RustDesk destination is not a regular app directory")
        }
    }
}
