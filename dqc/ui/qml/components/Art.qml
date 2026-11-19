import QtQuick

// Game artwork, with a plain placeholder while it loads or when none exists.
Rectangle {
    id: root
    property string gameId: ""
    property string name: ""
    property bool large: false
    property int fillMode: Image.PreserveAspectCrop
    color: Theme.c.surfaceHi
    radius: Math.max(0, Theme.radius - 2)
    clip: true

    Text {
        anchors.centerIn: parent
        visible: img.status !== Image.Ready
        text: root.name.length ? root.name.charAt(0).toUpperCase() : ""
        color: Theme.c.muted
        font.family: "Segoe UI"
        font.pixelSize: Math.max(12, Math.min(root.height * 0.4, 40))
        font.weight: Font.DemiBold
    }

    Image {
        id: img
        anchors.fill: parent
        source: root.gameId ? "image://art/" + root.gameId + (root.large ? "/L" : "/S") : ""
        asynchronous: true
        cache: true
        fillMode: root.fillMode
        smooth: true
        opacity: status === Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 180 } }
    }
}
