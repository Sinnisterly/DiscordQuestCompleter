import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

Item {
    id: page
    property string selectedId: ""

    // Called from the Quests page to show one game here.
    function showGame(gameId, name) {
        search.text = name
        Backend.search(name)
        selectedId = gameId
    }

    Timer {
        id: debounce
        interval: 120
        onTriggered: Backend.search(search.text)
    }

    // After the list is rebuilt, keep the selected game if it is still there,
    // otherwise select the first result.
    Connections {
        target: LibraryModel
        function onModelReset() { page.syncSelection() }
    }
    function syncSelection() {
        var row = LibraryModel.indexOf(selectedId)
        if (row < 0 && LibraryModel.count > 0) {
            selectedId = LibraryModel.idAt(0)
            return
        }
        list.currentIndex = row
        if (row >= 0) list.positionViewAtIndex(row, ListView.Contain)
    }
    onSelectedIdChanged: syncSelection()
    Component.onCompleted: syncSelection()

    RowLayout {
        id: columns
        anchors.fill: parent
        anchors.margins: 24
        spacing: 20

        // Fixed shares of the width. Long paths would otherwise widen a column.
        ColumnLayout {
            Layout.fillHeight: true
            Layout.preferredWidth: (columns.width - columns.spacing) * 0.55
            Layout.maximumWidth: Layout.preferredWidth
            spacing: 10

            Txt { text: "Library"; role: "title" }

            AppField {
                id: search
                Layout.fillWidth: true
                leftPadding: 36
                placeholderText: "Search games, for example where winds, zzz, valorant"
                onTextChanged: debounce.restart()
                Icon {
                    glyph: ""
                    size: 13
                    color: Theme.c.muted
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            Txt {
                role: "muted"
                text: search.text.trim() === ""
                      ? list.count + " community-verified games. Type to search all " + Backend.gameCount.toLocaleString(Qt.locale(), "f", 0) + "."
                      : list.count + (list.count === 1 ? " result" : " results")
            }

            ListView {
                id: list
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: LibraryModel
                spacing: 2
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                keyNavigationEnabled: true
                onCurrentIndexChanged: if (currentIndex >= 0 && LibraryModel.idAt(currentIndex) !== page.selectedId) page.selectedId = LibraryModel.idAt(currentIndex)

                delegate: Rectangle {
                    id: row
                    required property int index
                    required property string gameId
                    required property string name
                    required property string path
                    required property bool verified
                    required property bool hasQuest
                    required property bool needsSteam
                    required property int pathCount
                    width: ListView.view.width - 10
                    height: 66
                    radius: Theme.radius
                    color: ListView.isCurrentItem ? Theme.c.surfaceHi : hover.hovered ? Theme.c.surface : "transparent"
                    Behavior on color { ColorAnimation { duration: 100 } }
                    HoverHandler { id: hover }
                    TapHandler { onTapped: page.selectedId = row.gameId }

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 8
                        spacing: 12
                        Art {
                            gameId: row.gameId
                            name: row.name
                            Layout.preferredWidth: 112
                            Layout.fillHeight: true
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            Txt { text: row.name; font.weight: Font.DemiBold; Layout.fillWidth: true }
                            Txt { text: row.path; role: "mono"; font.pixelSize: 11; elide: Text.ElideMiddle; Layout.fillWidth: true }
                            Row {
                                spacing: 5
                                Badge { visible: row.hasQuest; text: "Quest"; tone: "warn" }
                                Badge { visible: row.verified; text: "Verified"; tone: "good" }
                                Badge { visible: row.needsSteam; text: "Needs Steam install"; tone: "bad" }
                                Badge { visible: row.pathCount > 1; text: row.pathCount + " paths" }
                            }
                        }
                    }
                }
            }
        }

        LaunchPanel {
            gameId: page.selectedId
            Layout.fillHeight: true
            Layout.preferredWidth: (columns.width - columns.spacing) * 0.45
            Layout.maximumWidth: Layout.preferredWidth
        }
    }
}
