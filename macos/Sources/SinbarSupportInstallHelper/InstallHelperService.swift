import Darwin
import Foundation
import SinbarSupportCore

final class InstallHelperService: NSObject, RustDeskInstallHelperProtocol {
    private static let queue = DispatchQueue(
        label: "com.sinbarconsultants.supportassistant.installhelper.serial",
        qos: .userInitiated
    )
    private static let activityLock = NSLock()
    private static var pendingRequests = 0
    private static var idleGeneration: UInt64 = 0

    private let configuration: RuntimeConfiguration
    private let callerUID: uid_t

    init(configuration: RuntimeConfiguration, callerUID: uid_t) {
        self.configuration = configuration
        self.callerUID = callerUID
        super.init()
    }

    func installRustDesk(
        artifactPath: String,
        signedEnvelope: Data,
        withReply reply: @escaping (Bool, String?) -> Void
    ) {
        Self.registerRequest()
        Self.queue.async { [configuration, callerUID] in
            defer { Self.finishRequest() }
            do {
                guard artifactPath.utf8.count <= 1_024,
                      signedEnvelope.count <= 131_072 else {
                    throw SupportError.helperRejected("installation request is too large")
                }

                let artifactURL = URL(fileURLWithPath: artifactPath, isDirectory: false)
                let manifest = try SignedManifestVerifier(
                    configuration: configuration
                ).verify(envelopeData: signedEnvelope)

                try RustDeskInstaller(configuration: configuration).install(
                    artifactURL: artifactURL,
                    manifest: manifest,
                    callerUID: callerUID
                )
                reply(true, nil)
            } catch {
                // Return only a bounded user-facing description. Tokens and paths are never logged.
                let message = (error as? SupportError)?.errorDescription
                    ?? "The verified installation could not be completed."
                reply(false, String(message.prefix(500)))
            }
        }
    }

    private static func registerRequest() {
        activityLock.lock()
        pendingRequests += 1
        idleGeneration &+= 1
        activityLock.unlock()
    }

    private static func finishRequest() {
        activityLock.lock()
        pendingRequests -= 1
        idleGeneration &+= 1
        let generation = idleGeneration
        let shouldArm = pendingRequests == 0
        activityLock.unlock()

        guard shouldArm else { return }
        DispatchQueue.global().asyncAfter(deadline: .now() + 5) {
            activityLock.lock()
            let isStillIdle = pendingRequests == 0 && idleGeneration == generation
            activityLock.unlock()
            if isStillIdle {
                // launchd starts a fresh authenticated helper for a future request.
                _exit(EXIT_SUCCESS)
            }
        }
    }
}
