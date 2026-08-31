import Foundation

@objc public protocol RustDeskInstallHelperProtocol: NSObjectProtocol {
    func installRustDesk(
        artifactPath: String,
        signedEnvelope: Data,
        withReply reply: @escaping (Bool, String?) -> Void
    )
}

public enum HelperServiceConstants {
    public static let machServiceName = "com.sinbarconsultants.supportassistant.installhelper"
    public static let installedRustDeskURL = URL(
        fileURLWithPath: "/Applications/RustDesk.app",
        isDirectory: true
    )
}
