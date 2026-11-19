import QtQuick
import QtQuick.Layouts

// The app draws its own title bar. Dragging uses the system move, so Windows
// snapping still works.
Rectangle {
    id: bar
    required property var window
    height: 40
    color: Theme.c.bg

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        onPressed: bar.window.startSystemMove()
        onDoubleClicked: bar.window.toggleMaximize()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        spacing: 10

        Rectangle {
            width: 18; height: 18; radius: 5
            color: Theme.c.accent
            Icon {
                anchors.centerIn: parent
                glyph: ""
                size: 9
                color: "#ffffff"
            }
        }
        Txt {
            text: "Discord Quest Completer"
            role: "muted"
            Layout.fillWidth: true
        }

        Repeater {
            model: [
                { glyph: "", action: "min" },
                { glyph: bar.window.maximized ? "" : "", action: "max" },
                { glyph: "", action: "close" }
            ]
            delegate: Rectangle {
                id: btn
                required property var modelData
                Layout.preferredWidth: 46
                Layout.fillHeight: true
                color: hover.containsMouse
                       ? (modelData.action === "close" ? "#e81123" : Theme.c.surfaceHi)
                       : "transparent"
                Behavior on color { ColorAnimation { duration: 100 } }
                Icon {
                    anchors.centerIn: parent
                    glyph: btn.modelData.glyph
                    size: 10
                    color: hover.containsMouse && btn.modelData.action === "close" ? "#ffffff" : Theme.c.text
                }
                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        if (btn.modelData.action === "min") bar.window.showMinimized()
                        else if (btn.modelData.action === "max") bar.window.toggleMaximize()
                        else Backend.closeWindow()
                    }
                }
            }
        }
    }
}
