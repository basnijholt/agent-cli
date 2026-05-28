// swift-tools-version: 5.9

import PackageDescription

let package = Package(
    name: "AgentCLI",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(name: "AgentCLI", targets: ["AgentCLI"]),
    ],
    dependencies: [
        .package(url: "https://github.com/sindresorhus/KeyboardShortcuts", exact: "2.4.0"),
    ],
    targets: [
        .executableTarget(
            name: "AgentCLI",
            dependencies: [
                .product(name: "KeyboardShortcuts", package: "KeyboardShortcuts"),
            ],
            path: "Sources/AgentCLI"
        ),
        .testTarget(
            name: "AgentCLITests",
            dependencies: ["AgentCLI"],
            path: "Tests/AgentCLITests"
        ),
    ]
)
