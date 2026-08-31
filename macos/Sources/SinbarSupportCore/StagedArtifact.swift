import CryptoKit
import Darwin
import Foundation

public struct StagedArtifact: Sendable {
    public static let cacheIdentifier = "com.sinbarconsultants.supportassistant"

    public let rootURL: URL
    public let fileURL: URL
    public let byteCount: Int64

    public func remove() {
        try? FileManager.default.removeItem(at: rootURL)
    }

    public func sha256() throws -> String {
        try FileDigest.sha256(at: fileURL)
    }

    public static func makePrivateStagingDirectory() throws -> URL {
        guard let caches = FileManager.default.urls(
            for: .cachesDirectory,
            in: .userDomainMask
        ).first else {
            throw SupportError.artifactFailure("user cache directory is unavailable")
        }

        let incoming = caches
            .appendingPathComponent(cacheIdentifier, isDirectory: true)
            .appendingPathComponent("Incoming", isDirectory: true)
        let root = incoming.appendingPathComponent(UUID().uuidString, isDirectory: true)

        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: Int16(0o700))]
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: Int16(0o700))],
            ofItemAtPath: incoming.path
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: Int16(0o700))],
            ofItemAtPath: root.path
        )
        return root
    }
}

public enum FileDigest {
    public static func sha256(at fileURL: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: fileURL)
        defer { try? handle.close() }

        var digest = SHA256()
        while true {
            let chunk = try handle.read(upToCount: 1_048_576) ?? Data()
            if chunk.isEmpty { break }
            digest.update(data: chunk)
        }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }
}
