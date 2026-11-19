import QtQuick
import QtQuick.Controls.Basic

// Model entries are objects holding the textRole, the valueRole and an
// optional "enabled" flag.
ComboBox {
    id: control
    property int elideMode: Text.ElideRight
    implicitHeight: 36
    font.family: "Segoe UI"
    font.pixelSize: 13

    delegate: ItemDelegate {
        id: item
        required property var modelData
        required property int index
        width: control.popup.width - 8
        x: 4
        enabled: modelData.enabled === undefined || modelData.enabled
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: item.modelData[control.textRole]
            color: item.enabled ? Theme.c.text : Theme.c.muted
            font: control.font
            elide: Text.ElideMiddle
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: Math.max(0, Theme.radius - 4)
            color: item.highlighted ? Theme.c.surfaceHi : "transparent"
        }
    }

    indicator: Icon {
        x: control.width - width - 12
        y: (control.height - height) / 2
        glyph: ""
        size: 11
        color: Theme.c.muted
    }

    contentItem: Text {
        leftPadding: 12
        rightPadding: 30
        text: control.displayText
        font: control.font
        color: Theme.c.text
        elide: control.elideMode
        verticalAlignment: Text.AlignVCenter
    }

    background: Rectangle {
        radius: Math.max(0, Theme.radius - 2)
        color: Theme.c.surface
        border.width: 1
        border.color: control.activeFocus || control.popup.visible ? Theme.c.accent : Theme.c.border
    }

    popup: Popup {
        y: control.height + 4
        width: control.width
        padding: 4
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 320)
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
        }
        background: Rectangle {
            radius: Math.max(0, Theme.radius - 2)
            color: Theme.c.surface
            border.width: 1
            border.color: Theme.c.border
        }
    }
}
