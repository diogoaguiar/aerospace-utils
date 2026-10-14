// Throwaway test windows for the live layout checks. Opens N windows titled
// probe-1..probe-N and keeps writing their frames to a JSON file.
// Usage: aeroprobe <count> <frames.json>

import AppKit

let count = Int(CommandLine.arguments[1]) ?? 4
let out = URL(fileURLWithPath: CommandLine.arguments[2])
let app = NSApplication.shared
app.setActivationPolicy(.regular)

var windows: [NSWindow] = []
for i in 1...count {
    let w = NSWindow(
        contentRect: NSRect(x: 80 + i * 40, y: 80 + i * 40, width: 360, height: 260),
        styleMask: [.titled, .closable, .resizable, .miniaturizable],
        backing: .buffered, defer: false)
    w.title = "probe-\(i)"
    let label = NSTextField(labelWithString: "\(i)")
    label.font = NSFont.systemFont(ofSize: 120, weight: .bold)
    label.frame = NSRect(x: 20, y: 20, width: 240, height: 160)
    w.contentView?.addSubview(label)
    w.isReleasedWhenClosed = false
    w.makeKeyAndOrderFront(nil)
    windows.append(w)
}

Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { _ in
    let frames: [[String: Any]] = windows.map { w in
        let f = w.frame
        return ["title": w.title, "x": f.origin.x, "y": f.origin.y, "w": f.size.width, "h": f.size.height]
    }
    if let data = try? JSONSerialization.data(withJSONObject: frames) { try? data.write(to: out, options: .atomic) }
}
app.run()
