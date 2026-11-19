import QtQuick
import QtQuick.Layouts

// Page navigation. Adding a page means adding an entry to `pages` here and a
// matching item in Main.qml's StackLayout.
Rectangle {
    id: side
    property int current: 0
    signal picked(int index)
    color: Theme.c.bg
    implicitWidth: 210

    readonly property var pages: [
        { label: "Quests", glyph: "" },
        { label: "Library", glyph: "" },
        { label: "Sessions", glyph: "" },
        { label: "Themes", glyph: "" },
        { label: "Settings", glyph: "" }
    ]

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        anchors.topMargin: 6
        spacing: 2

        Repeater {
            model: side.pages
            delegate: Rectangle {
                id: nav
                required property var modelData
                required property int index
                readonly property bool active: side.current === index
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                radius: Math.max(0, Theme.radius - 2)
                color: active ? Theme.c.surfaceHi : area.containsMouse ? Theme.c.surface : "transparent"
                Behavior on color { ColorAnimation { duration: 120 } }

                Rectangle {
                    width: 3
                    height: nav.active ? 16 : 0
                    radius: 2
                    color: Theme.c.accent
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    Behavior on height { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 10
                    spacing: 12
                    Icon {
                        glyph: nav.modelData.glyph
                        size: 15
                        color: nav.active ? Theme.c.text : Theme.c.muted
                    }
                    Txt {
                        text: nav.modelData.label
                        color: nav.active ? Theme.c.text : Theme.c.muted
                        font.weight: nav.active ? Font.DemiBold : Font.Normal
                        Layout.fillWidth: true
                    }
                    Badge {
                        visible: nav.modelData.label === "Sessions" && Backend.runningCount > 0
                        text: Backend.runningCount
                        tone: "accent"
                    }
                    Badge {
                        visible: nav.modelData.label === "Quests" && QuestModel.count > 0
                        text: QuestModel.count
                        tone: "warn"
                    }
                }
                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: side.picked(nav.index)
                }
            }
        }

        Item { Layout.fillHeight: true }

        Txt {
            text: Backend.catalogStatus
            role: "muted"
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Layout.leftMargin: 6
            Layout.bottomMargin: 4
        }
    }
}
