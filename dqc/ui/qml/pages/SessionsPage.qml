import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

Item {
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        PageHeader {
            Layout.fillWidth: true
            title: "Sessions"
            subtitle: Backend.runningCount === 0 ? "Nothing running"
                    : Backend.runningCount + (Backend.runningCount === 1 ? " session running" : " sessions running")
        }

        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: SessionModel.count > 0
            model: SessionModel
            spacing: 10
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            add: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 180 } }
            remove: Transition { NumberAnimation { property: "opacity"; to: 0; duration: 180 } }

            delegate: Card {
                id: item
                required property int sessionId
                required property string gameId
                required property string name
                required property string path
                required property real progress
                required property string status
                required property string state
                width: ListView.view.width
                height: 96

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 14
                    Art {
                        gameId: item.gameId
                        name: item.name
                        Layout.preferredWidth: 120
                        Layout.fillHeight: true
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        RowLayout {
                            Layout.fillWidth: true
                            Txt { text: item.name; role: "heading"; Layout.fillWidth: true }
                            Txt {
                                text: item.status
                                color: item.state === "finished" ? Theme.c.good
                                     : item.state === "stopped" ? Theme.c.warn : Theme.c.muted
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            height: 6
                            radius: 3
                            color: Theme.c.surfaceHi
                            Rectangle {
                                width: parent.width * item.progress
                                height: parent.height
                                radius: 3
                                color: item.state === "stopped" ? Theme.c.warn
                                     : item.state === "finished" ? Theme.c.good : Theme.c.accent
                                Behavior on width { NumberAnimation { duration: 450 } }
                            }
                        }
                        Txt { text: item.path; role: "mono"; font.pixelSize: 11; elide: Text.ElideMiddle; Layout.fillWidth: true }
                    }
                    AppButton {
                        text: "Stop"
                        glyph: ""
                        visible: item.state === "running"
                        onClicked: Backend.stopSession(item.sessionId)
                    }
                    // A run that stopped early stays here until retried or dismissed.
                    AppButton {
                        visible: item.state === "stopped"
                        kind: "primary"
                        glyph: ""
                        text: "Retry"
                        onClicked: Backend.retrySession(item.sessionId)
                    }
                    AppButton {
                        visible: item.state === "stopped"
                        kind: "subtle"
                        text: "Dismiss"
                        onClicked: Backend.dismissSession(item.sessionId)
                    }
                }
            }
        }

        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: SessionModel.count === 0
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 440)
                spacing: 10
                Icon { glyph: ""; size: 28; color: Theme.c.muted; Layout.alignment: Qt.AlignHCenter }
                Txt { text: "Nothing running"; role: "heading"; Layout.alignment: Qt.AlignHCenter }
                Txt {
                    text: "Launch a game from Quests or Library. Each session gets a small countdown window. "
                        + "Leave it open until the time runs out, then check the quest in Discord."
                    role: "muted"
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }
            }
        }
    }
}
