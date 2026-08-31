import Foundation
import XCTest
@testable import SinbarSupportCore

final class DeepLinkTests: XCTestCase {
    private let token = String(repeating: "A", count: 43)

    func testAcceptsExactCanonicalLaunchURL() throws {
        let url = try XCTUnwrap(URL(string: "sinbarsupport://start?token=\(token)"))
        XCTAssertEqual(try SupportLaunch(url: url).token, token)
    }

    func testRejectsUnknownAndDuplicateParameters() throws {
        let urls = [
            "sinbarsupport://start?token=\(token)&origin=https://support.sinbarconsultants.com",
            "sinbarsupport://start?token=\(token)&token=\(token)",
            "sinbarsupport://start?other=\(token)",
        ]
        for value in urls {
            XCTAssertThrowsError(try SupportLaunch(url: XCTUnwrap(URL(string: value))))
        }
    }

    func testRejectsAuthorityFragmentPathPortAndEncodedToken() throws {
        let urls = [
            "sinbarsupport://user@start?token=\(token)",
            "sinbarsupport://start:443?token=\(token)",
            "sinbarsupport://start/path?token=\(token)",
            "sinbarsupport://start?token=\(token)#fragment",
            "sinbarsupport://start?token=%41\(String(repeating: "A", count: 42))",
        ]
        for value in urls {
            XCTAssertThrowsError(try SupportLaunch(url: XCTUnwrap(URL(string: value))))
        }
    }

    func testRejectsMalformedTokens() throws {
        for malformed in ["", "short", String(repeating: "A", count: 44), String(repeating: "=", count: 43)] {
            XCTAssertThrowsError(
                try SupportLaunch(
                    url: XCTUnwrap(URL(string: "sinbarsupport://start?token=\(malformed)"))
                )
            )
        }
    }
}
