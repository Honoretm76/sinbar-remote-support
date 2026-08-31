import AppKit
import SinbarSupportCore

@MainActor
final class StatusWindowController: NSWindowController {
    private let heading = NSTextField(labelWithString: "Sinbar Remote Support")
    private let status = NSTextField(labelWithString: "Preparing secure support…")
    private let progress = NSProgressIndicator()

    convenience init() {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 250),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        self.init(window: window)
        configureWindow()
    }

    private func configureWindow() {
        guard let window, let content = window.contentView else { return }
        window.title = "Sinbar Support Assistant"
        window.isReleasedWhenClosed = false
        window.center()
        content.wantsLayer = true
        content.layer?.backgroundColor = NSColor(
            calibratedWhite: 0.045,
            alpha: 1
        ).cgColor

        heading.translatesAutoresizingMaskIntoConstraints = false
        heading.font = .systemFont(ofSize: 26, weight: .semibold)
        heading.textColor = NSColor(
            calibratedRed: 0.79,
            green: 0.66,
            blue: 0.30,
            alpha: 1
        )

        status.translatesAutoresizingMaskIntoConstraints = false
        status.font = .systemFont(ofSize: 15)
        status.textColor = .white
        status.maximumNumberOfLines = 3
        status.lineBreakMode = .byWordWrapping
        status.alignment = .center

        progress.translatesAutoresizingMaskIntoConstraints = false
        progress.style = .spinning
        progress.controlSize = .regular
        progress.startAnimation(nil)

        content.addSubview(heading)
        content.addSubview(status)
        content.addSubview(progress)
        NSLayoutConstraint.activate([
            heading.topAnchor.constraint(equalTo: content.topAnchor, constant: 42),
            heading.centerXAnchor.constraint(equalTo: content.centerXAnchor),
            status.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 42),
            status.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -42),
            status.topAnchor.constraint(equalTo: heading.bottomAnchor, constant: 30),
            progress.centerXAnchor.constraint(equalTo: content.centerXAnchor),
            progress.topAnchor.constraint(equalTo: status.bottomAnchor, constant: 25),
        ])
    }

    func showWaitingForPortal() {
        progress.stopAnimation(nil)
        progress.isHidden = true
        status.stringValue = "Return to support.sinbarconsultants.com and click Start Remote Support."
    }

    func showStatus(_ message: String) {
        progress.isHidden = false
        progress.startAnimation(nil)
        status.textColor = .white
        status.stringValue = message
    }

    func showSuccess() {
        progress.stopAnimation(nil)
        progress.isHidden = true
        status.textColor = NSColor.systemGreen
        status.stringValue = "RustDesk is open. Share the displayed ID only with your Sinbar technician."
    }

    func requestConsent(rustDeskVersion: String) -> Bool {
        progress.stopAnimation(nil)
        progress.isHidden = true

        let alert = NSAlert()
        alert.alertStyle = .informational
        alert.messageText = "Start attended Sinbar remote support?"
        alert.informativeText = "Sinbar verified this one-time request and RustDesk \(rustDeskVersion). Continuing may install RustDesk and will open it so you can choose what to share with your technician. No permanent password or unattended access will be enabled."
        alert.addButton(withTitle: "Cancel")
        alert.addButton(withTitle: "Continue")
        // Fail safe: Return selects Cancel. Continue has no key equivalent and
        // therefore requires a deliberate button selection.
        alert.buttons.first?.keyEquivalent = "\r"
        alert.buttons.last?.keyEquivalent = ""
        NSApp.activate(ignoringOtherApps: true)

        // NSButton has one key equivalent, so handle Escape at the modal event
        // boundary while retaining Return as the fail-safe default.
        let escapeMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 {
                NSApp.abortModal()
                return nil
            }
            return event
        }
        defer {
            if let escapeMonitor {
                NSEvent.removeMonitor(escapeMonitor)
            }
            alert.window.orderOut(nil)
        }
        return alert.runModal() == .alertSecondButtonReturn
    }

    func showFailure(_ error: Error) {
        progress.stopAnimation(nil)
        progress.isHidden = true
        status.textColor = NSColor.systemRed
        status.stringValue = (error as? SupportError)?.errorDescription
            ?? "Remote support could not be started. No permanent access was enabled."
    }
}
