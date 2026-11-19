import QtQuick
import QtQuick.Layouts

// Page title, a line under it, and room on the right for buttons.
RowLayout {
    property alias title: titleText.text
    property alias subtitle: subtitleText.text
    default property alias actions: actionRow.data
    spacing: 16

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 2
        Txt { id: titleText; role: "title"; Layout.fillWidth: true }
        Txt {
            id: subtitleText
            role: "muted"
            visible: text !== ""
            Layout.fillWidth: true
        }
    }
    RowLayout {
        id: actionRow
        spacing: 8
    }
}
