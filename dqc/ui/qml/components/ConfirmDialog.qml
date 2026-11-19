import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Questions and notices raised by the backend. Requests that arrive while
// one is open wait in a queue.
Popup {
    id: dialog
    property var queue: []
    property var current: null

    function ask(token, title, body, ok, cancel) {
        queue.push({ token: token, title: title, body: body, ok: ok, cancel: cancel })
        if (!opened) next()
    }
    function next() {
        if (queue.length === 0) { current = null; return }
        current = queue.shift()
        open()
    }
    function finish(accepted) {
        var token = current ? current.token : 0
        close()
        Backend.answer(token, accepted)
    }

    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape
    anchors.centerIn: Overlay.overlay
    width: Math.min(460, parent ? parent.width - 64 : 460)
    padding: 22
    onClosed: Qt.callLater(next)
    onAboutToHide: if (current && !accepted) Backend.answer(current.token, false)
    property bool accepted: false
    onAboutToShow: accepted = false

    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.45) }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140 }
        NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: 140; easing.type: Easing.OutCubic }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 }
    }

    background: Rectangle {
        radius: Theme.radius + 4
        color: Theme.c.surface
        border.width: 1
        border.color: Theme.c.border
    }

    contentItem: ColumnLayout {
        spacing: 12
        Txt {
            text: dialog.current ? dialog.current.title : ""
            role: "heading"
            Layout.fillWidth: true
        }
        Txt {
            text: dialog.current ? dialog.current.body : ""
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            color: Theme.c.muted
            lineHeight: 1.15
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.topMargin: 8
            Layout.alignment: Qt.AlignRight
            spacing: 8
            AppButton {
                visible: dialog.current && dialog.current.cancel !== ""
                text: dialog.current ? dialog.current.cancel : ""
                onClicked: dialog.close()
            }
            AppButton {
                kind: "primary"
                text: dialog.current ? dialog.current.ok : "OK"
                onClicked: { dialog.accepted = true; dialog.finish(true) }
            }
        }
    }
}
