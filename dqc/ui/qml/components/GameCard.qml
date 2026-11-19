import QtQuick
import QtQuick.Layouts

// One live quest on the Quests page.
Card {
    id: card
    required property string gameId
    required property string name
    required property string reward
    required property string endsLabel
    required property string questSource
    required property bool needsSteam
    required property int orbs
    required property int accepted   // 1 yes, 0 no, -1 unknown
    required property int progress   // percent from Discord, -1 unknown
    required property string wrongPlatform  // e.g. "Xbox"; empty when Desktop or unknown
    required property string launchTime     // the quest's own time plus the sync margin
    signal details()

    border.color: hover.hovered ? Theme.c.accent : Theme.c.border
    Behavior on border.color { ColorAnimation { duration: 140 } }
    HoverHandler { id: hover }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        Art {
            gameId: card.gameId
            name: card.name
            large: true
            Layout.fillWidth: true
            Layout.preferredHeight: Math.round(width * 0.42)
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 4
            Layout.rightMargin: 4
            spacing: 3
            Txt { text: card.name; role: "heading"; font.pixelSize: 15; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                // Orb quests show the amount large. Item quests name the item.
                Rectangle {
                    visible: card.orbs > 0
                    width: 10; height: 10; radius: 5
                    color: Theme.c.accent
                    border.width: 2
                    border.color: Qt.lighter(Theme.c.accent, 1.4)
                }
                Txt {
                    visible: card.orbs > 0
                    text: card.orbs.toLocaleString(Qt.locale(), "f", 0) + " orbs"
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    color: Theme.c.accentHi
                }
                Txt {
                    visible: card.orbs === 0
                    text: card.reward !== "" ? card.reward + " (no orbs)" : "Quest running"
                    role: "muted"
                    Layout.fillWidth: true
                }
                Item { Layout.fillWidth: card.orbs > 0 }
            }
        }

        Flow {
            Layout.fillWidth: true
            Layout.leftMargin: 4
            spacing: 6
            Badge { visible: card.endsLabel !== ""; text: card.endsLabel; tone: "warn" }
            Badge { visible: card.progress >= 100; text: "Done. Claim it in Discord"; tone: "good" }
            Badge {
                visible: card.wrongPlatform !== ""
                text: "Set to " + card.wrongPlatform + ", needs Desktop"
                tone: "bad"
            }
            Badge {
                visible: card.accepted === 1 && card.progress < 100 && card.wrongPlatform === ""
                text: "Accepted"
                tone: "good"
            }
            Badge { visible: card.accepted === 0; text: "Not accepted"; tone: "bad" }
            // Quests read from Discord carry an accepted badge instead.
            Badge {
                visible: card.questSource !== "discord"
                text: card.questSource === "marked" ? "Marked by you" : "Shared list"
            }
            Badge { visible: card.needsSteam; text: "Needs Steam install"; tone: "bad" }
        }

        Item { Layout.fillHeight: true }

        // Progress as Discord reports it, read from the Quests page.
        RowLayout {
            visible: card.progress > 0 && card.progress < 100
            Layout.fillWidth: true
            Layout.leftMargin: 4
            Layout.rightMargin: 4
            spacing: 8
            Rectangle {
                Layout.fillWidth: true
                height: 5
                radius: 3
                color: Theme.c.surfaceHi
                Rectangle {
                    width: parent.width * Math.max(0, card.progress) / 100
                    height: parent.height
                    radius: 3
                    color: Theme.c.good
                    Behavior on width { NumberAnimation { duration: 400 } }
                }
            }
            Txt { text: card.progress + "% done in Discord"; role: "muted"; font.pixelSize: 11 }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            AppButton {
                kind: "primary"
                glyph: ""
                text: card.progress >= 100 ? "Done" : "Launch " + card.launchTime
                enabled: card.progress < 100
                Layout.fillWidth: true
                onClicked: Backend.quickLaunch(card.gameId)
            }
            AppButton {
                text: "Options"
                onClicked: card.details()
            }
        }
    }
}
