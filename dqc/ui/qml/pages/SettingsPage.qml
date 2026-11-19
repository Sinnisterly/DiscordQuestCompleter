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
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border }
                    Toggle {
                        Layout.fillWidth: true
                        title: "Check for quests in the background"
                        description: "Once an hour, while you are away from the PC, opens the Quests page in Discord, "
                                   + "reads it, and goes back to where Discord was. You do not need to open the page yourself."
                        checked: Backend.backgroundCheck
                        onToggled: function (value) { Backend.backgroundCheck = value }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.bottomMargin: 8
                        spacing: 8
                        Icon { glyph: "\uE946"; size: 13; color: Theme.c.muted; Layout.alignment: Qt.AlignTop }
                        Txt {
                            Layout.fillWidth: true
                            role: "muted"
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            text: "Discord comes to the front for about a second while this runs, so it only happens after "
                                + "5 minutes with no keyboard or mouse use, never while a fullscreen game or video is in front, "
                                + "and never while you are using Discord. Discord must be open, not minimized. "
                                + "Open the Help on the Quests page for more."
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border }
                    Toggle {
                        Layout.fillWidth: true
                        enabled: Backend.trayAvailable
                        title: "Quest alerts"
                        description: "Windows notifications when a new quest appears, when one is ready to claim, "
                                   + "and when one you have not finished ends today."
                        checked: Backend.alertsEnabled
                        onToggled: function (value) { Backend.alertsEnabled = value }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border }
                    Toggle {
                        Layout.fillWidth: true
                        title: "Auto-launch new quests"
                        description: "When a new quest is found, accept it, set it to Desktop and start it, with no click from you."
                        checked: Backend.autoLaunch
                        onToggled: function (value) { Backend.autoLaunch = value }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.bottomMargin: 8
                        spacing: 8
                        Icon { glyph: "\uE7BA"; size: 13; color: Theme.c.warn; Layout.alignment: Qt.AlignTop }
                        Txt {
                            Layout.fillWidth: true
                            color: Theme.c.warn
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            text: "This acts on your Discord account while you are away. Automation like this is the "
                                + "kind of activity most likely to be flagged by Discord, and can lead to a warning or a ban. "
                                + "Off by default. Use it at your own risk."
                        }
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
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border }
                    Toggle {
                        Layout.fillWidth: true
                        title: "Start with Windows"
                        description: "Opens in the tray when you sign in, so new quests are caught without you starting the app. "
                                   + "You can also turn this off in Windows Settings under Apps, Startup."
                        checked: Backend.startWithWindows
                        onToggled: function (value) { Backend.startWithWindows = value }
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

            Txt { text: "Updates"; role: "section"; Layout.topMargin: 8 }
            Card {
                Layout.fillWidth: true
                implicitHeight: updateCol.implicitHeight + 24
                ColumnLayout {
                    id: updateCol
                    anchors.fill: parent
                    anchors.margins: 12
                    anchors.leftMargin: 18
                    anchors.rightMargin: 18
                    spacing: 0
                    RowLayout {
                        visible: Backend.updateVersion !== ""
                        Layout.fillWidth: true
                        Layout.topMargin: 6
                        Layout.bottomMargin: 6
                        spacing: 10
                        Icon { glyph: "\uE896"; size: 16; color: Theme.c.accentHi }
                        Txt {
                            text: "Version " + Backend.updateVersion + " is available. You have " + Backend.version + "."
                            Layout.fillWidth: true
                        }
                        AppButton {
                            kind: "primary"
                            compact: true
                            text: "Download"
                            onClicked: Qt.openUrlExternally(Backend.updateUrl)
                        }
                    }
                    Toggle {
                        Layout.fillWidth: true
                        title: "Check for updates"
                        description: "Looks at the project's GitHub releases page when the app starts, at most twice a day. Nothing about you is sent."
                        checked: Backend.checkUpdates
                        onToggled: function (value) { Backend.checkUpdates = value }
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
