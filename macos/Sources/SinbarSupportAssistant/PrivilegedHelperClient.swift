import Foundation
import SinbarSupportCore

final class PrivilegedHelperClient: @unchecked Sendable {
    private let configuration: RuntimeConfiguration

    init(configuration: RuntimeConfiguration) {
        self.configuration = configuration
    }

    func install(artifactURL: URL, signedEnvelope: Data) async throws {
        try CodeSignatureVerifier.verifyInstalledHelper(configuration: configuration)

        try await withCheckedThrowingContinuation {
            (continuation: CheckedContinuation<Void, Error>) in
            let connection = NSXPCConnection(
                machServiceName: HelperServiceConstants.machServiceName,
                options: .privileged
            )
            connection.remoteObjectInterface = NSXPCInterface(
                with: RustDeskInstallHelperProtocol.self
            )
            connection.setCodeSigningRequirement(
                configuration.helperCodeSigningRequirement
            )

            let oneShot = OneShotContinuation(continuation: continuation) {
                connection.invalidate()
            }
            connection.interruptionHandler = {
                oneShot.fail(SupportError.helperUnavailable)
            }
            connection.invalidationHandler = {
                oneShot.fail(SupportError.helperUnavailable)
            }
            connection.resume()

            guard let helper = connection.remoteObjectProxyWithErrorHandler({ _ in
                oneShot.fail(SupportError.helperUnavailable)
            }) as? RustDeskInstallHelperProtocol else {
                oneShot.fail(SupportError.helperUnavailable)
                return
            }

            helper.installRustDesk(
                artifactPath: artifactURL.path,
                signedEnvelope: signedEnvelope
            ) { succeeded, message in
                if succeeded {
                    oneShot.succeed()
                } else {
                    oneShot.fail(
                        SupportError.helperRejected(
                            String((message ?? "verified install failed").prefix(500))
                        )
                    )
                }
            }

            DispatchQueue.global().asyncAfter(deadline: .now() + 180) {
                oneShot.fail(SupportError.helperUnavailable)
            }
        }
    }
}

private final class OneShotContinuation: @unchecked Sendable {
    private let lock = NSLock()
    private var completed = false
    private let continuation: CheckedContinuation<Void, Error>
    private let cleanup: () -> Void

    init(
        continuation: CheckedContinuation<Void, Error>,
        cleanup: @escaping () -> Void
    ) {
        self.continuation = continuation
        self.cleanup = cleanup
    }

    func succeed() {
        finish(.success(()))
    }

    func fail(_ error: Error) {
        finish(.failure(error))
    }

    private func finish(_ result: Result<Void, Error>) {
        lock.lock()
        guard !completed else {
            lock.unlock()
            return
        }
        completed = true
        lock.unlock()

        cleanup()
        switch result {
        case .success:
            continuation.resume()
        case .failure(let error):
            continuation.resume(throwing: error)
        }
    }
}
