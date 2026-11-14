// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "MetaLabCore",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        .library(name: "MetaLabCore", targets: ["MetaLabCore"]),
    ],
    targets: [
        .target(name: "MetaLabCore"),
        .testTarget(
            name: "MetaLabCoreTests",
            dependencies: ["MetaLabCore"]
        ),
    ]
)
