import QtQuick
import QtQuick.Controls.Basic

Slider {
    id: control
    implicitHeight: 24

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth
        height: 4
        radius: 2
        color: Theme.c.surfaceHi
        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 2
            color: Theme.c.accent
        }
    }

    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: 16
        height: 16
        radius: 8
        color: control.pressed ? Theme.c.accentHi : Theme.c.text
        border.width: 2
        border.color: Theme.c.accent
    }
}
