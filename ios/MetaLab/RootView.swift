import SwiftUI
import MetaLabCore

struct RootView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    header
                    if let configureError = model.configureError {
                        bannerView(configureError)
                    }
                    if let banner = model.session.banner {
                        bannerView(banner)
                    }
                    lensPanel
                    if let card = model.session.lastCard {
                        phoneCard(card)
                    }
                    controls
                }
                .padding(20)
            }
        }
        .preferredColorScheme(.dark)
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 4) {
                Text("MetaLab")
                    .font(.system(size: 34, weight: .semibold, design: .serif))
                    .foregroundStyle(.white)
                Text(linkLabel)
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.7))
            }
            Spacer()
            Text(phaseLabel)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.black)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.accentColor, in: Capsule())
        }
        .accessibilityElement(children: .combine)
    }

    private var lensPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.session.displayEnabled ? "Lens" : "Lens off · answer by voice")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white.opacity(0.55))
                .textCase(.uppercase)
            lensBody
                .frame(maxWidth: .infinity, minHeight: 280)
                .padding(20)
                .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 20))
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(Color.white.opacity(0.12), lineWidth: 1)
                )
        }
    }

    @ViewBuilder
    private var lensBody: some View {
        switch model.lens {
        case .status(let headline, let detail):
            VStack(alignment: .leading, spacing: 8) {
                Text(headline)
                    .font(.system(size: 28, weight: .semibold, design: .serif))
                Text(detail)
                    .foregroundStyle(.white.opacity(0.72))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        case .failure(let message):
            Text(message)
                .font(.body)
                .frame(maxWidth: .infinity, alignment: .leading)
        case .card(let title, let caption, let imageURL):
            VStack(alignment: .leading, spacing: 10) {
                if let imageURL {
                    AsyncImage(url: imageURL) { phase in
                        switch phase {
                        case .success(let image):
                            image.resizable().scaledToFit()
                        default:
                            Color.white.opacity(0.06)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 180)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                Text(title)
                    .font(.system(size: 22, weight: .semibold, design: .serif))
                Text(caption)
                    .foregroundStyle(.white.opacity(0.8))
            }
        }
    }

    private func phoneCard(_ card: CardMessage) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("On this phone")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white.opacity(0.55))
                .textCase(.uppercase)
            Text(card.title)
                .font(.headline)
            Text(card.caption)
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.75))
            if let book = card.book {
                Text("\(book.title) · \(book.location)")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.55))
            }
            if !card.models.reason.isEmpty || !card.models.image.isEmpty {
                Text(modelLine(card.models))
                    .font(.caption.monospaced())
                    .foregroundStyle(.white.opacity(0.45))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 16))
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 14) {
            if !model.session.registered {
                actionButton("Register in Meta AI", systemImage: "link") {
                    Task { await model.register() }
                }
            } else if !model.session.permissionGranted {
                actionButton("Allow camera", systemImage: "camera") {
                    Task { await model.allowCamera() }
                }
            }

            if model.session.needsNewSession || model.session.link == .stopped {
                actionButton("Reconnect", systemImage: "arrow.clockwise") {
                    Task { await model.reconnect() }
                }
            }

            actionButton(askTitle, systemImage: "text.book.closed") {
                model.invoke()
            }
            .disabled(!model.session.canInvoke || model.phase != .idle)
            .opacity(model.session.canInvoke && model.phase == .idle ? 1 : 0.45)

            if let reason = model.blockedReason, model.phase == .idle {
                Text(reason)
                    .font(.footnote)
                    .foregroundStyle(.white.opacity(0.7))
            }

            TextField("Typed command, optional", text: $model.typedCommand)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(12)
                .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
                .accessibilityLabel("Typed command instead of the microphone")

            TextField("Backend WebSocket", text: $model.backendURL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .keyboardType(.URL)
                .padding(12)
                .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
                .accessibilityLabel("Backend WebSocket URL")

            Toggle("Show the lens", isOn: displayBinding)
            Toggle("High-quality photo fallback", isOn: $model.useStandalonePhoto)
            Toggle("Keep a sample frame for the reading test", isOn: $model.keepSampleFrames)
            if let url = model.sampleFrameURL {
                Text(url.lastPathComponent)
                    .font(.caption.monospaced())
                    .foregroundStyle(.white.opacity(0.5))
            }

            Button("New book") { model.newBook() }
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.white.opacity(0.7))
        }
        .tint(.accentColor)
    }

    private func bannerView(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text(text)
                .font(.subheadline)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let title = model.session.actionTitle, model.session.action != .none, model.session.action != .waitForResume {
                Button(title) { perform(model.session.action) }
                    .font(.subheadline.weight(.semibold))
                    .buttonStyle(.borderedProminent)
            }
        }
        .padding(14)
        .background(Color.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 14))
        .accessibilityElement(children: .combine)
    }

    private func actionButton(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.body.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
    }

    private var displayBinding: Binding<Bool> {
        Binding(
            get: { model.session.displayEnabled },
            set: { model.setDisplayEnabled($0) }
        )
    }

    private var askTitle: String {
        switch model.phase {
        case .idle: "Ask about this page"
        case .capturing: "Capturing"
        case .waiting: "Working"
        case .speaking: "Speaking"
        }
    }

    private var phaseLabel: String {
        switch model.phase {
        case .idle: model.session.link == .started ? "Ready" : "Idle"
        case .capturing: "Capturing"
        case .waiting: "Working"
        case .speaking: "Speaking"
        }
    }

    private var linkLabel: String {
        switch model.session.link {
        case .idle: "Glasses idle"
        case .starting: "Connecting"
        case .started: "Glasses connected"
        case .paused: "Glasses paused"
        case .stopping: "Disconnecting"
        case .stopped: "Glasses stopped"
        }
    }

    private func modelLine(_ models: ModelTrace) -> String {
        let reason = models.reason.isEmpty ? "reasoning pending" : models.reason
        let image = models.image.isEmpty ? "image pending" : models.image
        return "\(reason) · \(image)"
    }

    private func perform(_ action: RecoveryAction) {
        switch action {
        case .requestPermission:
            Task { await model.allowCamera() }
        case .openSettings:
            if let url = URL(string: UIApplication.openSettingsURLString) {
                UIApplication.shared.open(url)
            }
        case .startNewSession:
            Task { await model.reconnect() }
        case .retryInvoke:
            model.invoke()
        case .waitForResume, .none:
            break
        }
    }
}
