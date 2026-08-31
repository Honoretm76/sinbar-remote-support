import Darwin
import Foundation
import SinbarSupportCore

final class InstallHelperListenerDelegate: NSObject, NSXPCListenerDelegate {
    private let configuration: RuntimeConfiguration

    init(configuration: RuntimeConfiguration) {
        self.configuration = configuration
        super.init()
    }

    func listener(
        _ listener: NSXPCListener,
        shouldAcceptNewConnection connection: NSXPCConnection
    ) -> Bool {
        let callerUID = connection.effectiveUserIdentifier
        guard callerUID >= 500 else {
            return false
        }

        let service = InstallHelperService(
            configuration: configuration,
            callerUID: callerUID
        )
        connection.exportedInterface = NSXPCInterface(
            with: RustDeskInstallHelperProtocol.self
        )
        connection.exportedObject = service
        connection.invalidationHandler = { _ = service }
        connection.interruptionHandler = { _ = service }
        connection.resume()
        return true
    }
}
