import QtQuick

// Text in one of a few fixed styles.
// role: "body", "title", "heading", "muted", "section" or "mono".
Text {
    property string role: "body"
    color: role === "muted" || role === "section" || role === "mono" ? Theme.c.muted : Theme.c.text
    font.family: role === "mono" ? "Cascadia Mono" : "Segoe UI"
    font.pixelSize: role === "title" ? 22 : role === "heading" ? 16 : role === "section" ? 11
                  : role === "mono" || role === "muted" ? 12 : 13
    font.weight: role === "title" || role === "heading" || role === "section" ? Font.DemiBold : Font.Normal
    font.letterSpacing: role === "section" ? 0.8 : 0
    font.capitalization: role === "section" ? Font.AllUppercase : Font.MixedCase
    elide: Text.ElideRight
}
