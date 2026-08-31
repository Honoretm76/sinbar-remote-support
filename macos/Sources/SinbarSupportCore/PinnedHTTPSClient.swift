import Foundation

public final class RejectRedirectsDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    public func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }
}

public final class PinnedHTTPSClient: @unchecked Sendable {
    private let configuration: RuntimeConfiguration
    private let session: URLSession
    private let delegate: RejectRedirectsDelegate

    public init(configuration: RuntimeConfiguration) {
        self.configuration = configuration
        self.delegate = RejectRedirectsDelegate()

        let sessionConfiguration = URLSessionConfiguration.ephemeral
        sessionConfiguration.timeoutIntervalForRequest = 20
        sessionConfiguration.timeoutIntervalForResource = 600
        sessionConfiguration.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        sessionConfiguration.urlCache = nil
        sessionConfiguration.httpCookieStorage = nil
        sessionConfiguration.httpShouldSetCookies = false
        sessionConfiguration.waitsForConnectivity = false
        self.session = URLSession(
            configuration: sessionConfiguration,
            delegate: delegate,
            delegateQueue: nil
        )
    }

    public func consume(token: String) async throws -> Data {
        guard configuration.apiBaseURL.absoluteString ==
                "https://support.sinbarconsultants.com",
              let endpoint = URL(
                string: "https://support.sinbarconsultants.com/api/v1/support/sessions/consume"
              ) else {
            throw SupportError.invalidConfiguration("consume endpoint is not pinned")
        }

        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(
            "SinbarSupportAssistant/\(configuration.assistantVersion) macOS",
            forHTTPHeaderField: "User-Agent"
        )
        request.httpBody = try JSONEncoder().encode(
            ConsumeRequest(
                token: token,
                architecture: .current,
                assistantVersion: configuration.assistantVersion
            )
        )

        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  http.statusCode == 200 else {
                throw SupportError.networkFailure("the one-time support request was refused")
            }
            guard data.count <= 131_072 else {
                throw SupportError.invalidServerResponse("signed manifest is too large")
            }
            let contentType = http.value(forHTTPHeaderField: "Content-Type")?.lowercased() ?? ""
            guard contentType.hasPrefix("application/json") else {
                throw SupportError.invalidServerResponse("unexpected response content type")
            }
            return data
        } catch let error as SupportError {
            throw error
        } catch {
            throw SupportError.networkFailure("request failed without exposing session details")
        }
    }

    public func downloadArtifact(from url: URL) async throws -> StagedArtifact {
        let stagingRoot = try StagedArtifact.makePrivateStagingDirectory()
        let partialURL = stagingRoot.appendingPathComponent("artifact.part", isDirectory: false)
        let finalURL = stagingRoot.appendingPathComponent(
            "artifact.\(url.pathExtension.lowercased())",
            isDirectory: false
        )

        do {
            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            request.setValue("application/octet-stream", forHTTPHeaderField: "Accept")
            request.setValue(
                "SinbarSupportAssistant/\(configuration.assistantVersion) macOS",
                forHTTPHeaderField: "User-Agent"
            )

            let (temporaryURL, response) = try await session.download(for: request)
            guard let http = response as? HTTPURLResponse,
                  http.statusCode == 200,
                  response.url == url else {
                throw SupportError.artifactFailure("download did not remain on the approved URL")
            }

            if http.expectedContentLength > configuration.maximumArtifactBytes {
                throw SupportError.artifactFailure("artifact exceeds the configured size limit")
            }

            try FileManager.default.moveItem(at: temporaryURL, to: partialURL)
            try FileManager.default.setAttributes(
                [.posixPermissions: NSNumber(value: Int16(0o600))],
                ofItemAtPath: partialURL.path
            )

            let attributes = try FileManager.default.attributesOfItem(atPath: partialURL.path)
            let size = (attributes[.size] as? NSNumber)?.int64Value ?? -1
            let type = attributes[.type] as? FileAttributeType
            guard type == .typeRegular,
                  size > 0,
                  size <= configuration.maximumArtifactBytes else {
                throw SupportError.artifactFailure("downloaded artifact is not an approved regular file")
            }

            try FileManager.default.moveItem(at: partialURL, to: finalURL)
            return StagedArtifact(rootURL: stagingRoot, fileURL: finalURL, byteCount: size)
        } catch let error as SupportError {
            try? FileManager.default.removeItem(at: stagingRoot)
            throw error
        } catch {
            try? FileManager.default.removeItem(at: stagingRoot)
            throw SupportError.artifactFailure("secure download failed")
        }
    }
}
