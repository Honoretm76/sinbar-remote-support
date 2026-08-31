import Foundation

public enum StrictJSON {
    public static func object(
        from data: Data,
        exactKeys: Set<String>,
        context: String
    ) throws -> [String: Any] {
        let value = try JSONSerialization.jsonObject(with: data, options: [])
        guard let object = value as? [String: Any],
              Set(object.keys) == exactKeys else {
            throw SupportError.invalidServerResponse("unexpected \(context) fields")
        }
        return object
    }

    public static func nestedObject(
        _ value: Any?,
        exactKeys: Set<String>,
        context: String
    ) throws -> [String: Any] {
        guard let object = value as? [String: Any],
              Set(object.keys) == exactKeys else {
            throw SupportError.invalidServerResponse("unexpected \(context) fields")
        }
        return object
    }
}
