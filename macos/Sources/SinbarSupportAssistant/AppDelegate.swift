import AppKit
import Foundation
import SinbarSupportCore

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let windowController = StatusWindowController()
    private var coordinator: SupportCoordinator?
    private var started = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        windowController.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.75) { [weak self] in
            guard let self, !self.started else { return }
            self.windowController.showWaitingForPortal()
        }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        guard urls.count == 1, let url = urls.first else {
            windowController.showFailure(SupportError.invalidLaunchURL)
            return
        }
        begin(url: url)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }

    private func begin(url: URL) {
        guard !started else { return }
        started = true

        do {
            let configuration = try RuntimeConfiguration.loadInstalled()
            let launch = try SupportLaunch(url: url)
            let coordinator = SupportCoordinator(
                configuration: configuration,
                status: { [weak windowController = self.windowController] message in
                    Task { @MainActor in
                        windowController?.showStatus(message)
                    }
                },
                consent: { [weak windowController = self.windowController] manifest in
                    windowController?.requestConsent(
                        rustDeskVersion: manifest.artifact.version
                    ) ?? false
                }
            )
            self.coordinator = coordinator

            Task {
                do {
                    try await coordinator.run(launch: launch)
                    await MainActor.run {
                        self.windowController.showSuccess()
                    }
                    try? await Task.sleep(for: .seconds(1))
                    await MainActor.run { NSApp.terminate(nil) }
                } catch {
                    await MainActor.run {
                        if (error as? SupportError) == .userCancelled {
                            NSApp.terminate(nil)
                        } else {
                            self.windowController.showFailure(error)
                        }
                    }
                }
            }
        } catch {
            windowController.showFailure(error)
        }
    }
}
