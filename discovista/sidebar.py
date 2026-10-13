"""Panel lateral con los discos, sus particiones y otros volúmenes."""
import html

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QLabel, QMenu, QVBoxLayout, QWidget

from .info import fmt_pct, fmt_size
from .treemap import InfoPopup

PART_COLORS = ["#5b8def", "#47c19a", "#f0a050", "#c77dff", "#ef6f8a", "#4fc3e8", "#e4cf55", "#8bd36a"]
MUTED = "#8b93a7"


def usage_color(frac):
    if frac < 0.70:
        return QColor("#4cc38a")
    if frac < 0.88:
        return QColor("#f0b447")
    return QColor("#ef5d6c")


def volume_html(v, disk=None):
    rows = [("Tipo", f"{v.type_name} · {html.escape(v.fs_name)}"),
            ("Dispositivo", html.escape(v.path)),
            ("Tamaño", fmt_size(v.size))]
    if v.label:
        rows.insert(0, ("Etiqueta", html.escape(v.label)))
    if v.mountpoints:
        rows.append(("Montada en", "<br>".join(html.escape(m) for m in v.mountpoints)))
    else:
        rows.append(("Montada en", f"<span style='color:{MUTED}'>no está montada</span>"))
    if v.used is not None and v.total:
        free = max(0, v.total - v.used)
        rows.append(("Usado", f"<b>{fmt_size(v.used)}</b> ({fmt_pct(100 * v.used / v.total)})"))
        rows.append(("Libre", f"{fmt_size(free)}"))
    if disk is not None:
        rows.append(("Disco", f"{html.escape(disk.model)} ({html.escape(disk.path)})"))
    if v.uuid:
        rows.append(("UUID", f"<span style='color:{MUTED}'>{v.uuid}</span>"))
    body = "".join(f"<tr><td style='color:{MUTED};padding-right:12px'>{k}</td><td>{val}</td></tr>"
                   for k, val in rows)
    hint = ("Clic para analizar su contenido" if v.mountpoints and v.fstype != "swap"
            else ("Memoria de intercambio: no contiene archivos" if v.fstype == "swap"
                  else "Móntala para poder analizar su contenido"))
    return (f"<div style='font-size:12.5pt;font-weight:600'>{html.escape(v.title)}</div>"
            f"<table cellspacing=0 cellpadding=2 style='margin-top:6px'>{body}</table>"
            f"<div style='color:#7fa7ff;margin-top:6px'>{hint}</div>")


