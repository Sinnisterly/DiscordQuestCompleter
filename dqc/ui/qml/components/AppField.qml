import QtQuick
import QtQuick.Controls.Basic

TextField {
    id: control
    property bool invalid: false
    implicitHeight: 36
    leftPadding: 12
    rightPadding: 12
    font.family: "Segoe UI"
    font.pixelSize: 13
    color: Theme.c.text
    placeholderTextColor: Theme.c.muted
    selectionColor: Theme.c.accent
    selectedTextColor: "#ffffff"
    background: Rectangle {
        radius: Math.max(0, Theme.radius - 2)
        color: Theme.c.surface
        border.width: 1
        border.color: control.invalid ? Theme.c.bad
                    : control.activeFocus ? Theme.c.accent : Theme.c.border
        Behavior on border.color { ColorAnimation { duration: 120 } }
    }
}
