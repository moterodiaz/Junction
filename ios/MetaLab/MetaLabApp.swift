import SwiftUI

@main
struct MetaLabApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView(model: model)
                .onOpenURL { url in
                    Task { await model.handle(url: url) }
                }
        }
    }
}
