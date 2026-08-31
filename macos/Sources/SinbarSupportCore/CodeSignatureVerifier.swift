import Foundation
import Security

public enum CodeSignatureVerifier {
    public static func verifyRustDeskApp(
        at appURL: URL,
        configuration: RuntimeConfiguration
    ) throws {
        let requirementText = "identifier \"\(configuration.rustDeskBundleIdentifier)\" "
            + "and anchor apple generic "
            + "and certificate leaf[subject.OU] = \"\(configuration.rustDeskTeamIdentifier)\""
        try verifyStaticCode(
            at: appURL,
            requirementText: requirementText,
            expectedIdentifier: configuration.rustDeskBundleIdentifier,
            expectedTeamIdentifier: configuration.rustDeskTeamIdentifier
        )

        let gatekeeper = try SystemToolRunner.run(
            .spctl,
            arguments: ["--assess", "--type", "execute", "--verbose=4", appURL.path]
        )
        guard gatekeeper.exitCode == 0 else {
            throw SupportError.codeSignatureFailure("Gatekeeper rejected the RustDesk application")
        }
    }

    public static func verifyInstalledHelper(configuration: RuntimeConfiguration) throws {
        let helperURL = URL(
            fileURLWithPath: "/Library/PrivilegedHelperTools/\(configuration.helperCodeIdentifier)"
        )
        try verifyStaticCode(
            at: helperURL,
            requirementText: configuration.helperCodeSigningRequirement,
            expectedIdentifier: configuration.helperCodeIdentifier,
            expectedTeamIdentifier: configuration.sinbarTeamIdentifier
        )
    }

    private static func verifyStaticCode(
        at url: URL,
        requirementText: String,
        expectedIdentifier: String,
        expectedTeamIdentifier: String
    ) throws {
        var staticCode: SecStaticCode?
        guard SecStaticCodeCreateWithPath(url as CFURL, [], &staticCode) == errSecSuccess,
              let staticCode else {
            throw SupportError.codeSignatureFailure("signed code cannot be opened")
        }

        var requirement: SecRequirement?
        guard SecRequirementCreateWithString(
            requirementText as CFString,
            [],
            &requirement
        ) == errSecSuccess,
        let requirement else {
            throw SupportError.codeSignatureFailure("publisher requirement cannot be created")
        }

        let flags = SecCSFlags(
            rawValue: kSecCSCheckAllArchitectures | kSecCSStrictValidate | kSecCSCheckNestedCode
        )
        guard SecStaticCodeCheckValidity(staticCode, flags, requirement) == errSecSuccess else {
            throw SupportError.codeSignatureFailure("strict Apple code-signature validation failed")
        }

        var signingInformation: CFDictionary?
        guard SecCodeCopySigningInformation(
            staticCode,
            SecCSFlags(rawValue: kSecCSSigningInformation),
            &signingInformation
        ) == errSecSuccess,
        let info = signingInformation as? [String: Any],
        info[kSecCodeInfoIdentifier as String] as? String == expectedIdentifier,
        info[kSecCodeInfoTeamIdentifier as String] as? String == expectedTeamIdentifier else {
            throw SupportError.codeSignatureFailure("code identity does not match the pinned publisher")
        }
    }
}
