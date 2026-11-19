import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// A labeled switch with an optional description under the label.
Item {
    id: root
    property alias checked: sw.checked
    property string title: ""
    property string description: ""
    signal toggled(bool value)
    implicitHeight: row.implicitHeight + 16
    opacity: enabled ? 1 : 0.5

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.topMargin: 8
        anchors.bottomMargin: 8
        spacing: 16
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Txt { text: root.title; Layout.fillWidth: true }
            Txt {
                text: root.description
                role: "muted"
                visible: text !== ""
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        Switch {
            id: sw
            onToggled: root.toggled(checked)
            indicator: Rectangle {
                implicitWidth: 40
                implicitHeight: 22
                radius: 11
                color: sw.checked ? Theme.c.accent : Theme.c.surfaceHi
                border.width: sw.checked ? 0 : 1
                border.color: Theme.c.border
                Behavior on color { ColorAnimation { duration: 140 } }
                Rectangle {
                    width: 16; height: 16; radius: 8
                    y: 3
                    x: sw.checked ? parent.width - width - 3 : 3
                    color: sw.checked ? "#ffffff" : Theme.c.muted
                    Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                }
            }
        }
    }
}
