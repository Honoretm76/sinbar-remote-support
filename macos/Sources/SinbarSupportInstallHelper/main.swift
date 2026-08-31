import Darwin
import Foundation
import SinbarSupportCore

guard let configuration = try? RuntimeConfiguration.loadInstalled() else {
    exit(EXIT_FAILURE)
}
let delegate = InstallHelperListenerDelegate(configuration: configuration)
let listener = NSXPCListener(
    machServiceName: HelperServiceConstants.machServiceName
)
listener.delegate = delegate
listener.setConnectionCodeSigningRequirement(
    configuration.assistantCodeSigningRequirement
)
listener.resume()
dispatchMain()
