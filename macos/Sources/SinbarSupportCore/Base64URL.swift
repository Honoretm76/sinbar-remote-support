import Foundation

public enum Base64URL {
    private static let allowed = CharacterSet(
        charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )

    public static func decode(_ value: String, maximumCharacters: Int = 131_072) throws -> Data {
        guard !value.isEmpty,
              value.utf8.count <= maximumCharacters,
              value.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
            throw SupportError.invalidServerResponse("invalid base64url value")
        }

        var base64 = value
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")

        let remainder = base64.utf8.count % 4
        if remainder != 0 {
            base64.append(String(repeating: "=", count: 4 - remainder))
        }

        guard let decoded = Data(base64Encoded: base64, options: []) else {
            throw SupportError.invalidServerResponse("invalid base64url encoding")
        }
        guard encode(decoded) == value else {
            throw SupportError.invalidServerResponse("base64url value is not canonical")
        }
        return decoded
    }

    public static func encode(_ data: Data) -> String {
        data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}
