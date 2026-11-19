import QtQuick
import QtQuick.Controls.Basic

// kind: "primary" (one per view), "ghost", "subtle" or "danger".
Button {
    id: control
    property string kind: "ghost"
    property string glyph: ""
    property bool compact: false

    implicitHeight: compact ? 30 : 36
    leftPadding: compact ? 10 : 14
    rightPadding: compact ? 10 : 14
    hoverEnabled: true
    font.family: "Segoe UI"
    font.pixelSize: compact ? 12 : 13
    font.weight: Font.DemiBold

    readonly property color fill: {
        if (!enabled) return Theme.c.surface
        if (kind === "primary") return hovered ? Theme.c.accentHi : Theme.c.accent
        if (kind === "danger") return hovered ? Qt.darker(Theme.c.bad, 1.1) : Theme.c.bad
        if (kind === "subtle") return hovered ? Theme.c.surfaceHi : "transparent"
        return hovered ? Theme.c.surfaceHi : Theme.c.surface
    }
    readonly property color ink: !enabled ? Theme.c.muted
                               : (kind === "primary" || kind === "danger") ? "#ffffff" : Theme.c.text

    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 7
            Icon {
                visible: control.glyph !== ""
                glyph: control.glyph
                size: control.compact ? 12 : 14
                color: control.ink
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: control.text
                visible: control.text !== ""
                font: control.font
                color: control.ink
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    background: Rectangle {
        radius: Math.max(0, Theme.radius - 2)
        color: control.fill
        border.width: control.kind === "ghost" ? 1 : 0
        border.color: Theme.c.border
        scale: control.down ? 0.98 : 1
        Behavior on color { ColorAnimation { duration: 120 } }
        Behavior on scale { NumberAnimation { duration: 80 } }
    }
}
