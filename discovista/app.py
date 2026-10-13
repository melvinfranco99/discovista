"""Ventana principal de DiscoVista."""
import html
import os
import sys
import time

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import (QAction, QColor, QCursor, QDesktopServices, QFont, QGuiApplication, QIcon,
                         QKeySequence, QPainter, QPalette, QPixmap)
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFileDialog, QFrame,
                             QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMenu, QMessageBox,
                             QProgressBar, QPushButton, QScrollArea, QSlider, QSplitter,
                             QStyledItemDelegate, QStyle, QToolButton, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

from . import __version__, disks
from .info import (CATEGORIES, OTHER_COLOR, PacmanDB, file_category, fmt_int, fmt_pct, fmt_size,
                   group_name, guess_purpose, user_name)
from .scanner import Scanner
from .sidebar import DiskCard, OtherVolumes, choose_mountpoint
from .treemap import InfoPopup, Treemap

HERE = os.path.dirname(os.path.abspath(__file__))
MUTED = "#8b93a7"
ACCENT = "#6d9bff"

STYLE = f"""
QMainWindow, QWidget#central {{ background:#11141b; }}
QWidget {{ color:#dfe3ee; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background:transparent; border:none; }}
QFrame#card {{ background:#1a1e29; border:1px solid #262c3b; border-radius:12px; }}
QFrame#panel {{ background:#161a23; border:1px solid #232937; border-radius:12px; }}
QLabel#h1 {{ font-size:15pt; font-weight:700; color:#f2f4fa; }}
QLabel#section {{ color:{MUTED}; font-size:8.5pt; font-weight:700; letter-spacing:1px; }}
QPushButton, QToolButton, QComboBox {{
    background:#1f2431; border:1px solid #2d3446; border-radius:8px; padding:6px 12px; color:#e3e7f1; }}
QPushButton:hover, QToolButton:hover, QComboBox:hover {{ background:#283043; border-color:#3b4560; }}
QPushButton:pressed, QToolButton:pressed {{ background:#1a1f2b; }}
QPushButton:disabled, QToolButton:disabled {{ color:#5b6274; }}
QPushButton#primary {{ background:#3a63d6; border-color:#4a73e6; color:white; font-weight:600; }}
QPushButton#primary:hover {{ background:#4672ea; }}
QPushButton#crumb {{ background:transparent; border:none; padding:4px 6px; color:#c9cfdd; }}
QPushButton#crumb:hover {{ background:#232a3a; color:white; }}
QPushButton#crumbLast {{ background:transparent; border:none; padding:4px 6px; color:white; font-weight:700; }}
QComboBox QAbstractItemView {{ background:#1f2431; selection-background-color:#3a63d6; }}
QTreeWidget {{ background:transparent; border:none; alternate-background-color:#191d27; }}
QTreeWidget::item {{ padding:3px 0; }}
QTreeWidget::item:hover {{ background:#222838; }}
QTreeWidget::item:selected {{ background:#2c3956; }}
QHeaderView::section {{ background:transparent; color:{MUTED}; border:none; border-bottom:1px solid #262c3b;
    padding:4px; font-size:8.5pt; }}
QProgressBar {{ background:#1f2431; border:none; border-radius:4px; height:8px; text-align:center; }}
QProgressBar::chunk {{ background:{ACCENT}; border-radius:4px; }}
QStatusBar {{ background:#0e1016; color:{MUTED}; }}
QSplitter::handle {{ background:#11141b; }}
QMenu {{ background:#1d2230; border:1px solid #333a4f; padding:4px; }}
QMenu::item {{ padding:6px 22px; border-radius:5px; }}
QMenu::item:selected {{ background:#3a63d6; }}
QMenu::separator {{ height:1px; background:#333a4f; margin:4px 8px; }}
QScrollBar:vertical {{ background:transparent; width:9px; }}
QScrollBar::handle:vertical {{ background:#2d3446; border-radius:4px; min-height:30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height:0; }}
QSlider::groove:horizontal {{ height:4px; background:#2d3446; border-radius:2px; }}
QSlider::handle:horizontal {{ background:{ACCENT}; width:14px; margin:-6px 0; border-radius:7px; }}
QToolTip {{ background:#1d2230; color:#e4e8f3; border:1px solid #3d4459; }}
"""


