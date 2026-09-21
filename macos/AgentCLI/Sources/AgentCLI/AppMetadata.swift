import Foundation

struct SparkleConfiguration: Equatable {
    let feedURL: String
    let publicEDKey: String

    var isConfigured: Bool {
        !feedURL.isEmpty && !publicEDKey.isEmpty
    }
}

enum AppMetadata {
    static var versionDisplayString: String {
        versionDisplayString(infoDictionary: Bundle.main.infoDictionary ?? [:])
    }

    static var sparkleConfiguration: SparkleConfiguration {
        sparkleConfiguration(infoDictionary: Bundle.main.infoDictionary ?? [:])
    }

    static func versionDisplayString(infoDictionary: [String: Any]) -> String {
        let shortVersion = stringValue(
            infoDictionary["CFBundleShortVersionString"],
            fallback: "Unknown"
        )
        let buildVersion = stringValue(infoDictionary["CFBundleVersion"])

        guard !buildVersion.isEmpty, buildVersion != shortVersion else {
            return shortVersion
        }
        return "\(shortVersion) (\(buildVersion))"
    }

    static func sparkleConfiguration(infoDictionary: [String: Any]) -> SparkleConfiguration {
        SparkleConfiguration(
            feedURL: stringValue(infoDictionary["SUFeedURL"]),
            publicEDKey: stringValue(infoDictionary["SUPublicEDKey"])
        )
    }

    private static func stringValue(_ value: Any?, fallback: String = "") -> String {
        guard let string = value as? String else { return fallback }
        let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? fallback : trimmed
    }
}
