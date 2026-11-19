import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components"
import "pages"

ApplicationWindow {
    id: win
    width: 1180
    height: 760
    minimumWidth: 960
    minimumHeight: 620
    visible: !StartHidden
    title: "Discord Quest Completer"
    flags: Qt.Window | Qt.FramelessWindowHint
    color: Theme.c.bg
    font.family: "Segoe UI"

    property int currentPage: 0
    property bool maximized: false
    property rect normalGeometry: Qt.rect(0, 0, 0, 0)
    readonly property int edge: 6

    function showToast(text, kind) { toast.show(text, kind) }

    // A frameless window that the system maximizes covers the taskbar, so
    // maximize to the screen's work area by hand.
    function toggleMaximize() {
        if (maximized) {
            x = normalGeometry.x; y = normalGeometry.y
            width = normalGeometry.width; height = normalGeometry.height
            maximized = false
        } else {
            normalGeometry = Qt.rect(x, y, width, height)
            var area = Backend.availableGeometry(x + width / 2, y + height / 2)
            x = area.x; y = area.y; width = area.width; height = area.height
            maximized = true
        }
    }

    onClosing: function (close) {
        close.accepted = false
        Backend.closeWindow()
    }

    Connections {
        target: Backend
        function onToast(text, kind) { win.showToast(text, kind) }
        function onDialogRequested(token, title, body, ok, cancel) { dialog.ask(token, title, body, ok, cancel) }
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.c.bg
        border.width: win.maximized ? 0 : 1
        border.color: Theme.c.border

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: win.maximized ? 0 : 1
            spacing: 0

            TitleBar {
                window: win
                Layout.fillWidth: true
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                Sidebar {
                    Layout.fillHeight: true
                    current: win.currentPage
                    onPicked: function (index) { win.currentPage = index }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: Theme.c.bg

                    Rectangle {
                        anchors.fill: parent
                        anchors.rightMargin: 8
                        anchors.bottomMargin: 8
                        radius: Theme.radius + 4
                        color: Qt.tint(Theme.c.bg, Qt.rgba(1, 1, 1, 0.015))
                        border.width: 1
                        border.color: Theme.c.border

                        StackLayout {
                            id: stack
                            anchors.fill: parent
                            currentIndex: win.currentPage
                            onCurrentIndexChanged: pageIn.restart()

                            QuestsPage {
                                onOpenGame: function (gameId, name) {
                                    library.showGame(gameId, name)
                                    win.currentPage = 2
                                }
                            }
                            OrbsPage {}
                            LibraryPage { id: library }
                            SessionsPage {}
                            ThemesPage {}
                            SettingsPage {}
                        }

                        ParallelAnimation {
                            id: pageIn
                            NumberAnimation { target: stack; property: "opacity"; from: 0.4; to: 1; duration: 160 }
                            NumberAnimation { target: stack; property: "anchors.topMargin"; from: 8; to: 0; duration: 160; easing.type: Easing.OutCubic }
                        }
                    }
                }
            }
        }
    }

    // Edge and corner grips. Hidden while maximized.
    Repeater {
        model: [
            { edges: Qt.LeftEdge, x: 0, y: win.edge, w: win.edge, h: -2 * win.edge, cursor: Qt.SizeHorCursor },
            { edges: Qt.RightEdge, x: -win.edge, y: win.edge, w: win.edge, h: -2 * win.edge, cursor: Qt.SizeHorCursor },
            { edges: Qt.TopEdge, x: win.edge, y: 0, w: -2 * win.edge, h: win.edge, cursor: Qt.SizeVerCursor },
            { edges: Qt.BottomEdge, x: win.edge, y: -win.edge, w: -2 * win.edge, h: win.edge, cursor: Qt.SizeVerCursor },
            { edges: Qt.LeftEdge | Qt.TopEdge, x: 0, y: 0, w: win.edge, h: win.edge, cursor: Qt.SizeFDiagCursor },
            { edges: Qt.RightEdge | Qt.BottomEdge, x: -win.edge, y: -win.edge, w: win.edge, h: win.edge, cursor: Qt.SizeFDiagCursor },
            { edges: Qt.RightEdge | Qt.TopEdge, x: -win.edge, y: 0, w: win.edge, h: win.edge, cursor: Qt.SizeBDiagCursor },
            { edges: Qt.LeftEdge | Qt.BottomEdge, x: 0, y: -win.edge, w: win.edge, h: win.edge, cursor: Qt.SizeBDiagCursor }
        ]
        delegate: MouseArea {
            required property var modelData
            visible: !win.maximized
            // Negative values count from the right or bottom edge.
            x: modelData.x < 0 ? win.width + modelData.x : modelData.x
            y: modelData.y < 0 ? win.height + modelData.y : modelData.y
            width: modelData.w < 0 ? win.width + modelData.w : modelData.w
            height: modelData.h < 0 ? win.height + modelData.h : modelData.h
            cursorShape: modelData.cursor
            acceptedButtons: Qt.LeftButton
            onPressed: win.startSystemResize(modelData.edges)
        }
    }

    Toast { id: toast }
    ConfirmDialog { id: dialog }
}
