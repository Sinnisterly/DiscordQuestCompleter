import QtQuick

// A small colored tag. tone: "accent", "good", "warn", "bad" or "muted".
Rectangle {
    property alias text: label.text
    property string tone: "muted"
    readonly property color toneColor: tone === "accent" ? Theme.c.accent
                                     : tone === "good" ? Theme.c.good
                                     : tone === "warn" ? Theme.c.warn
                                     : tone === "bad" ? Theme.c.bad : Theme.c.muted
    implicitWidth: label.implicitWidth + 14
    implicitHeight: 20
    radius: 10
    color: Qt.rgba(toneColor.r, toneColor.g, toneColor.b, 0.16)
    Text {
        id: label
        anchors.centerIn: parent
        color: parent.toneColor
        font.family: "Segoe UI"
        font.pixelSize: 11
        font.weight: Font.DemiBold
    }
}
