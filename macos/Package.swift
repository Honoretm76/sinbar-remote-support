// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "SinbarSupportAssistant",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(
            name: "SinbarSupportAssistant",
            targets: ["SinbarSupportAssistant"]
        ),
        .executable(
            name: "SinbarSupportInstallHelper",
            targets: ["SinbarSupportInstallHelper"]
        ),
    ],
    targets: [
        .target(
            name: "SinbarSupportCore",
            path: "Sources/SinbarSupportCore"
        ),
        .executableTarget(
            name: "SinbarSupportAssistant",
            dependencies: ["SinbarSupportCore"],
            path: "Sources/SinbarSupportAssistant"
        ),
        .executableTarget(
            name: "SinbarSupportInstallHelper",
            dependencies: ["SinbarSupportCore"],
            path: "Sources/SinbarSupportInstallHelper"
        ),
        .testTarget(
            name: "SinbarSupportCoreTests",
            dependencies: ["SinbarSupportCore"],
            path: "Tests/SinbarSupportCoreTests"
        ),
    ]
)
