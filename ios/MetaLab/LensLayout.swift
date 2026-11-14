import MWDATDisplay
import MetaLabCore

enum LensLayout {
    /// One full layout. `Display.send` replaces the 600×600 lens; there is no partial update.
    /// Bright text on the default (black) field, because dark pixels disappear on the additive display.
    static func make(_ content: LensContent) -> FlexBox {
        switch content {
        case .status(let headline, let detail):
            return FlexBox(direction: .column, spacing: 16, alignment: .center, crossAlignment: .center, padding: EdgeInsets(all: 28)) {
                Text(headline, style: .heading)
                Text(detail, style: .body, color: .secondary)
            }
        case .failure(let message):
            return FlexBox(direction: .column, spacing: 12, padding: EdgeInsets(all: 28)) {
                Text("Try again", style: .heading)
                Text(message, style: .body)
            }
        case .card(let title, let caption, let imageURL):
            if let imageURL {
                return FlexBox(direction: .column, spacing: 10, padding: EdgeInsets(all: 16)) {
                    Image(uri: imageURL.absoluteString, sizePreset: .fill, cornerRadius: .small)
                        .flexGrow(1)
                    Text(title, style: .heading)
                    Text(caption, style: .body, color: .secondary)
                }
            }
            return FlexBox(direction: .column, spacing: 12, padding: EdgeInsets(all: 28)) {
                Text(title, style: .heading)
                Text(caption, style: .body)
            }
        }
    }
}
