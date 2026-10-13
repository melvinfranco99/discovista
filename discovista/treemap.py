"""Widget de mapa de árbol (treemap) anidado y ventana emergente de información."""
import zlib

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QCursor, QFont, QFontMetrics, QGuiApplication,
                         QLinearGradient, QPainter, QPen, QPixmap)
from PyQt6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .info import file_category, fmt_size
from .scanner import Node

BG = QColor("#151821")


# ---------------------------------------------------------------- popup ----
class InfoPopup(QWidget):
    """Tarjeta flotante que sigue al ratón."""

    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = InfoPopup()
        return cls._instance

    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.frame = QFrame()
        self.frame.setObjectName("popup")
        self.frame.setStyleSheet(
            "#popup{background:rgba(24,27,38,245);border:1px solid #3d4459;border-radius:10px;}"
            "QLabel{color:#e4e8f3;background:transparent;}")
        fl = QVBoxLayout(self.frame)
        fl.setContentsMargins(14, 11, 14, 11)
        self.label = QLabel()
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(520)
        self.label.setMinimumWidth(380)
        fl.addWidget(self.label)
        lay.addWidget(self.frame)
        self._html = None

    def show_html(self, html, gpos=None):
        if gpos is None:
            gpos = QCursor.pos()
        if html != self._html:
            self._html = html
            self.label.setText(html)
            self.adjustSize()
        screen = QGuiApplication.screenAt(gpos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        w, h = self.width(), self.height()
        x, y = gpos.x() + 18, gpos.y() + 20
        if x + w > geo.right():
            x = gpos.x() - w - 14
        if y + h > geo.bottom():
            y = gpos.y() - h - 14
        x = max(geo.left(), x)
        y = max(geo.top(), y)
        self.move(x, y)
        if not self.isVisible():
            self.show()

    def hide_popup(self):
        self.hide()


# --------------------------------------------------------------- layout ----
def _worst(row_sum, row_max, row_min, side):
    s2 = row_sum * row_sum
    w2 = side * side
    return max(w2 * row_max / s2, s2 / (w2 * row_min))


def squarify(sizes, x, y, w, h):
    """Algoritmo 'squarified treemap'. sizes debe ir ordenado de mayor a menor."""
    total = sum(sizes)
    if total <= 0 or w <= 0 or h <= 0:
        return []
    scale = w * h / total
    areas = [s * scale for s in sizes]
    rects = []
    i, n = 0, len(areas)
    while i < n:
        side = min(w, h)
        if side <= 0:
            rects.extend((x, y, 0, 0) for _ in range(n - i))
            break
        row = [areas[i]]
        rsum, rmax, rmin = areas[i], areas[i], areas[i]
        i += 1
        while i < n:
            a = areas[i]
            if a <= 0:
                break
            ns, nmax, nmin = rsum + a, max(rmax, a), min(rmin, a)
            if _worst(ns, nmax, nmin, side) <= _worst(rsum, rmax, rmin, side):
                row.append(a)
                rsum, rmax, rmin = ns, nmax, nmin
                i += 1
            else:
                break
        if w >= h:
            cw = rsum / h
            yy = y
            for a in row:
                hh = a / cw
                rects.append((x, yy, cw, hh))
                yy += hh
            x += cw
            w -= cw
        else:
            rh = rsum / w
            xx = x
            for a in row:
                ww = a / rh
                rects.append((xx, y, ww, rh))
                xx += ww
            y += rh
            h -= rh
    return rects


class Item:
    __slots__ = ("rect", "node", "depth", "header", "hue")

    def __init__(self, rect, node, depth, hue):
        self.rect = rect
        self.node = node
        self.depth = depth
        self.header = False
        self.hue = hue


def visible_children(node):
    return sorted((c for c in list(node.children or ()) if c.size > 0 or c.kind == "mount"),
                  key=lambda c: c.size, reverse=True)


def _text_color(c):
    lum = 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()
    return QColor("#111318") if lum > 0.62 else QColor("#f4f6fb")


# --------------------------------------------------------------- widget ----
class Treemap(QWidget):
    zoomRequested = pyqtSignal(object)
    upRequested = pyqtSignal()
    contextRequested = pyqtSignal(object, QPoint)
    hoverChanged = pyqtSignal(object)

    HEADER = 19
    PAD = 3

    def __init__(self, describe, parent=None):
        super().__init__(parent)
        self.describe = describe
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)
        self.root = None
        self.items = []
        self.cache = None
        self._cache_key = None
        self.dirty = True
        self.hover = None
        self.highlight = None
        self.color_mode = "folder"
        self.max_depth = 6
        self.message = ("Elige un disco o una partición en el panel izquierdo\n"
                        "o pulsa «Abrir carpeta» para analizar cualquier carpeta.")
        self.font_n = QFont(self.font())
        self.font_n.setPointSizeF(8.6)
        self.font_b = QFont(self.font_n)
        self.font_b.setBold(True)
        self.font_s = QFont(self.font_n)
        self.font_s.setPointSizeF(7.8)
        self.hue_of = {}

    # API --------------------------------------------------------------
    def set_root(self, node):
        self.root = node
        self.hover = None
        self.highlight = None
        InfoPopup.get().hide_popup()
        self.invalidate()

    def set_message(self, text):
        self.message = text
        self.invalidate()

    def invalidate(self):
        self.dirty = True
        self.update()

    def set_highlight(self, node):
        if node is not self.highlight:
            self.highlight = node
            self.update()

    def color_for(self, node):
        """Color con el que aparece un nodo (para la lista lateral)."""
        for it in self.items:
            if it.node is node:
                return self._base_color(it)
        return QColor("#5a6275")

    # layout -----------------------------------------------------------
    def _layout(self):
        self.items = []
        self.hue_of = {}
        if not self.root:
            return
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        self._layout_children(self.root, visible_children(self.root), r, 1, None)

    def _layout_children(self, parent, kids, r, depth, hue):
        if r.width() < 3 or r.height() < 3 or not kids:
            return
        total = sum(k.size for k in kids)
        if total <= 0:
            return
        area = r.width() * r.height()
        min_size = total * 6.0 / area       # elementos de menos de ~6 px² se agrupan
        shown, rest, restn = [], 0, 0
        for k in kids:
            if k.size >= min_size and k.size > 0:
                shown.append(k)
            else:
                rest += k.size
                restn += 1
        if rest > 0 and restn:
            rn = Node(f"{restn} elementos diminutos", parent, "rest", rest)
            rn.count = restn
            shown.append(rn)
            shown.sort(key=lambda c: c.size, reverse=True)
        rects = squarify([k.size for k in shown], r.x(), r.y(), r.width(), r.height())
        for i, (k, (x, y, w, h)) in enumerate(zip(shown, rects)):
            hh = hue if hue is not None else (0.58 + i * 0.61803398875) % 1.0
            self._add(k, QRectF(x, y, w, h), depth, hh)

    def _add(self, node, rect, depth, hue):
        it = Item(rect, node, depth, hue)
        self.items.append(it)
        if (node.kind == "dir" and node.children and depth < self.max_depth
                and rect.width() > 34 and rect.height() > self.HEADER + 14):
            it.header = True
            inner = rect.adjusted(self.PAD, self.HEADER, -self.PAD, -self.PAD)
            self._layout_children(node, visible_children(node), inner, depth + 1, hue)

    # colores ----------------------------------------------------------
    def _base_color(self, it):
        n = it.node
        if n.kind == "rest":
            return QColor("#4a5063")
        if n.kind == "group":
            return QColor("#6c7488") if self.color_mode == "type" else QColor.fromHslF(it.hue, 0.25, 0.48)
        if n.kind == "mount":
            return QColor("#2b3346")
        if self.color_mode == "type":
            if n.kind == "file":
                return QColor(file_category(n.name)[1])
            light = max(0.13, 0.27 - 0.025 * it.depth)
            return QColor.fromHslF(0.62, 0.14, light if it.header else 0.36)
        if n.kind == "file":
            jitter = (zlib.crc32(n.name.encode(errors="replace")) % 100) / 100.0
            return QColor.fromHslF(it.hue, 0.58, 0.50 + 0.10 * jitter)
        if it.header:
            return QColor.fromHslF(it.hue, 0.48, max(0.17, 0.34 - 0.035 * it.depth))
        return QColor.fromHslF(it.hue, 0.45, 0.42)

    # pintado ----------------------------------------------------------
    def _render(self):
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(BG)
        self._layout()
        p = QPainter(pm)
        if not self.root:
            p.setPen(QColor("#7d869c"))
            f = QFont(self.font())
            f.setPointSizeF(12)
            p.setFont(f)
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self.message)
        elif not self.items:
            p.setPen(QColor("#7d869c"))
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter,
                       "Esta carpeta está vacía" if self.root.note is None else self.root.note)
        for it in self.items:
            self._paint_item(p, it)
        p.end()
        self.cache = pm
        self.dirty = False

    def _paint_item(self, p, it):
        r = it.rect
        if r.width() < 1 or r.height() < 1:
            return
        n = it.node
        c = self._base_color(it)
        rr = r.adjusted(0.5, 0.5, -0.5, -0.5)

        if it.header:
            p.fillRect(r, c.darker(135))
            hdr = QRectF(r.x(), r.y(), r.width(), self.HEADER)
            g = QLinearGradient(hdr.topLeft(), hdr.bottomLeft())
            g.setColorAt(0, c.lighter(125))
            g.setColorAt(1, c)
            p.fillRect(hdr, g)
            p.setPen(QPen(QColor(0, 0, 0, 120), 1))
            p.drawRect(rr)
            self._label(p, hdr.adjusted(5, 0, -4, 0), n.name, fmt_size(n.size), c, header=True)
            return

        if n.kind == "rest":
            p.fillRect(r, c)
            p.fillRect(r, QBrush(QColor(255, 255, 255, 22), Qt.BrushStyle.BDiagPattern))
        elif n.kind == "mount":
            p.fillRect(r, c)
            p.setPen(QPen(QColor("#6f7a96"), 1, Qt.PenStyle.DashLine))
            p.drawRect(rr.adjusted(1, 1, -1, -1))
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0.0, c.lighter(128))
            g.setColorAt(0.55, c)
            g.setColorAt(1.0, c.darker(140))
            p.fillRect(r, g)
            if n.kind == "group":
                p.fillRect(r, QBrush(QColor(0, 0, 0, 30), Qt.BrushStyle.Dense6Pattern))
        p.setPen(QPen(QColor(0, 0, 0, 110), 1))
        p.drawRect(rr)

        if r.width() > 38 and r.height() > 15:
            name = n.name
            if n.kind == "mount":
                name = f"↪ {n.name} (otro disco)"
            elif n.kind == "dir":
                name = n.name + "/"
            self._label(p, r.adjusted(4, 2, -3, -2), name,
                        fmt_size(n.size) if n.kind != "mount" else "", c)

    def _label(self, p, r, name, size, bg, header=False):
        p.setPen(_text_color(bg))
        fm_b = QFontMetrics(self.font_b)
        if header:
            p.setFont(self.font_b)
            size_w = QFontMetrics(self.font_s).horizontalAdvance(size) + 10
            avail = r.width() - size_w
            if avail > 24:
                p.drawText(r.adjusted(0, 0, -size_w, 0), Qt.AlignmentFlag.AlignVCenter,
                           fm_b.elidedText(name, Qt.TextElideMode.ElideMiddle, int(avail)))
                p.setFont(self.font_s)
                col = _text_color(bg)
                col.setAlpha(190)
                p.setPen(col)
                p.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, size)
            else:
                p.drawText(r, Qt.AlignmentFlag.AlignVCenter,
                           fm_b.elidedText(name, Qt.TextElideMode.ElideRight, int(r.width())))
            return
        p.setFont(self.font_b)
        line_h = fm_b.height()
        p.drawText(QRectF(r.x(), r.y(), r.width(), line_h), Qt.AlignmentFlag.AlignLeft,
                   fm_b.elidedText(name, Qt.TextElideMode.ElideMiddle, int(r.width())))
        if size and r.height() > line_h * 2:
            p.setFont(self.font_s)
            col = _text_color(bg)
            col.setAlpha(200)
            p.setPen(col)
            p.drawText(QRectF(r.x(), r.y() + line_h, r.width(), line_h), Qt.AlignmentFlag.AlignLeft, size)

    def paintEvent(self, e):
        key = (self.width(), self.height(), self.devicePixelRatioF())
        if self.dirty or self.cache is None or self._cache_key != key:
            self._render()
            self._cache_key = key
        p = QPainter(self)
        p.drawPixmap(0, 0, self.cache)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for node, col in ((self.highlight, QColor("#ffd166")), (self.hover, QColor("#ffffff"))):
            if node is None:
                continue
            it = self._item_of(node)
            if it is None:
                continue
            fill = QColor(col)
            fill.setAlpha(38)
            p.fillRect(it.rect, fill)
            p.setPen(QPen(col, 2))
            p.drawRect(it.rect.adjusted(1, 1, -1, -1))

    def _item_of(self, node):
        for it in self.items:
            if it.node is node:
                return it
        return None

    def item_at(self, pos):
        pt = QPointF(pos)
        for it in reversed(self.items):
            if it.rect.contains(pt):
                return it
        return None

    # eventos ----------------------------------------------------------
    def resizeEvent(self, e):
        self.dirty = True
        super().resizeEvent(e)

    def mouseMoveEvent(self, e):
        it = self.item_at(e.position().toPoint())
        node = it.node if it else None
        if node is not self.hover:
            self.hover = node
            self.hoverChanged.emit(node)
            self.update()
        if node is not None:
            InfoPopup.get().show_html(self.describe(node), e.globalPosition().toPoint())
            self.setCursor(Qt.CursorShape.PointingHandCursor if node.kind == "dir"
                           else Qt.CursorShape.ArrowCursor)
        else:
            InfoPopup.get().hide_popup()

    def leaveEvent(self, e):
        self.hover = None
        self.hoverChanged.emit(None)
        InfoPopup.get().hide_popup()
        self.update()

    def mousePressEvent(self, e):
        it = self.item_at(e.position().toPoint())
        b = e.button()
        if b == Qt.MouseButton.LeftButton and it:
            n = it.node
            # clic en un archivo -> entrar en su carpeta contenedora si no es la actual
            if n.kind != "dir":
                n = n.parent if n.parent is not self.root else None
            if n is not None and n is not self.root:
                InfoPopup.get().hide_popup()
                self.zoomRequested.emit(n)
        elif b in (Qt.MouseButton.BackButton, Qt.MouseButton.MiddleButton):
            self.upRequested.emit()
        elif b == Qt.MouseButton.RightButton and it:
            InfoPopup.get().hide_popup()
            self.contextRequested.emit(it.node, e.globalPosition().toPoint())
