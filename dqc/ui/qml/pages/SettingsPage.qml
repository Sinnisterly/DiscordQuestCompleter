import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

Item {
    Flickable {
        anchors.fill: parent
        contentHeight: body.implicitHeight + 48
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: body
            x: 24
            y: 24
            width: Math.min(parent.width - 48, 760)
            spacing: 16

            PageHeader { Layout.fillWidth: true; title: "Settings" }

            Txt { text: "Quest detection"; role: "section" }
            Card {
                Layout.fillWidth: true
                implicitHeight: detectCol.implicitHeight + 24
                ColumnLayout {
                    id: detectCol
                    anchors.fill: parent
                    anchors.margins: 12
                    anchors.leftMargin: 18
                    anchors.rightMargin: 18
                    spacing: 0
                    Toggle {
                        Layout.fillWidth: true
                        title: "Watch Discord for quests"
                        description: "Every 10 seconds, checks whether Discord's Quests page is open and reads it if so. "
                                   + "It reads what is on screen through Windows accessibility. It never uses your account or token."
                        checked: Backend.watchQuests
                        onToggled: function (value) { Backend.watchQuests = value }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        Layout.bottomMargin: 6
                        Txt { text: Backend.questStatus; role: "muted"; Layout.fillWidth: true }
                        AppButton {
                            compact: true
                            glyph: ""
                            text: "Detect now"
                            enabled: !Backend.detecting
                            onClicked: Backend.detectQuests()
                        }
                    }
                }
            }

            Txt { text: "Window"; role: "section"; Layout.topMargin: 8 }
            Card {
                Layout.fillWidth: true
                implicitHeight: windowCol.implicitHeight + 24
                ColumnLayout {
                    id: windowCol
                    anchors.fill: parent
                    anchors.margins: 12
                    anchors.leftMargin: 18
                    anchors.rightMargin: 18
                    spacing: 0
                    Toggle {
                        Layout.fillWidth: true
                        enabled: Backend.trayAvailable
                        title: "Keep running in the tray when closed"
                        description: Backend.trayAvailable
                                     ? "Closing the window leaves sessions running. Quit from the tray icon."
                                     : "Your desktop has no system tray, so closing the window quits the app."
                        checked: Backend.trayEnabled
                        onToggled: function (value) { Backend.trayEnabled = value }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border }
                    Toggle {
                        Layout.fillWidth: true
                        title: "Notify me when a session ends"
                        description: "Shows a Windows notification saying whether it ran the full time."
                        checked: Backend.notifyEnabled
                        onToggled: function (value) { Backend.notifyEnabled = value }
                    }
                }
            }

            Txt { text: "Game list"; role: "section"; Layout.topMargin: 8 }
            Card {
                Layout.fillWidth: true
                implicitHeight: listCol.implicitHeight + 32
                ColumnLayout {
                    id: listCol
                    anchors.fill: parent
                    anchors.margins: 16
                    anchors.leftMargin: 18
                    anchors.rightMargin: 18
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Txt { text: Backend.catalogStatus; Layout.fillWidth: true }
                        AppButton {
                            compact: true
                            glyph: ""
                            text: Backend.refreshing ? "Updating" : "Update now"
                            enabled: !Backend.refreshing
                            onClicked: Backend.refreshCatalog()
                        }
                    }
                    Txt {
                        text: "The list of games Discord can detect comes from Discord's public list and updates once a day on its own."
                        role: "muted"
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        Layout.fillWidth: true
                    }
                }
            }

            Txt { text: "About"; role: "section"; Layout.topMargin: 8 }
            Card {
                Layout.fillWidth: true
                implicitHeight: aboutCol.implicitHeight + 32
                ColumnLayout {
                    id: aboutCol
                    anchors.fill: parent
                    anchors.margins: 16
                    anchors.leftMargin: 18
                    anchors.rightMargin: 18
                    spacing: 8
                    Txt { text: "Discord Quest Completer " + Backend.version; font.weight: Font.DemiBold }
                    Txt {
                        text: "Not affiliated with Discord or any game publisher. Simulating game activity may break Discord's "
                            + "Terms of Service and can lead to warnings or a ban. You use it at your own risk."
                        role: "muted"
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        Layout.fillWidth: true
                    }
                    Txt {
                        text: "Files are kept in " + Backend.dataFolder
                        role: "mono"
                        font.pixelSize: 11
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                }
            }
        }
    }
}
