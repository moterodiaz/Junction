import Foundation

/// What the lens should show. The DAT adapter turns this into one FlexBox.
/// `send()` replaces the whole 600×600 display, so each value is a full layout.
public enum LensContent: Equatable, Sendable {
    case status(headline: String, detail: String)
    case card(title: String, caption: String, imageURL: URL?)
    case failure(message: String)
}

public enum LensCopy {
    public static func content(for stage: PipelineStage) -> LensContent {
        switch stage {
        case .transcribing:
            return .status(headline: "Listening", detail: "One frame, only because you asked.")
        case .reading:
            return .status(headline: "Reading page", detail: "Finding the passage.")
        case .thinking:
            return .status(headline: "Thinking", detail: "Using what you already asked.")
        case .drawing:
            return .status(headline: "Drawing", detail: "Making a picture for the lens.")
        }
    }

    public static func content(for card: CardMessage) -> LensContent {
        .card(
            title: card.title,
            caption: card.caption,
            imageURL: lensImageURL(card.imageURL)
        )
    }

    public static func content(for failure: FailureKind) -> LensContent {
        .failure(message: FailurePolicy.recovery(for: failure, retryable: true).banner)
    }

    /// The lens `Image` component loads from a URL. Only https is usable.
    /// A missing image (billing off, or a non-https URL) becomes a text card.
    public static func lensImageURL(_ raw: String?) -> URL? {
        guard let raw, let url = URL(string: raw), url.scheme?.lowercased() == "https" else {
            return nil
        }
        return url
    }
}