class PartitionStrip(QWidget):
    """Barra con una "cajita" proporcional por partición."""
    scanRequested = pyqtSignal(object)

    def __init__(self, disk, colors):
        super().__init__()
        self.disk = disk
        self.colors = colors
        self.setMouseTracking(True)
        self.setFixedHeight(30)
        self.boxes = []

    def _layout(self):
        self.boxes = []
        vols = [self.disk.whole] if self.disk.whole else self.disk.volumes
        total = max(self.disk.size, sum(v.size for v in vols)) or 1
        W = self.width() - 2
        x = 1.0
        for v in vols:
            w = max(5.0, W * v.size / total)
            self.boxes.append((QRectF(x, 1, w - 2, self.height() - 2), v))
            x += w
        if x < W - 6:
            self.boxes.append((QRectF(x, 1, W - x, self.height() - 2), None))

    def paintEvent(self, e):
        self._layout()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for r, v in self.boxes:
            if v is None:
                p.setPen(QPen(QColor("#4a5165"), 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r, 5, 5)
                continue
            c = QColor(self.colors.get(id(v), "#5b8def"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c.darker(230))
            p.drawRoundedRect(r, 5, 5)
            if v.used is not None and v.total:
                frac = min(1.0, v.used / v.total)
                ur = QRectF(r.x(), r.y(), r.width() * frac, r.height())
                g = QLinearGradient(ur.topLeft(), ur.bottomLeft())
                g.setColorAt(0, c.lighter(120))
                g.setColorAt(1, c)
                p.setBrush(g)
                p.save()
                p.setClipRect(ur)
                p.drawRoundedRect(r, 5, 5)
                p.restore()
            p.setPen(QPen(c, 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
            if r.width() > 34:
                p.setPen(QColor("#f4f6fb"))
                f = QFont(self.font())
                f.setPointSizeF(7.8)
                f.setBold(True)
                p.setFont(f)
                txt = QFontMetrics(f).elidedText(v.title, Qt.TextElideMode.ElideRight, int(r.width() - 6))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, txt)

    def _at(self, pos):
        for r, v in self.boxes:
            if r.contains(pos.toPointF() if hasattr(pos, "toPointF") else pos):
                return r, v
        return None, None

    def mouseMoveEvent(self, e):
        r, v = self._at(e.position())
        pop = InfoPopup.get()
        if r is None:
            pop.hide_popup()
            return
        if v is None:
            used = sum(x.size for x in self.disk.volumes)
            pop.show_html(f"<div style='font-size:12.5pt;font-weight:600'>Espacio sin asignar</div>"
                          f"<div>{fmt_size(max(0, self.disk.size - used))} libres sin particionar en "
                          f"{html.escape(self.disk.model)} ({html.escape(self.disk.path)})</div>",
                          e.globalPosition().toPoint())
        else:
            pop.show_html(volume_html(v, self.disk), e.globalPosition().toPoint())
        self.setCursor(Qt.CursorShape.PointingHandCursor if v and v.mountpoints else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, e):
        InfoPopup.get().hide_popup()

    def mousePressEvent(self, e):
        r, v = self._at(e.position())
        if v is not None and e.button() == Qt.MouseButton.LeftButton:
            InfoPopup.get().hide_popup()
            self.scanRequested.emit(v)


class VolumeRow(QWidget):
    scanRequested = pyqtSignal(object)

    def __init__(self, vol, disk, color):
        super().__init__()
        self.vol = vol
        self.disk = disk
        self.color = QColor(color)
        self.hovered = False
        self.setMouseTracking(True)
        self.setFixedHeight(50)
        if vol.mountpoints and vol.fstype != "swap":
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, e):
        v = self.vol
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        indent = 14 * v.level
        r = QRectF(self.rect()).adjusted(indent + 1, 1, -1, -1)
        if self.hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 14))
            p.drawRoundedRect(r, 7, 7)
        # cuadrado de color
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color if v.mounted or v.fstype == "swap" else self.color.darker(200))
        p.drawRoundedRect(QRectF(r.x() + 6, r.y() + 8, 10, 10), 3, 3)

        f = QFont(self.font())
        f.setPointSizeF(9.2)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#e8ebf3") if v.mounted else QColor("#9aa1b3"))
        title = v.title
        if v.level:
            title = "↳ " + title
        fm = QFontMetrics(f)
        right = fmt_size(v.size)
        fs = QFont(self.font())
        fs.setPointSizeF(8)
        rw = QFontMetrics(fs).horizontalAdvance(right)
        p.drawText(QRectF(r.x() + 22, r.y() + 3, r.width() - 30 - rw, 18), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(title, Qt.TextElideMode.ElideRight, int(r.width() - 34 - rw)))
        p.setFont(fs)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(r.x(), r.y() + 3, r.width() - 6, 18),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, right)

        sub = f"{v.name} · {v.fs_name}"
        if v.type not in ("part", "disk", "net"):
            sub = f"{v.name} · {v.type_name}"
        bar = QRectF(r.x() + 22, r.y() + 24, r.width() - 30, 6)
        if v.used is not None and v.total:
            frac = min(1.0, v.used / v.total)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2a2f3e"))
            p.drawRoundedRect(bar, 3, 3)
            p.setBrush(usage_color(frac))
            p.drawRoundedRect(QRectF(bar.x(), bar.y(), max(4, bar.width() * frac), bar.height()), 3, 3)
            sub += f" · {fmt_size(v.total - v.used)} libres ({fmt_pct(100 * (1 - frac))})"
        elif v.fstype == "swap":
            sub += " · memoria de intercambio"
        elif not v.mounted:
            sub += " · sin montar"
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(r.x() + 22, r.y() + 32, r.width() - 26, 16), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(fs).elidedText(sub, Qt.TextElideMode.ElideRight, int(r.width() - 28)))

    def enterEvent(self, e):
        self.hovered = True
        self.update()

    def leaveEvent(self, e):
        self.hovered = False
        InfoPopup.get().hide_popup()
        self.update()

    def mouseMoveEvent(self, e):
        InfoPopup.get().show_html(volume_html(self.vol, self.disk), e.globalPosition().toPoint())

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            InfoPopup.get().hide_popup()
            self.scanRequested.emit(self.vol)


class DiskCard(QFrame):
    scanRequested = pyqtSignal(object)

    def __init__(self, disk, other=False):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 8)
        lay.setSpacing(4)
        vols = disk.all_volumes()
        colors = {id(v): PART_COLORS[i % len(PART_COLORS)] for i, v in enumerate(vols)}

        title = QLabel(f"<b>{html.escape(disk.model)}</b>")
        title.setStyleSheet("font-size:11pt;color:#eef1f8")
        lay.addWidget(title)
        if not other:
            sub = QLabel(f"{disk.kind_name} · {fmt_size(disk.size)} · {disk.path}")
            sub.setStyleSheet(f"color:{MUTED};font-size:8.5pt")
            lay.addWidget(sub)
            strip = PartitionStrip(disk, colors)
            strip.scanRequested.connect(self.scanRequested)
            lay.addSpacing(4)
            lay.addWidget(strip)
            lay.addSpacing(2)
        for v in vols:
            row = VolumeRow(v, None if other else disk, colors[id(v)])
            row.scanRequested.connect(self.scanRequested)
            lay.addWidget(row)


class OtherVolumes:
    """Contenedor tipo 'disco' para volúmenes de red/FUSE."""

    def __init__(self, vols):
        self.model = "Otros volúmenes (red, FUSE…)"
        self.vols = vols
        self.path = ""
        self.size = sum(v.size for v in vols)

    def all_volumes(self):
        return self.vols


def choose_mountpoint(vol, parent, global_pos):
    """Si el volumen tiene varios puntos de montaje deja elegir uno."""
    if len(vol.mountpoints) <= 1:
        return vol.mountpoints[0] if vol.mountpoints else None
    m = QMenu(parent)
    for mp in vol.mountpoints:
        m.addAction(mp)
    a = m.exec(global_pos)
    return a.text() if a else None
