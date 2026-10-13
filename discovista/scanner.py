"""Escaneo del sistema de archivos en segundo plano.

El árbol se construye "en vivo": cada vez que se termina de listar una carpeta
su tamaño se propaga a todos sus antecesores, así la interfaz puede pintar el
mapa mientras el escaneo avanza.
"""
import heapq
import os
import stat
import time

from PyQt6.QtCore import QThread, pyqtSignal

# Archivos que se guardan individualmente por carpeta; el resto se agrupa.
TOP_FILES = 40


class Node:
    __slots__ = ("name", "parent", "kind", "size", "uid", "gid", "mtime",
                 "children", "files", "dirs", "count", "note")

    # kind: 'dir', 'file', 'group' (archivos pequeños agrupados), 'mount',
    #       'rest' (nodo virtual creado al dibujar)
    def __init__(self, name, parent, kind, size=0, uid=-1, gid=-1, mtime=0.0):
        self.name = name
        self.parent = parent
        self.kind = kind
        self.size = size
        self.uid = uid
        self.gid = gid
        self.mtime = mtime
        self.children = [] if kind == "dir" else None
        self.files = 0      # archivos contenidos (recursivo)
        self.dirs = 0       # subcarpetas contenidas (recursivo)
        self.count = 0      # para 'group'/'rest': número de elementos
        self.note = None    # p. ej. "sin permiso de lectura"

    def path(self):
        if self.kind in ("group", "rest"):
            return self.parent.path()
        parts = []
        n = self
        while n.parent is not None:
            parts.append(n.name)
            n = n.parent
        if not parts:
            return n.name
        parts.reverse()
        return os.path.join(n.name, *parts)

    def ancestors(self):
        n = self.parent
        while n is not None:
            yield n
            n = n.parent

    def root(self):
        n = self
        while n.parent is not None:
            n = n.parent
        return n

    def is_container(self):
        return self.kind == "dir"


class Scanner(QThread):
    progress = pyqtSignal(object, object, object, str)   # archivos, carpetas, bytes, ruta
    scanDone = pyqtSignal(object, float, bool)           # raíz, segundos, cancelado

    def __init__(self, path, mountpoints, parent=None):
        super().__init__(parent)
        self.path = os.path.abspath(path)
        self.skip_mounts = {m for m in mountpoints if m != self.path}
        self._cancel = False
        self.denied = 0
        st = os.lstat(self.path)
        self.root = Node(self.path, None, "dir", 0, st.st_uid, st.st_gid, st.st_mtime)

    def cancel(self):
        self._cancel = True

    def run(self):
        t0 = time.monotonic()
        last = t0
        root = self.root
        stack = [(root, self.path)]
        seen_inodes = set()
        nfiles = ndirs = 0
        join = os.path.join
        S_ISDIR, S_ISREG = stat.S_ISDIR, stat.S_ISREG

        while stack and not self._cancel:
            node, path = stack.pop()
            try:
                it = os.scandir(path)
            except OSError as e:
                node.note = "Sin permiso de lectura" if isinstance(e, PermissionError) else str(e.strerror or e)
                self.denied += 1
                continue

            files = []
            fsize = 0
            fcount = 0
            subdirs = []
            dir_inodes = 0
            with it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    mode = st.st_mode
                    if S_ISDIR(mode):
                        full = join(path, e.name)
                        if full in self.skip_mounts:
                            m = Node(e.name, node, "mount", 0, st.st_uid, st.st_gid, st.st_mtime)
                            node.children.append(m)
                            continue
                        dsz = st.st_blocks * 512
                        d = Node(e.name, node, "dir", dsz, st.st_uid, st.st_gid, st.st_mtime)
                        node.children.append(d)
                        subdirs.append((d, full))
                        dir_inodes += dsz
                    else:
                        if st.st_nlink > 1 and S_ISREG(mode):
                            key = (st.st_dev, st.st_ino)
                            if key in seen_inodes:
                                continue
                            seen_inodes.add(key)
                        sz = st.st_blocks * 512
                        fsize += sz
                        fcount += 1
                        files.append((sz, e.name, st.st_uid, st.st_gid, st.st_mtime))

            # Guardar los archivos más grandes y agrupar el resto
            if len(files) > TOP_FILES:
                top = heapq.nlargest(TOP_FILES, files, key=lambda f: f[0])
                rest = fsize - sum(f[0] for f in top)
                g = Node(f"{len(files) - TOP_FILES} archivos más pequeños", node, "group", rest)
                g.count = len(files) - TOP_FILES
                g.files = g.count
                node.children.append(g)
            else:
                top = files
            for sz, name, uid, gid, mt in top:
                f = Node(name, node, "file", sz, uid, gid, mt)
                node.children.append(f)

            # Propagar hacia arriba
            # (las subcarpetas ya incluyen el tamaño de su propio inodo)
            node.size += fsize + dir_inodes
            node.files += fcount
            node.dirs += len(subdirs)
            add = fsize + dir_inodes
            for a in node.ancestors():
                a.size += add
                a.files += fcount
                a.dirs += len(subdirs)

            nfiles += fcount
            ndirs += len(subdirs)
            stack.extend(subdirs)

            now = time.monotonic()
            if now - last > 0.12:
                last = now
                self.progress.emit(nfiles, ndirs, root.size, path)

        self.progress.emit(nfiles, ndirs, root.size, "")
        self.scanDone.emit(root, time.monotonic() - t0, self._cancel)
