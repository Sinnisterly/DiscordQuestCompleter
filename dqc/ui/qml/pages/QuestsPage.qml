import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

Item {
    id: page
    signal openGame(string gameId, string name)
    readonly property bool anyQuests: QuestModel.count > 0 || Backend.otherQuests.length > 0

    function orbText(n) { return n.toLocaleString(Qt.locale(), "f", 0) + " orbs" }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        PageHeader {
            Layout.fillWidth: true
            title: "Quests"
            subtitle: {
                var parts = []
                if (QuestModel.count > 0)
                    parts.push(QuestModel.count + (QuestModel.count === 1 ? " quest" : " quests")
                               + " you can run here, " + page.orbText(Backend.questOrbs))
                if (Backend.otherQuests.length > 0)
                    parts.push(Backend.otherQuests.length + " more in Discord, " + page.orbText(Backend.otherOrbs))
                parts.push(Backend.questStatus + (Backend.watchQuests ? ". Watching Discord" : ""))
                return parts.join(". ")
            }
            AppButton {
                kind: "primary"
                glyph: ""
                visible: QuestModel.count > 1
                text: Backend.launchingAll ? "Accepting quests" : "Launch all"
                enabled: !Backend.launchingAll
                onClicked: Backend.launchAll()
            }
            AppButton {
                glyph: ""
                text: Backend.detecting ? "Reading" : "Detect from Discord"
                enabled: !Backend.detecting
                onClicked: Backend.detectQuests()
            }
            AppButton {
                kind: "subtle"
                glyph: ""
                text: "Help"
                onClicked: helpDialog.open()
            }
        }

        HelpDialog { id: helpDialog; objectName: "helpDialog" }

        GridView {
            id: grid
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: page.anyQuests
            clip: true
            model: QuestModel
            readonly property int columns: Math.max(1, Math.floor(width / 280))
            cellWidth: Math.floor(width / columns)
            cellHeight: Math.round(cellWidth * 0.42) + 160
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Item {
                id: cell
                required property string gameId
                required property string name
                required property string title
                required property string reward
                required property string endsLabel
                required property string questSource
                required property bool needsSteam
                required property int orbs
                required property int accepted
                required property int progress
                required property string wrongPlatform
                required property string launchTime
                width: grid.cellWidth
                height: grid.cellHeight
                GameCard {
                    anchors.fill: parent
                    anchors.margins: 6
                    gameId: cell.gameId
                    name: cell.title
                    reward: cell.reward
                    endsLabel: cell.endsLabel
                    questSource: cell.questSource
                    needsSteam: cell.needsSteam
                    orbs: cell.orbs
                    accepted: cell.accepted
                    progress: cell.progress
                    wrongPlatform: cell.wrongPlatform
                    launchTime: cell.launchTime
                    onDetails: page.openGame(cell.gameId, cell.name)
                    opacity: 0
                    Component.onCompleted: opacity = 1
                    Behavior on opacity { NumberAnimation { duration: 180 } }
                }
            }

            // Quests this app cannot run, listed after the ones it can.
            footer: ColumnLayout {
                width: grid.width
                spacing: 10
                visible: Backend.otherQuests.length > 0

                Txt {
                    text: "Do these in Discord"
                    role: "section"
                    Layout.topMargin: QuestModel.count > 0 ? 14 : 0
                    Layout.leftMargin: 6
                }
                GridLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 6
                    Layout.rightMargin: 6
                    columns: grid.columns
                    columnSpacing: 12
                    rowSpacing: 12
                    Repeater {
                        model: Backend.otherQuests
                        delegate: OtherQuestCard {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredWidth: 1
                            Layout.alignment: Qt.AlignTop
                            title: modelData.title
                            reason: modelData.reason
                            reward: modelData.reward
                            orbs: modelData.orbs
                            endsLabel: modelData.endsLabel
                        }
                    }
                }
                Item { height: 6 }
            }
        }

        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !page.anyQuests

            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 48, 460)
                spacing: 10
                Icon {
                    glyph: ""
                    size: 28
                    color: Theme.c.muted
                    Layout.alignment: Qt.AlignHCenter
                }
                Txt {
                    text: "No quests found yet"
                    role: "heading"
                    Layout.alignment: Qt.AlignHCenter
                }
                Txt {
                    text: "Open Discord and click Quests in the left sidebar, then press Detect from Discord. "
                        + "With Watch Discord turned on in Settings, this page updates by itself while the Quests page is open."
                    role: "muted"
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }
                Txt {
                    text: "You can also mark a game by hand from the Library page."
                    role: "muted"
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    Layout.fillWidth: true
                }
            }
        }
    }
}