class BarDelegate(QStyledItemDelegate):
    """Dibuja el porcentaje como una barra."""

    def paint(self, p, opt, idx):
        if opt.state & QStyle.StateFlag.State_Selected:
            p.fillRect(opt.rect, QColor("#2c3956"))
        frac = idx.data(Qt.ItemDataRole.UserRole) or 0.0
        color = idx.data(Qt.ItemDataRole.UserRole + 1) or QColor(ACCENT)
        r = QRectF(opt.rect).adjusted(4, opt.rect.height() / 2 - 4, -44, -(opt.rect.height() / 2 - 4))
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#262c3b"))
        p.drawRoundedRect(r, 4, 4)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(r.x(), r.y(), max(3, r.width() * frac), r.height()), 4, 4)
        p.setPen(QColor("#c9cfdd"))
        p.drawText(QRectF(opt.rect).adjusted(0, 0, -4, 0),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fmt_pct(frac * 100))
        p.restore()


def _swatch(color, size=12):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), 3, 3)
    p.end()
    return QIcon(pm)


def _breakable(path):
    """Permite que las rutas largas se partan en varias líneas."""
    return html.escape(path).replace("/", "/​")


class MainWindow(QMainWindow):
    def __init__(self, start_path=None):
        super().__init__()
        self.setWindowTitle("DiscoVista — explorador de discos")
        self.setWindowIcon(QIcon(os.path.join(HERE, "discovista.svg")))
        self.resize(1440, 880)

        self.pacman = PacmanDB()
        self.scanner = None
        self.scan_root = None
        self.current = None
        self.loc = (None, None, None)       # (mount, volumen, disco) del escaneo
        self.expected = None                # bytes esperados (para el progreso)
        self.disks = []
        self._pending_zoom = None

        central = QWidget(objectName="central")
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(10, 10, 10, 6)
        outer.setSpacing(10)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(8)
        outer.addWidget(split)

        # ----- panel izquierdo: discos
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        hl = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(os.path.join(HERE, "discovista.svg")).pixmap(30, 30))
        hl.addWidget(logo)
        t = QLabel("DiscoVista", objectName="h1")
        hl.addWidget(t)
        hl.addStretch()
        rb = QToolButton()
        rb.setText("⟳")
        rb.setToolTip("Actualizar la lista de discos")
        rb.clicked.connect(self.load_disks)
        hl.addWidget(rb)
        ll.addLayout(hl)
        sec = QLabel("DISCOS Y VOLÚMENES", objectName="section")
        ll.addWidget(sec)
        self.disk_area = QScrollArea()
        self.disk_area.setWidgetResizable(True)
        self.disk_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ll.addWidget(self.disk_area, 1)
        qb = QHBoxLayout()
        home_b = QPushButton("Carpeta personal")
        home_b.clicked.connect(lambda: self.start_scan(os.path.expanduser("~")))
        open_b = QPushButton("Abrir carpeta…", objectName="primary")
        open_b.clicked.connect(self.choose_folder)
        qb.addWidget(home_b)
        qb.addWidget(open_b)
        ll.addLayout(qb)
        left.setMinimumWidth(290)
        split.addWidget(left)

        # ----- centro: barra de navegación + treemap
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(8)
        nav = QHBoxLayout()
        self.up_btn = QToolButton()
        self.up_btn.setText("↑  Subir")
        self.up_btn.setToolTip("Subir un nivel (Retroceso)")
        self.up_btn.clicked.connect(self.go_up)
        nav.addWidget(self.up_btn)
        self.crumbs = QHBoxLayout()
        self.crumbs.setSpacing(0)
        cw = QWidget()
        cw.setLayout(self.crumbs)
        nav.addWidget(cw, 1)
        nav.addWidget(QLabel("Colorear:"))
        self.color_box = QComboBox()
        self.color_box.addItems(["por carpeta", "por tipo de archivo"])
        self.color_box.currentIndexChanged.connect(self.set_color_mode)
        nav.addWidget(self.color_box)
        nav.addSpacing(6)
        nav.addWidget(QLabel("Detalle:"))
        self.depth = QSlider(Qt.Orientation.Horizontal)
        self.depth.setRange(1, 10)
        self.depth.setValue(6)
        self.depth.setFixedWidth(90)
        self.depth.setToolTip("Cuántos niveles de carpetas se dibujan a la vez")
        self.depth.valueChanged.connect(self.set_depth)
        nav.addWidget(self.depth)
        self.rescan_btn = QToolButton()
        self.rescan_btn.setText("⟳ Reanalizar")
        self.rescan_btn.clicked.connect(self.rescan)
        nav.addWidget(self.rescan_btn)
        ml.addLayout(nav)

        self.treemap = Treemap(self.describe)
        self.treemap.zoomRequested.connect(self.zoom_to)
        self.treemap.upRequested.connect(self.go_up)
        self.treemap.contextRequested.connect(self.context_menu)
        self.treemap.hoverChanged.connect(self.on_treemap_hover)
        frame = QFrame(objectName="panel")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(4, 4, 4, 4)
        fl.addWidget(self.treemap)
        ml.addWidget(frame, 1)

        # barra de progreso
        prog = QHBoxLayout()
        self.status = QLabel("Listo.")
        self.status.setStyleSheet(f"color:{MUTED}")
        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(220)
        self.progress.hide()
        self.cancel_btn = QPushButton("Detener")
        self.cancel_btn.clicked.connect(self.cancel_scan)
        self.cancel_btn.hide()
        prog.addWidget(self.status, 1)
        prog.addWidget(self.progress)
        prog.addWidget(self.cancel_btn)
        ml.addLayout(prog)
        split.addWidget(mid)

        # ----- panel derecho: detalles
        right = QFrame(objectName="panel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.setSpacing(4)
        rl.addWidget(QLabel("CARPETA ACTUAL", objectName="section"))
        self.d_title = QLabel("—", objectName="h1")
        self.d_title.setWordWrap(True)
        rl.addWidget(self.d_title)
        self.d_path = QLabel("")
        self.d_path.setWordWrap(True)
        self.d_path.setStyleSheet(f"color:{MUTED};font-size:8.5pt")
        self.d_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(self.d_path)
        self.d_size = QLabel("")
        self.d_size.setStyleSheet("font-size:22pt;font-weight:700;color:white")
        rl.addWidget(self.d_size)
        self.d_stats = QLabel("")
        self.d_stats.setWordWrap(True)
        self.d_stats.setStyleSheet(f"color:{MUTED}")
        rl.addWidget(self.d_stats)
        rl.addSpacing(8)
        rl.addWidget(QLabel("LO QUE MÁS OCUPA", objectName="section"))
        self.list = QTreeWidget()
        self.list.setColumnCount(3)
        self.list.setHeaderLabels(["Nombre", "Tamaño", "%"])
        self.list.setRootIsDecorated(False)
        self.list.setMouseTracking(True)
        self.list.setUniformRowHeights(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setItemDelegateForColumn(2, BarDelegate(self.list))
        hdr = self.list.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.resizeSection(2, 120)
        hdr.setStretchLastSection(False)
        self.list.itemEntered.connect(self.on_list_hover)
        self.list.itemDoubleClicked.connect(self.on_list_double)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.on_list_menu)
        self.list.viewport().installEventFilter(self)
        rl.addWidget(self.list, 1)
        self.legend_title = QLabel("LEYENDA", objectName="section")
        rl.addWidget(self.legend_title)
        self.legend = QLabel()
        self.legend.setWordWrap(True)
        rl.addWidget(self.legend)
        hint = QLabel("Clic: entrar en una carpeta · Clic derecho: opciones · "
                      "Retroceso o botón central: subir")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:#5f6679;font-size:8pt")
        rl.addWidget(hint)
        right.setMinimumWidth(300)
        split.addWidget(right)
        split.setSizes([320, 820, 360])
        split.setStretchFactor(1, 1)

        self.live_timer = QTimer(self)
        self.live_timer.setInterval(700)
        self.live_timer.timeout.connect(self.live_refresh)

        for seq, fn in ((QKeySequence(Qt.Key.Key_Backspace), self.go_up),
                        (QKeySequence("Alt+Up"), self.go_up),
                        (QKeySequence("F5"), self.rescan),
                        (QKeySequence("Ctrl+O"), self.choose_folder),
                        (QKeySequence("Ctrl+Q"), self.close)):
            a = QAction(self)
            a.setShortcut(seq)
            a.triggered.connect(fn)
            self.addAction(a)

        self.load_disks()
        self.update_legend()
        self.update_nav()
        if start_path:
            QTimer.singleShot(100, lambda: self.start_scan(start_path))

    # ------------------------------------------------------------ discos --
    def load_disks(self):
        self.disks = disks.list_disks()
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 4, 4)
        lay.setSpacing(10)
        for d in self.disks:
            card = DiskCard(d)
            card.scanRequested.connect(self.scan_volume)
            lay.addWidget(card)
        others = disks.other_volumes(self.disks)
        if others:
            card = DiskCard(OtherVolumes(others), other=True)
            card.scanRequested.connect(self.scan_volume)
            lay.addWidget(card)
        if not self.disks and not others:
            lay.addWidget(QLabel("No se han encontrado discos (¿falta «lsblk»?)"))
        lay.addStretch()
        self.disk_area.setWidget(w)

    def scan_volume(self, vol):
        if vol.fstype == "swap":
            QMessageBox.information(self, "Swap", "Esta partición es memoria de intercambio (swap): "
                                    "no contiene archivos que analizar.")
            return
        if not vol.mountpoints:
            QMessageBox.information(
                self, "Partición sin montar",
                f"«{vol.title}» ({vol.path}) no está montada.\n\nMóntala desde tu gestor de archivos "
                f"o con «udisksctl mount -b {vol.path}» y pulsa ⟳ para actualizar.")
            return
        mp = choose_mountpoint(vol, self, QCursor.pos())
        if mp:
            self.start_scan(mp)

    def choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Elige la carpeta que quieres analizar",
                                             os.path.expanduser("~"))
        if d:
            self.start_scan(d)

    # ----------------------------------------------------------- escaneo --
    def start_scan(self, path):
        self.cancel_scan(wait=True)
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            QMessageBox.warning(self, "No es una carpeta", f"No se puede analizar «{path}».")
            return
        self.loc = disks.locate(path, self.disks)
        m, v, _ = self.loc
        self.expected = None
        if m and m.mountpoint == path:
            try:
                st = os.statvfs(path)
                self.expected = (st.f_blocks - st.f_bfree) * st.f_frsize
            except OSError:
                pass
        try:
            self.scanner = Scanner(path, disks.mountpoints(), self)
        except OSError as e:
            QMessageBox.warning(self, "Error", f"No se puede leer «{path}»:\n{e}")
            return
        self.scanner.progress.connect(self.on_progress)
        self.scanner.scanDone.connect(self.on_done)
        self.scan_root = self.scanner.root
        self.current = self.scan_root
        self.treemap.set_root(self.current)
        self.progress.setRange(0, 1000 if self.expected else 0)
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_btn.show()
        self.status.setText(f"Analizando {path}…")
        self.scanner.start()
        self.live_timer.start()
        self.update_nav()
        self.refresh_details()

    def cancel_scan(self, wait=False):
        if self.scanner and self.scanner.isRunning():
            self.scanner.cancel()
            if wait:
                self.scanner.wait()

    def rescan(self):
        if self.scan_root:
            target = self.current.path() if self.current else self.scan_root.path()
            root_path = self.scan_root.path()
            self.start_scan(root_path)
            self._pending_zoom = target

    def on_progress(self, nfiles, ndirs, nbytes, path):
        if self.sender() is not self.scanner:
            return
        txt = f"Analizando… {fmt_int(nfiles)} archivos · {fmt_int(ndirs)} carpetas · {fmt_size(nbytes)}"
        if path:
            txt += f"   <span style='color:#5f6679'>{html.escape(path[-70:])}</span>"
        self.status.setText(txt)
        if self.expected:
            self.progress.setValue(min(990, int(1000 * nbytes / max(1, self.expected))))

    def on_done(self, root, secs, cancelled):
        if root is not self.scan_root:
            return
        self.live_timer.stop()
        self.progress.hide()
        self.cancel_btn.hide()
        sc = self.sender()
        msg = (f"{'Análisis detenido' if cancelled else 'Análisis completado'} en "
               f"{secs:.1f} s · {fmt_int(root.files)} archivos · {fmt_int(root.dirs)} carpetas · "
               f"{fmt_size(root.size)}")
        if sc is not None and getattr(sc, "denied", 0):
            msg += (f" · <span style='color:#f0b447'>{fmt_int(sc.denied)} carpetas sin permiso "
                    f"de lectura (no contadas)</span>")
        self.status.setText(msg)
        target = getattr(self, "_pending_zoom", None)
        self._pending_zoom = None
        if target:
            n = self.find_node(target)
            if n is not None:
                self.current = n
                self.treemap.set_root(n)
        self.treemap.invalidate()
        self.refresh_details()
        self.update_nav()

    def live_refresh(self):
        self.treemap.invalidate()
        self.refresh_details()

    def find_node(self, path):
        root = self.scan_root
        rp = root.path()
        if path == rp:
            return root
        if not path.startswith(rp.rstrip("/") + "/"):
            return None
        n = root
        for part in path[len(rp.rstrip("/")) + 1:].split("/"):
            nxt = next((c for c in n.children or () if c.name == part and c.kind == "dir"), None)
            if nxt is None:
                return n
            n = nxt
        return n

    # -------------------------------------------------------- navegación --
    def zoom_to(self, node):
        if node is None or node.kind != "dir":
            return
        self.current = node
        self.treemap.set_root(node)
        self.update_nav()
        self.refresh_details()

    def go_up(self):
        if self.current is not None and self.current.parent is not None:
            self.zoom_to(self.current.parent)

    def update_nav(self):
        while self.crumbs.count():
            it = self.crumbs.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.up_btn.setEnabled(bool(self.current and self.current.parent))
        self.rescan_btn.setEnabled(self.scan_root is not None)
        if not self.current:
            lab = QLabel("Ninguna carpeta analizada")
            lab.setStyleSheet(f"color:{MUTED}")
            self.crumbs.addWidget(lab)
            self.crumbs.addStretch()
            return
        chain = [self.current] + list(self.current.ancestors())
        chain.reverse()
        if len(chain) > 7:
            chain = chain[:1] + [None] + chain[-5:]
        for i, n in enumerate(chain):
            if i:
                sep = QLabel("›")
                sep.setStyleSheet(f"color:{MUTED};padding:0 1px")
                self.crumbs.addWidget(sep)
            if n is None:
                self.crumbs.addWidget(QLabel("…"))
                continue
            last = i == len(chain) - 1
            b = QPushButton(n.name, objectName="crumbLast" if last else "crumb")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, node=n: self.zoom_to(node))
            self.crumbs.addWidget(b)
        self.crumbs.addStretch()

    def set_color_mode(self, idx):
        self.treemap.color_mode = "folder" if idx == 0 else "type"
        self.treemap.invalidate()
        self.update_legend()
        QTimer.singleShot(0, self.refresh_details)

    def set_depth(self, v):
        self.treemap.max_depth = v
        self.treemap.invalidate()

    def update_legend(self):
        if self.treemap.color_mode == "folder":
            self.legend_title.setText("CÓMO LEER EL MAPA")
            self.legend.setText(
                f"<span style='color:{MUTED}'>Cada cajita es una carpeta o archivo y su área es "
                "proporcional a lo que ocupa. Cada carpeta principal tiene su propio color; "
                "las cajas rayadas agrupan elementos diminutos.</span>")
            return
        self.legend_title.setText("LEYENDA")
        items = [(n, c) for n, c, _ in CATEGORIES] + [("Otros", OTHER_COLOR)]
        cells = [f"<td style='padding:1px 10px 1px 0'><span style='color:{c};font-size:12pt'>■</span> "
                 f"<span style='font-size:8.5pt'>{html.escape(n)}</span></td>" for n, c in items]
        rows = ["<tr>" + "".join(cells[i:i + 2]) + "</tr>" for i in range(0, len(cells), 2)]
        self.legend.setText("<table cellspacing=0>" + "".join(rows) + "</table>")

    # ----------------------------------------------------------- detalles --
    def refresh_details(self):
        n = self.current
        self.list.clear()
        if n is None:
            self.d_title.setText("—")
            self.d_path.setText("")
            self.d_size.setText("")
            self.d_stats.setText("Elige un disco, una partición o una carpeta para empezar.")
            return
        self.d_title.setText(html.escape(os.path.basename(n.path().rstrip("/")) or n.path()))
        self.d_path.setText(_breakable(n.path()))
        self.d_size.setText(fmt_size(n.size))
        stats = f"{fmt_int(n.files)} archivos · {fmt_int(n.dirs)} carpetas"
        m, v, _ = self.loc
        if v is not None and v.used:
            stats += f"<br>Ocupa el {fmt_pct(100 * n.size / v.used)} de lo usado en {html.escape(v.title)}"
            if v.total:
                stats += f" ({fmt_size(v.total - v.used)} libres)"
        purpose = self.purpose(n)
        if purpose:
            stats += f"<br><span style='color:#a9c1ff'>{html.escape(purpose)}</span>"
        if n.note:
            stats += f"<br><span style='color:#f0b447'>{html.escape(n.note)}</span>"
        self.d_stats.setText(stats)

        from .treemap import visible_children
        kids = visible_children(n)[:200]
        total = max(1, n.size)
        for k in kids:
            label = k.name + ("/" if k.kind == "dir" else "")
            it = QTreeWidgetItem([label, fmt_size(k.size) if k.kind != "mount" else "otro disco", ""])
            col = self.treemap.color_for(k)
            it.setIcon(0, _swatch(col))
            it.setData(0, Qt.ItemDataRole.UserRole, k)
            it.setData(2, Qt.ItemDataRole.UserRole, k.size / total)
            it.setData(2, Qt.ItemDataRole.UserRole + 1, col)
            it.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.list.addTopLevelItem(it)

    def on_list_hover(self, item, col):
        node = item.data(0, Qt.ItemDataRole.UserRole)
        self.treemap.set_highlight(node)
        InfoPopup.get().show_html(self.describe(node))

    def eventFilter(self, obj, ev):
        if obj is self.list.viewport() and ev.type() == ev.Type.Leave:
            self.treemap.set_highlight(None)
            InfoPopup.get().hide_popup()
        return super().eventFilter(obj, ev)

    def on_list_double(self, item, col):
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node.kind == "dir":
            InfoPopup.get().hide_popup()
            self.zoom_to(node)

    def on_list_menu(self, pos):
        item = self.list.itemAt(pos)
        if item:
            InfoPopup.get().hide_popup()
            self.context_menu(item.data(0, Qt.ItemDataRole.UserRole), self.list.viewport().mapToGlobal(pos))

    def on_treemap_hover(self, node):
        pass

    # ---------------------------------------------------------- tooltips --
    def purpose(self, node):
        if node.kind in ("group", "rest"):
            return None
        path = node.path()
        parts = []
        pkg = self.pacman.lookup(path)
        if pkg:
            parts.append(pkg)
        g = guess_purpose(path, node.name, node.kind == "dir")
        if g:
            parts.append(g)
        return " — ".join(parts) if parts else None

    def describe(self, node):
        k = node.kind
        kind_txt = {"dir": "Carpeta", "file": "Archivo", "group": "Grupo de archivos pequeños",
                    "rest": "Elementos demasiado pequeños para dibujarlos", "mount": "Punto de montaje"}[k]
        if k == "file":
            cat, col = file_category(node.name)
            kind_txt = f"Archivo · <span style='color:{col}'>{html.escape(cat)}</span>"
        rows = []
        if k == "mount":
            mp = node.path()
            mm, mv, md = disks.locate(mp, self.disks)
            rows.append(("Ubicación", _breakable(mp)))
            if mm:
                rows.append(("Contiene", f"{html.escape(mm.source)} ({html.escape(mm.fstype)})"))
            if md:
                rows.append(("Disco", f"{html.escape(md.model)} ({html.escape(md.path)})"))
            rows.append(("Nota", "Es otro sistema de archivos; no se incluye en este análisis. "
                                 "Elígelo en el panel izquierdo para analizarlo."))
        else:
            parent = node.parent
            size = f"<b>{fmt_size(node.size)}</b>"
            pct = []
            if parent is not None and parent.size:
                pct.append(f"{fmt_pct(100 * node.size / parent.size)} de «{html.escape(parent.name)}»")
            if self.current is not None and self.current is not parent and self.current.size:
                pct.append(f"{fmt_pct(100 * node.size / self.current.size)} de la vista")
            if (self.scan_root is not None and self.scan_root.size and self.scan_root is not parent
                    and self.scan_root is not self.current):
                pct.append(f"{fmt_pct(100 * node.size / self.scan_root.size)} del total")
            if pct:
                size += f" <span style='color:{MUTED}'>· " + " · ".join(pct) + "</span>"
            rows.append(("Tamaño", size))
            where = node.path() if k not in ("group", "rest") else node.parent.path()
            rows.append(("Ubicación" if k not in ("group", "rest") else "Dentro de", _breakable(where)))
            purpose = self.purpose(node)
            if purpose:
                rows.append(("Pertenece a", f"<span style='color:#a9c1ff'>{html.escape(purpose)}</span>"))
            if k in ("dir", "file"):
                rows.append(("Propietario", f"{html.escape(user_name(node.uid))} "
                                            f"<span style='color:{MUTED}'>(grupo {html.escape(group_name(node.gid))})</span>"))
            if k == "dir":
                rows.append(("Contenido", f"{fmt_int(node.files)} archivos · {fmt_int(node.dirs)} carpetas"))
            elif k in ("group", "rest"):
                rows.append(("Contenido", f"{fmt_int(node.count)} elementos"))
            if k in ("dir", "file") and node.mtime:
                rows.append(("Modificado", time.strftime("%d/%m/%Y %H:%M", time.localtime(node.mtime))))
            m, v, d = self.loc
            if v is not None:
                rows.append(("Partición", f"{html.escape(v.path)} · {html.escape(v.fs_name)} "
                                          f"<span style='color:{MUTED}'>(montada en {html.escape(m.mountpoint)})</span>"))
            elif m is not None:
                rows.append(("Volumen", f"{html.escape(m.source)} · {html.escape(m.fstype)} "
                                        f"<span style='color:{MUTED}'>(montado en {html.escape(m.mountpoint)})</span>"))
            if d is not None:
                rows.append(("Disco", f"{html.escape(d.model)} <span style='color:{MUTED}'>({html.escape(d.path)}, "
                                      f"{html.escape(d.kind_name)})</span>"))
            if node.note:
                rows.append(("Aviso", f"<span style='color:#f0b447'>{html.escape(node.note)}</span>"))
        body = "".join(
            f"<tr><td style='color:{MUTED};padding-right:12px;white-space:nowrap' valign='top'>{a}</td>"
            f"<td>{b}</td></tr>" for a, b in rows)
        hint = ""
        if k == "dir" and node is not self.current:
            hint = "Clic para entrar · clic derecho para más opciones"
        elif k in ("file", "dir"):
            hint = "Clic derecho para más opciones"
        title = node.name if k not in ("group", "rest") else node.name
        return (f"<div style='font-size:12.5pt;font-weight:600'>{html.escape(title)}</div>"
                f"<div style='color:{MUTED};margin-bottom:6px'>{kind_txt}</div>"
                f"<table cellspacing=0 cellpadding=2>{body}</table>"
                + (f"<div style='color:#7fa7ff;margin-top:6px'>{hint}</div>" if hint else ""))

    # -------------------------------------------------------- menú contextual --
    def context_menu(self, node, gpos):
        if node is None:
            return
        menu = QMenu(self)
        path = node.path()
        if node.kind == "dir" and node is not self.current:
            menu.addAction("Entrar en la carpeta", lambda: self.zoom_to(node))
        if self.current is not None and self.current.parent is not None:
            menu.addAction("Subir un nivel", self.go_up)
        menu.addSeparator()
        if node.kind == "file":
            menu.addAction("Abrir archivo", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
            menu.addAction("Mostrar en el gestor de archivos",
                           lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path))))
        else:
            menu.addAction("Abrir en el gestor de archivos",
                           lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        menu.addAction("Copiar ruta", lambda: QGuiApplication.clipboard().setText(path))
        if node.kind == "mount":
            menu.addAction("Analizar este volumen", lambda: self.start_scan(path))
        if node.kind == "dir":
            menu.addAction("Analizar solo esta carpeta", lambda: self.start_scan(path))
        if node.kind in ("dir", "file") and node.parent is not None:
            menu.addSeparator()
            menu.addAction("Mover a la papelera…", lambda: self.trash(node))
        menu.exec(gpos)

    def trash(self, node):
        path = node.path()
        if self.scanner and self.scanner.isRunning():
            QMessageBox.information(self, "Espera", "Espera a que termine el análisis antes de borrar.")
            return
        r = QMessageBox.question(
            self, "Mover a la papelera",
            f"¿Mover a la papelera «{node.name}»?\n\n{path}\n\nTamaño: {fmt_size(node.size)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        from PyQt6.QtCore import QFile
        res = QFile.moveToTrash(path)
        ok = res[0] if isinstance(res, tuple) else res
        if not ok:
            QMessageBox.warning(self, "No se pudo", f"No se ha podido mover a la papelera:\n{path}\n\n"
                                "Puede que no tengas permisos o que el disco no tenga papelera.")
            return
        parent = node.parent
        try:
            parent.children.remove(node)
        except ValueError:
            pass
        nf = node.files + (1 if node.kind == "file" else 0)
        nd = node.dirs + (1 if node.kind == "dir" else 0)
        for a in node.ancestors():
            a.size -= node.size
            a.files -= nf
            a.dirs -= nd
        if self.current is node or node in list(self.current.ancestors()):
            self.current = parent
            self.treemap.set_root(parent)
        self.treemap.invalidate()
        self.refresh_details()
        self.update_nav()
        self.status.setText(f"«{node.name}» movido a la papelera ({fmt_size(node.size)} liberados "
                            f"cuando vacíes la papelera).")

    def closeEvent(self, e):
        InfoPopup.get().hide_popup()
        self.cancel_scan(wait=True)
        super().closeEvent(e)


def dark_palette(app):
    app.setStyle("Fusion")
    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: "#11141b", QPalette.ColorRole.WindowText: "#dfe3ee",
        QPalette.ColorRole.Base: "#161a23", QPalette.ColorRole.AlternateBase: "#191d27",
        QPalette.ColorRole.Text: "#dfe3ee", QPalette.ColorRole.Button: "#1f2431",
        QPalette.ColorRole.ButtonText: "#e3e7f1", QPalette.ColorRole.Highlight: "#3a63d6",
        QPalette.ColorRole.HighlightedText: "#ffffff", QPalette.ColorRole.ToolTipBase: "#1d2230",
        QPalette.ColorRole.ToolTipText: "#e4e8f3", QPalette.ColorRole.PlaceholderText: "#6b7285",
        QPalette.ColorRole.Link: ACCENT,
    }
    for role, col in roles.items():
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)


def main():
    QGuiApplication.setDesktopFileName("discovista")
    app = QApplication(sys.argv)
    app.setApplicationName("DiscoVista")
    app.setApplicationVersion(__version__)
    dark_palette(app)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--version" in sys.argv:
        print(f"DiscoVista {__version__}")
        return 0
    w = MainWindow(args[0] if args else None)
    w.show()
    return app.exec()
