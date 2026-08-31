import Foundation

public enum SystemTool: String, Sendable {
    case hdiutil = "/usr/bin/hdiutil"
    case spctl = "/usr/sbin/spctl"
    case ditto = "/usr/bin/ditto"
    case pkgutil = "/usr/sbin/pkgutil"
    case installer = "/usr/sbin/installer"
}

public struct ToolResult: Sendable, Equatable {
    public let exitCode: Int32
    public let output: String
}

public enum SystemToolRunner {
    @discardableResult
    public static func run(
        _ tool: SystemTool,
        arguments: [String],
        maximumOutputBytes: Int = 65_536
    ) throws -> ToolResult {
        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: tool.rawValue)
        process.arguments = arguments
        process.environment = [
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C",
            "LC_ALL": "C",
        ]
        process.standardOutput = pipe
        process.standardError = pipe

        do {
            try process.run()
        } catch {
            throw SupportError.installationFailure("an approved system utility could not start")
        }

        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let bounded = data.prefix(maximumOutputBytes)
        return ToolResult(
            exitCode: process.terminationStatus,
            output: String(decoding: bounded, as: UTF8.self)
        )
    }
}
