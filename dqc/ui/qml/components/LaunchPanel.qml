import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Everything needed to launch one game: path, placement and duration.
Card {
    id: panel
    property string gameId: ""
    property var detail: ({})
    readonly property bool hasGame: detail.id !== undefined
    property var planResult: ({ ok: false, text: "" })
    property var durationResult: Backend.durationHint("")

    function reload() {
        detail = gameId ? Backend.gameDetail(gameId) : ({})
        if (!hasGame) return
        pathBox.currentIndex = 0
        var modes = detail.placements.map(function (p) { return p.mode })
        placementBox.currentIndex = Math.max(0, modes.indexOf(detail.defaultMode))
        replan()
    }
    function replan() {
        if (!hasGame || pathBox.currentIndex < 0 || placementBox.currentIndex < 0) {
            planResult = { ok: false, text: "" }
            return
        }
        planResult = Backend.planPath(gameId,
                                      detail.paths[pathBox.currentIndex].path,
                                      detail.placements[placementBox.currentIndex].mode)
    }

    onGameIdChanged: reload()
    Connections {
        target: Backend
        // Badges or the whole game list changed. Keep the user's choices.
        function onCatalogChanged() {
            if (!panel.gameId) return
            var keepPath = pathBox.currentIndex, keepMode = placementBox.currentIndex
            panel.detail = Backend.gameDetail(panel.gameId)
            if (!panel.hasGame) return
            pathBox.currentIndex = Math.min(keepPath, panel.detail.paths.length - 1)
            placementBox.currentIndex = keepMode
            panel.replan()
        }
    }

    Txt {
        anchors.centerIn: parent
        visible: !panel.hasGame
        text: "Pick a game from the list."
        role: "muted"
    }

    Flickable {
        anchors.fill: parent
        anchors.margins: 16
        visible: panel.hasGame
        contentHeight: body.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: body
            width: parent.width
            spacing: 10

            Art {
                gameId: panel.gameId
                name: panel.detail.name || ""
                large: true
                fillMode: Image.PreserveAspectFit
                Layout.fillWidth: true
                Layout.preferredHeight: 150
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Txt {
                    text: panel.detail.name || ""
                    role: "heading"
                    font.pixelSize: 18
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    Layout.fillWidth: true
                }
                Badge {
                    visible: !!panel.detail.hasQuest
                    text: panel.detail.orbs > 0 ? panel.detail.orbs.toLocaleString(Qt.locale(), "f", 0) + " orbs"
                        : panel.detail.reward ? panel.detail.reward : "Quest running"
                    tone: "warn"
                }
            }

            Txt {
                visible: !!panel.detail.notes
                text: panel.detail.notes || ""
                color: panel.detail.warn ? Theme.c.bad : Theme.c.muted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                Layout.fillWidth: true
            }

            Txt { text: "Executable path"; role: "section"; Layout.topMargin: 4 }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                AppCombo {
                    id: pathBox
                    Layout.fillWidth: true
                    model: panel.hasGame ? panel.detail.paths : []
                    textRole: "path"
                    valueRole: "path"
                    elideMode: Text.ElideMiddle
                    onActivated: panel.replan()
                }
                Badge {
                    visible: panel.hasGame && pathBox.currentIndex >= 0
                             && panel.detail.paths.length > pathBox.currentIndex
                             && panel.detail.paths[pathBox.currentIndex].verified
                    text: "Verified"
                    tone: "good"
                }
            }
            Txt {
                text: panel.planResult.text
                role: "mono"
                color: panel.planResult.ok ? Theme.c.muted : Theme.c.bad
                font.pixelSize: 11
                elide: Text.ElideMiddle
                Layout.fillWidth: true
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 4
                spacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    spacing: 5
                    Txt { text: "Duration"; role: "section" }
                    AppField {
                        id: durationField
                        Layout.fillWidth: true
                        placeholderText: Backend.defaultDuration
                        invalid: !panel.durationResult.ok
                        onTextChanged: panel.durationResult = Backend.durationHint(text)
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    spacing: 5
                    Txt { text: "Placement"; role: "section" }
                    AppCombo {
                        id: placementBox
                        Layout.fillWidth: true
                        model: panel.hasGame ? panel.detail.placements : []
                        textRole: "label"
                        valueRole: "mode"
                        onActivated: function (index) {
                            if (!panel.detail.placements[index].enabled)
                                currentIndex = 0
                            panel.replan()
                        }
                    }
                }
            }
            Txt {
                text: panel.durationResult.text + (panel.durationResult.ok ? ". Also accepts 20m, 1h30m, 25:00 or 900." : "")
                role: "muted"
                color: panel.durationResult.ok ? Theme.c.muted : Theme.c.bad
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                Layout.fillWidth: true
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 6
                spacing: 8
                AppButton {
                    kind: "primary"
                    glyph: ""
                    text: "Launch"
                    enabled: panel.planResult.ok && panel.durationResult.ok
                    Layout.fillWidth: true
                    onClicked: Backend.launch(panel.gameId,
                                              panel.detail.paths[pathBox.currentIndex].path,
                                              panel.detail.placements[placementBox.currentIndex].mode,
                                              durationField.text)
                }
                AppButton {
                    // Quests read from Discord are managed by detection, not by hand.
                    visible: panel.detail.questSource !== "discord"
                    text: panel.detail.questSource === "marked" ? "Unmark quest" : "Mark quest"
                    glyph: ""
                    onClicked: Backend.setQuestMarked(panel.gameId, panel.detail.questSource !== "marked")
                }
            }
        }
    }
}
