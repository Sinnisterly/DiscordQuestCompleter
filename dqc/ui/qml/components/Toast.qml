import QtQuick
import QtQuick.Layouts

// A short message at the bottom of the window that fades out on its own.
Rectangle {
    id: toast
    property string kind: "info"
    readonly property color tone: kind === "good" ? Theme.c.good : kind === "bad" ? Theme.c.bad : Theme.c.accent

    function show(text, kind) {
        label.text = text
        toast.kind = kind || "info"
        hideTimer.restart()
        toast.state = "shown"
    }

    width: Math.min(row.implicitWidth + 32, parent.width - 48)
    height: row.implicitHeight + 20
    radius: Theme.radius
    color: Theme.c.surfaceHi
    border.width: 1
    border.color: Theme.c.border
    anchors.horizontalCenter: parent.horizontalCenter
    y: parent.height
    opacity: 0
    visible: opacity > 0

    states: State {
        name: "shown"
        PropertyChanges { target: toast; opacity: 1; y: toast.parent.height - toast.height - 24 }
    }
    transitions: Transition {
        NumberAnimation { properties: "opacity,y"; duration: 180; easing.type: Easing.OutCubic }
    }

    Timer {
        id: hideTimer
        interval: 4000
        onTriggered: toast.state = ""
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        width: toast.width - 32
        spacing: 10
        Icon {
            glyph: toast.kind === "good" ? "" : toast.kind === "bad" ? "" : ""
            color: toast.tone
            size: 14
        }
        Txt {
            id: label
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            Layout.fillWidth: true
            Layout.maximumWidth: 520
        }
    }

    MouseArea {
        anchors.fill: parent
        onClicked: toast.state = ""
    }
}
