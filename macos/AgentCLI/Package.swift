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
        .package(url: "https://github.com/sindresorhus/KeyboardShortcuts", exact: "1.10.0"),
        .package(url: "https://github.com/sparkle-project/Sparkle", exact: "2.9.2"),
    ],
    targets: [
        .executableTarget(
            name: "AgentCLI",
            dependencies: [
                .product(name: "KeyboardShortcuts", package: "KeyboardShortcuts"),
                .product(name: "Sparkle", package: "Sparkle"),
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
