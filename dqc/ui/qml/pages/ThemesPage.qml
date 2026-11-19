import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import "../components"

Item {
    id: page
    property string editingKey: ""
    property string saveError: ""

    function report(error, okText) {
        if (error) win.showToast(error, "bad")
        else if (okText) win.showToast(okText, "good")
    }

    ColorDialog {
        id: colorDialog
        title: "Pick a color"
        onAccepted: Theme.setColor(page.editingKey, selectedColor.toString().slice(0, 7))
    }
    FileDialog {
        id: importDialog
        title: "Import a theme"
        nameFilters: ["Theme files (*.json)"]
        onAccepted: page.report(Theme.importTheme(selectedFile), "Theme imported.")
    }
    FileDialog {
        id: exportDialog
        title: "Export this theme"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "json"
        nameFilters: ["Theme files (*.json)"]
        currentFile: "file:///" + Theme.name + ".json"
        onAccepted: page.report(Theme.exportTheme(selectedFile), "Theme exported.")
    }

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
            width: parent.width - 48
            spacing: 16

            PageHeader {
                Layout.fillWidth: true
                title: "Themes"
                subtitle: "Pick a theme, or change any color and save it as your own."
                AppButton { text: "Import"; glyph: ""; onClicked: importDialog.open() }
                AppButton { text: "Export"; glyph: ""; onClicked: exportDialog.open() }
            }

            Flow {
                Layout.fillWidth: true
                spacing: 12
                Repeater {
                    model: Theme.all
                    delegate: Rectangle {
                        id: swatch
                        required property var modelData
                        readonly property bool active: modelData.name === Theme.name
                        width: 168
                        height: 112
                        radius: Theme.radius + 2
                        color: modelData.colors.bg
                        border.width: active ? 2 : 1
                        border.color: active ? Theme.c.accent : Theme.c.border

                        Rectangle {
                            x: 12; y: 12
                            width: parent.width - 24; height: 46
                            radius: 6
                            color: swatch.modelData.colors.surface
                            border.width: 1
                            border.color: swatch.modelData.colors.border
                            Rectangle { x: 10; y: 10; width: 60; height: 7; radius: 3; color: swatch.modelData.colors.text }
                            Rectangle { x: 10; y: 23; width: 90; height: 6; radius: 3; color: swatch.modelData.colors.muted }
                            Rectangle {
                                anchors.right: parent.right; anchors.rightMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                width: 26; height: 14; radius: 4
                                color: swatch.modelData.colors.accent
                            }
                        }
                        Text {
                            x: 12
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 12
                            text: swatch.modelData.name
                            color: swatch.modelData.colors.text
                            font.family: "Segoe UI"
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                        Text {
                            anchors.right: parent.right
                            anchors.rightMargin: 12
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 13
                            text: swatch.modelData.preset ? "Built in" : "Yours"
                            color: swatch.modelData.colors.muted
                            font.family: "Segoe UI"
                            font.pixelSize: 11
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: Theme.apply(swatch.modelData.name)
                        }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                implicitHeight: editor.implicitHeight + 36

                ColumnLayout {
                    id: editor
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 18
                    spacing: 14

                    RowLayout {
                        Layout.fillWidth: true
                        Txt {
                            text: "Edit colors: " + Theme.name + (Theme.dirty ? " (unsaved)" : "")
                            role: "heading"
                            Layout.fillWidth: true
                        }
                        AppButton {
                            visible: Theme.dirty
                            compact: true
                            text: "Discard changes"
                            onClicked: Theme.revert()
                        }
                        AppButton {
                            visible: !Theme.preset && !Theme.dirty
                            compact: true
                            kind: "subtle"
                            glyph: ""
                            text: "Delete theme"
                            onClicked: Theme.remove(Theme.name)
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: Math.max(1, Math.floor(width / 300))
                        columnSpacing: 24
                        rowSpacing: 8

                        Repeater {
                            model: Theme.keys
                            delegate: RowLayout {
                                id: colorRow
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 10
                                Rectangle {
                                    width: 30; height: 30
                                    radius: 6
                                    color: Theme.c[colorRow.modelData.key]
                                    border.width: 1
                                    border.color: Theme.c.border
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            page.editingKey = colorRow.modelData.key
                                            colorDialog.selectedColor = Theme.c[colorRow.modelData.key]
                                            colorDialog.open()
                                        }
                                    }
                                }
                                Txt { text: colorRow.modelData.label; Layout.fillWidth: true }
                                AppField {
                                    implicitWidth: 96
                                    implicitHeight: 30
                                    font.family: "Cascadia Mono"
                                    font.pixelSize: 12
                                    text: Theme.c[colorRow.modelData.key]
                                    validator: RegularExpressionValidator { regularExpression: /#[0-9a-fA-F]{0,6}/ }
                                    onTextEdited: if (text.length === 7) Theme.setColor(colorRow.modelData.key, text)
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 12
                        Txt { text: "Corner roundness" }
                        AppSlider {
                            id: radiusSlider
                            from: 0; to: 20; stepSize: 1
                            value: Theme.radius
                            Layout.preferredWidth: 220
                            onMoved: Theme.setRadius(value)
                        }
                        Txt { text: Theme.radius + " px"; role: "muted" }
                        Item { Layout.fillWidth: true }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        AppField {
                            id: nameField
                            Layout.preferredWidth: 240
                            placeholderText: "Name for your theme"
                            text: Theme.preset ? "" : Theme.name
                        }
                        AppButton {
                            kind: "primary"
                            glyph: ""
                            text: "Save theme"
                            onClicked: page.report(Theme.saveAs(nameField.text), "Theme saved.")
                        }
                        Txt {
                            text: "Saving under the same name replaces your earlier version."
                            role: "muted"
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }
    }
}
