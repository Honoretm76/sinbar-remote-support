import Darwin
import Foundation

public enum FileSecurity {
    public struct RootStagedCopy {
        public let rootURL: URL
        public let fileURL: URL

        public func remove() {
            try? FileManager.default.removeItem(at: rootURL)
        }
    }

    public static func validateDownloadedArtifact(
        at url: URL,
        callerUID: uid_t,
        maximumBytes: Int64
    ) throws {
        var fileStatus = stat()
        guard lstat(url.path, &fileStatus) == 0,
              (fileStatus.st_mode & S_IFMT) == S_IFREG,
              fileStatus.st_uid == callerUID,
              (fileStatus.st_mode & 0o077) == 0,
              fileStatus.st_size > 0,
              fileStatus.st_size <= maximumBytes else {
            throw SupportError.helperRejected("artifact permissions, ownership, or size are invalid")
        }

        guard let user = getpwuid(callerUID),
              let homeCString = user.pointee.pw_dir else {
            throw SupportError.helperRejected("calling user cannot be resolved")
        }
        let home = String(cString: homeCString)
        let approvedPrefix = URL(fileURLWithPath: home, isDirectory: true)
            .appendingPathComponent("Library/Caches", isDirectory: true)
            .appendingPathComponent(StagedArtifact.cacheIdentifier, isDirectory: true)
            .appendingPathComponent("Incoming", isDirectory: true)
            .standardizedFileURL.path + "/"

        let canonical = url.resolvingSymlinksInPath().standardizedFileURL.path
        guard canonical.hasPrefix(approvedPrefix) else {
            throw SupportError.helperRejected("artifact path is outside the private Sinbar cache")
        }

        let stagingDirectory = url.deletingLastPathComponent()
        var directoryStatus = stat()
        guard lstat(stagingDirectory.path, &directoryStatus) == 0,
              (directoryStatus.st_mode & S_IFMT) == S_IFDIR,
              directoryStatus.st_uid == callerUID,
              (directoryStatus.st_mode & 0o077) == 0 else {
            throw SupportError.helperRejected("artifact staging directory is not private")
        }
    }

    public static func copyToRootOwnedStaging(
        sourceURL: URL,
        callerUID: uid_t,
        maximumBytes: Int64,
        fileExtension: String
    ) throws -> RootStagedCopy {
        guard fileExtension == "dmg" || fileExtension == "pkg" else {
            throw SupportError.helperRejected("artifact extension is not approved")
        }

        let sourceDescriptor = open(sourceURL.path, O_RDONLY | O_NOFOLLOW)
        guard sourceDescriptor >= 0 else {
            throw SupportError.helperRejected("artifact could not be opened securely")
        }
        defer { close(sourceDescriptor) }

        var openedStatus = stat()
        guard fstat(sourceDescriptor, &openedStatus) == 0,
              (openedStatus.st_mode & S_IFMT) == S_IFREG,
              openedStatus.st_uid == callerUID,
              (openedStatus.st_mode & 0o077) == 0,
              openedStatus.st_size > 0,
              openedStatus.st_size <= maximumBytes else {
            throw SupportError.helperRejected("opened artifact changed or is not approved")
        }

        let rootURL = URL(
            fileURLWithPath: "/private/var/tmp/com.sinbarconsultants.supportassistant.artifact.\(UUID().uuidString)",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: rootURL,
            withIntermediateDirectories: false,
            attributes: [.posixPermissions: NSNumber(value: Int16(0o700))]
        )

        let destinationURL = rootURL.appendingPathComponent(
            "artifact.\(fileExtension)",
            isDirectory: false
        )
        let destinationDescriptor = open(
            destinationURL.path,
            O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW,
            S_IRUSR | S_IWUSR
        )
        guard destinationDescriptor >= 0 else {
            try? FileManager.default.removeItem(at: rootURL)
            throw SupportError.helperRejected("root-owned artifact staging failed")
        }
        defer { close(destinationDescriptor) }

        do {
            var buffer = [UInt8](repeating: 0, count: 1_048_576)
            var copied: Int64 = 0
            while true {
                let readCount = read(sourceDescriptor, &buffer, buffer.count)
                if readCount == 0 { break }
                guard readCount > 0 else {
                    throw SupportError.helperRejected("artifact read failed")
                }

                var written = 0
                while written < readCount {
                    let result = buffer.withUnsafeBytes { bytes -> Int in
                        guard let base = bytes.baseAddress else { return -1 }
                        return write(
                            destinationDescriptor,
                            base.advanced(by: written),
                            readCount - written
                        )
                    }
                    guard result > 0 else {
                        throw SupportError.helperRejected("artifact staging write failed")
                    }
                    written += result
                }
                copied += Int64(readCount)
                guard copied <= maximumBytes else {
                    throw SupportError.helperRejected("artifact changed size during staging")
                }
            }

            guard copied == openedStatus.st_size,
                  fsync(destinationDescriptor) == 0 else {
                throw SupportError.helperRejected("artifact staging did not complete")
            }
            return RootStagedCopy(rootURL: rootURL, fileURL: destinationURL)
        } catch {
            try? FileManager.default.removeItem(at: rootURL)
            throw error
        }
    }
}
