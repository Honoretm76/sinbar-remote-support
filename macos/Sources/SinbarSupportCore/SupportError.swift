import Foundation

public enum SupportError: LocalizedError, Equatable {
    case invalidConfiguration(String)
    case invalidLaunchURL
    case invalidToken
    case networkFailure(String)
    case invalidServerResponse(String)
    case invalidSignature
    case rejectedManifest(String)
    case artifactFailure(String)
    case codeSignatureFailure(String)
    case installationFailure(String)
    case helperUnavailable
    case helperRejected(String)
    case userCancelled

    public var errorDescription: String? {
        switch self {
        case .invalidConfiguration(let detail):
            return "The Sinbar Support Assistant is not configured correctly: \(detail)"
        case .invalidLaunchURL:
            return "This support link is not valid. Return to support.sinbarconsultants.com and start again."
        case .invalidToken:
            return "This support link is malformed or has expired. Start a new support request."
        case .networkFailure(let detail):
            return "The secure support service could not be reached: \(detail)"
        case .invalidServerResponse(let detail):
            return "The support service returned an invalid response: \(detail)"
        case .invalidSignature:
            return "The support instructions could not be authenticated. Nothing was installed."
        case .rejectedManifest(let detail):
            return "The support instructions were rejected: \(detail)"
        case .artifactFailure(let detail):
            return "The RustDesk installer could not be verified: \(detail)"
        case .codeSignatureFailure(let detail):
            return "RustDesk publisher verification failed: \(detail)"
        case .installationFailure(let detail):
            return "RustDesk could not be installed: \(detail)"
        case .helperUnavailable:
            return "The signed Sinbar installation helper is unavailable. Reinstall the Sinbar Support Assistant."
        case .helperRejected(let detail):
            return "The installation helper rejected the request: \(detail)"
        case .userCancelled:
            return "Remote support was cancelled. Nothing was installed or opened."
        }
    }
}
