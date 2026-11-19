import QtQuick
import QtQuick.Layouts

// A quest on the Discord page that this app cannot run, with the reason.
Card {
    id: card
    required property string title
    required property string reason
    required property string reward
    required property int orbs
    required property string endsLabel

    color: Qt.rgba(Theme.c.surface.r, Theme.c.surface.g, Theme.c.surface.b, 0.55)
    implicitHeight: col.implicitHeight + 28

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 14
        spacing: 6

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Icon { glyph: ""; size: 13; color: Theme.c.muted }
            Txt { text: card.title; font.weight: Font.DemiBold; color: Theme.c.muted; Layout.fillWidth: true }
        }
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Badge {
                text: card.orbs > 0 ? card.orbs.toLocaleString(Qt.locale(), "f", 0) + " orbs"
                    : card.reward !== "" ? card.reward : "Reward unknown"
                tone: card.orbs > 0 ? "accent" : "muted"
            }
            Badge { visible: card.endsLabel !== ""; text: card.endsLabel; tone: "warn" }
        }
        Txt {
            text: card.reason
            role: "muted"
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            Layout.fillWidth: true
        }
    }
}
