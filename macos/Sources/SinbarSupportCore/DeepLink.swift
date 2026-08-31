import Foundation

public struct SupportLaunch: Sendable, Equatable {
    public let token: String

    public init(url: URL) throws {
        guard url.absoluteString.utf8.count <= 512,
              url.scheme?.lowercased() == "sinbarsupport",
              url.host?.lowercased() == "start",
              url.path.isEmpty,
              url.user == nil,
              url.password == nil,
              url.port == nil,
              url.fragment == nil,
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let queryItems = components.queryItems,
              queryItems.count == 1,
              queryItems[0].name == "token",
              let token = queryItems[0].value,
              components.percentEncodedQuery == "token=\(token)" else {
            throw SupportError.invalidLaunchURL
        }

        guard token.range(of: "^[A-Za-z0-9_-]{43}$", options: .regularExpression) != nil,
              let tokenData = try? Base64URL.decode(token, maximumCharacters: 43),
              tokenData.count == 32,
              Base64URL.encode(tokenData) == token else {
            throw SupportError.invalidToken
        }
        self.token = token
    }
}
