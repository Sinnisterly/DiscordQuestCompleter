import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

Item {
    id: page
    readonly property var s: Backend.orbSummary
    readonly property bool hasData: s.balance !== undefined && s.balance >= 0

    function num(n) { return Number(n || 0).toLocaleString(Qt.locale(), "f", 0) }

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
                title: "Orbs"
                subtitle: page.hasData
                          ? "Read from Discord " + page.s.updatedText + ". Tracking since " + page.s.sinceText + "."
                          : "Your balance is read from the top of Discord's Quests page."
                AppButton {
                    glyph: ""
                    text: Backend.detecting ? "Reading" : "Read now"
                    enabled: !Backend.detecting
                    onClicked: Backend.detectQuests()
                }
            }

            // Balance and totals.
            GridLayout {
                Layout.fillWidth: true
                columns: width > 760 ? 4 : 2
                columnSpacing: 12
                rowSpacing: 12

                Repeater {
                    model: [
                        { label: "Balance", value: page.hasData ? page.num(page.s.balance) : "None yet", accent: true },
                        { label: "Earned this week", value: page.num(page.s.week) },
                        { label: "Earned this month", value: page.num(page.s.month) },
                        { label: "Available in open quests", value: page.num(page.s.available) }
                    ]
                    delegate: Card {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        implicitHeight: 84
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 4
                            Txt { text: modelData.label; role: "muted" }
                            Txt {
                                text: modelData.value
                                font.pixelSize: 24
                                font.weight: Font.DemiBold
                                color: modelData.accent ? Theme.c.accentHi : Theme.c.text
                            }
                        }
                    }
                }
            }

            // Balance over the last 30 days.
            Card {
                Layout.fillWidth: true
                implicitHeight: 280

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        Txt { text: "Balance, last 30 days"; role: "heading"; Layout.fillWidth: true }
                        Txt {
                            visible: page.hasData
                            text: page.num(page.s.total) + " earned and " + page.num(page.s.spent) + " spent since tracking began"
                            role: "muted"
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Txt {
                            anchors.centerIn: parent
                            visible: !page.hasData
                            width: Math.min(parent.width - 40, 440)
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            elide: Text.ElideNone
                            role: "muted"
                            text: "Open the Quests page in Discord and press Read now. After that the balance is noted every time the page is read, and this chart fills in."
                        }

                        Canvas {
                            id: chart
                            anchors.fill: parent
                            visible: page.hasData
                            property var points: page.s.chart || []
                            onPointsChanged: requestPaint()
                            onWidthChanged: requestPaint()
                            onHeightChanged: requestPaint()
                            Connections { target: Theme; function onChanged() { chart.requestPaint() } }

                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.reset()
                                var pts = points.filter(function (p) { return p.balance >= 0 })
                                if (pts.length === 0) return
                                var left = 52, right = width - 8, top = 8, bottom = height - 24
                                var values = pts.map(function (p) { return p.balance })
                                var lo = Math.min.apply(null, values), hi = Math.max.apply(null, values)
                                if (hi === lo) { hi += 50; lo = Math.max(0, lo - 50) }
                                var n = points.length
                                function x(i) { return left + (right - left) * (n > 1 ? i / (n - 1) : 0.5) }
                                function y(v) { return bottom - (bottom - top) * (v - lo) / (hi - lo) }

                                ctx.font = "11px 'Segoe UI', sans-serif"
                                ctx.fillStyle = Theme.c.muted
                                ctx.strokeStyle = Theme.c.border
                                ctx.lineWidth = 1
                                for (var g = 0; g <= 3; g++) {
                                    var v = lo + (hi - lo) * g / 3
                                    var gy = y(v)
                                    ctx.beginPath(); ctx.moveTo(left, gy); ctx.lineTo(right, gy); ctx.stroke()
                                    ctx.fillText(Math.round(v).toLocaleString(), 4, gy + 4)
                                }
                                for (var d = 0; d < n; d += 7)
                                    ctx.fillText(points[d].day, x(d) - 10, height - 6)

                                ctx.strokeStyle = Theme.c.accent
                                ctx.lineWidth = 2
                                ctx.beginPath()
                                var started = false
                                for (var i = 0; i < n; i++) {
                                    if (points[i].balance < 0) continue
                                    var px = x(i), py = y(points[i].balance)
                                    if (!started) { ctx.moveTo(px, py); started = true } else ctx.lineTo(px, py)
                                }
                                ctx.stroke()

                                var last = n - 1
                                while (last >= 0 && points[last].balance < 0) last--
                                if (last >= 0) {
                                    ctx.fillStyle = Theme.c.accentHi
                                    ctx.beginPath()
                                    ctx.arc(x(last), y(points[last].balance), 4, 0, Math.PI * 2)
                                    ctx.fill()
                                }
                            }
                        }
                    }
                }
            }

            Txt {
                Layout.fillWidth: true
                role: "muted"
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                text: "The app can only see your balance while Discord's Quests page is open, so it is checked whenever that page is read. "
                    + "Orbs earned are worked out from the rise between readings, and orbs spent from any drop."
            }
        }
    }
}
