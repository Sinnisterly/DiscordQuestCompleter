import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// How to use the Quests page, as a short numbered list.
Popup {
    id: help
    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(560, parent ? parent.width - 64 : 560)
    padding: 24
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    readonly property var steps: [
        "Open Discord and click Quests in the left sidebar. Keep that page open while you use this app.",
        "Press Detect from Discord. The app reads the quests on that page. It never uses your account or token.",
        "Accept the quests you want in Discord. Launch all does this for you while the Quests page is open.",
        "Press Launch on a quest, or Launch all to run every quest at once. Each game runs as a small stand-in program that Discord sees as the game.",
        "Leave it running until the countdown ends. Each quest runs for the time it asks for plus 30 seconds. Then claim the reward in Discord."
    ]
    readonly property var notes: [
        "Quests under Do these in Discord run inside Discord, so this app cannot do them.",
        "If a quest does not move after a minute or two, press Options and try another executable path.",
        "With Watch Discord on in Settings, this page updates by itself whenever the Quests page is open.",
        "Turn on Start with Windows and new quest alerts in Settings to hear about new quests without opening the app.",
        "The Orbs page tracks your balance each time the Quests page is read."
    ]
    readonly property var backgroundNotes: [
        "Turn on Check for quests in the background in Settings, and you do not need to keep Discord's Quests page open.",
        "Once an hour the app opens the Quests page in Discord, reads it, then goes back to the page Discord was on.",
        "Discord only draws that page while it is on screen, so it comes to the front for about a second. "
            + "To keep that out of your way, it only runs after 5 minutes with no keyboard or mouse use, "
            + "never while a fullscreen game or video is in front, and never while you are using Discord.",
        "Discord has to be open, but it can sit behind other windows. If Discord is minimized or closed to the tray, "
            + "the check waits until it is open again.",
        "With Start with Windows and Quest alerts on as well, you hear about new quests without opening anything."
    ]

    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.45) }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 140 }
        NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: 140; easing.type: Easing.OutCubic }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 100 } }

    background: Rectangle {
        radius: Theme.radius + 4
        color: Theme.c.surface
        border.width: 1
        border.color: Theme.c.border
    }

    contentItem: ColumnLayout {
        spacing: 14

        Txt { text: "How it works"; role: "heading"; font.pixelSize: 18 }

        Repeater {
            model: help.steps
            delegate: RowLayout {
                required property string modelData
                required property int index
                Layout.fillWidth: true
                spacing: 12
                Rectangle {
                    Layout.alignment: Qt.AlignTop
                    width: 24; height: 24; radius: 12
                    color: Theme.c.accent
                    Text {
                        anchors.centerIn: parent
                        text: index + 1
                        color: "#ffffff"
                        font.family: "Segoe UI"
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                    }
                }
                Txt {
                    text: modelData
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    lineHeight: 1.15
                    Layout.fillWidth: true
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border; Layout.topMargin: 4 }

        Txt { text: "Checking in the background"; role: "section" }
        Repeater {
            model: help.backgroundNotes
            delegate: RowLayout {
                required property string modelData
                Layout.fillWidth: true
                spacing: 10
                Rectangle {
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: 7
                    width: 5; height: 5; radius: 3
                    color: Theme.c.accent
                }
                Txt {
                    text: modelData
                    role: "muted"
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    Layout.fillWidth: true
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border; Layout.topMargin: 4 }

        Txt { text: "Good to know"; role: "section" }
        Repeater {
            model: help.notes
            delegate: RowLayout {
                required property string modelData
                Layout.fillWidth: true
                spacing: 10
                Rectangle {
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: 7
                    width: 5; height: 5; radius: 3
                    color: Theme.c.muted
                }
                Txt {
                    text: modelData
                    role: "muted"
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    Layout.fillWidth: true
                }
            }
        }

        AppButton {
            Layout.alignment: Qt.AlignRight
            Layout.topMargin: 6
            kind: "primary"
            text: "Got it"
            onClicked: help.close()
        }
    }
}
