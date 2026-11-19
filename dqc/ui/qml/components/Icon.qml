import QtQuick

// A glyph from the Windows icon font (Segoe Fluent Icons or Segoe MDL2 Assets).
Text {
    property string glyph: ""
    property int size: 16
    text: glyph
    font.family: IconFont
    font.pixelSize: size
    color: Theme.c.text
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
}
