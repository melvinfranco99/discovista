"""Utilidades: formato de tamaños, propietarios, paquetes de pacman y
descripciones de "a qué pertenece" cada ruta."""
import grp
import os
import pwd
import sys
import threading
from functools import lru_cache


def fmt_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            if unit == "B":
                return f"{int(n)} B"
            s = f"{n:.1f}" if abs(n) < 100 else f"{n:.0f}"
            return s.replace(".", ",") + " " + unit
        n /= 1024


def fmt_int(n):
    return f"{int(n):,}".replace(",", ".")


def fmt_pct(x):
    if x >= 10:
        return f"{x:.0f} %"
    return f"{x:.1f} %".replace(".", ",")


@lru_cache(maxsize=4096)
def user_name(uid):
    if uid < 0:
        return "?"
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


@lru_cache(maxsize=4096)
def group_name(gid):
    if gid < 0:
        return "?"
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return str(gid)


class PacmanDB:
    """Mapa ruta -> paquete construido a partir de la base de datos local de
    pacman (se carga en segundo plano)."""

    BASE = "/var/lib/pacman/local"

    def __init__(self):
        self.owner = {}
        self.shared = {}
        self.ready = False
        self.available = os.path.isdir(self.BASE)
        if self.available:
            threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        owner, shared = {}, {}
        try:
            entries = os.listdir(self.BASE)
        except OSError:
            return
        for d in entries:
            name = sys.intern(d.rsplit("-", 2)[0])
            try:
                with open(os.path.join(self.BASE, d, "files"), encoding="utf-8", errors="replace") as fh:
                    data = fh.read()
            except OSError:
                continue
            start = data.find("%FILES%\n")
            if start < 0:
                continue
            end = data.find("\n\n", start)
            block = data[start + 8:end if end >= 0 else None]
            for line in block.split("\n"):
                if not line:
                    continue
                if line.endswith("/"):
                    p = "/" + line[:-1]
                    shared[p] = shared.get(p, 0) + 1
                    owner.setdefault(p, name)
                else:
                    owner["/" + line] = name
        self.owner, self.shared = owner, shared
        self.ready = True

    def lookup(self, path):
        if not self.ready:
            return None
        n = self.shared.get(path, 0)
        if n > 1:
            return f"compartida por {n} paquetes del sistema"
        pkg = self.owner.get(path)
        if pkg:
            return f"paquete «{pkg}» (pacman)"
        return None


HOME = os.path.expanduser("~")

# Reglas relativas a la carpeta personal (prefijo -> descripción)
HOME_RULES = {
    ".cache": "Caché de aplicaciones (normalmente se puede borrar)",
    ".local/share/Trash": "Papelera de reciclaje",
    ".local/share/Steam": "Steam (juegos y datos)",
    ".steam": "Steam",
    ".var/app": "Aplicaciones Flatpak (datos de usuario)",
    ".local/share/flatpak": "Flatpak (instalación de usuario)",
    ".mozilla": "Firefox (perfiles y caché)",
    ".config/google-chrome": "Google Chrome (perfil de usuario)",
    ".config/chromium": "Chromium (perfil de usuario)",
    ".config/BraveSoftware": "Brave (perfil de usuario)",
    ".config/Code": "Visual Studio Code (datos)",
    ".config/discord": "Discord",
    ".config/spotify": "Spotify",
    ".vscode": "Visual Studio Code (extensiones)",
    ".npm": "Caché de npm (Node.js)",
    ".nvm": "nvm (versiones de Node.js)",
    ".bun": "Bun (JavaScript)",
    ".cargo": "Rust / Cargo (paquetes y herramientas)",
    ".rustup": "Rust (toolchains instaladas)",
    "go": "Go (módulos y binarios)",
    ".gradle": "Gradle (caché de compilación Java/Android)",
    ".m2": "Maven (repositorio Java)",
    ".android": "Android (emuladores y configuración)",
    "Android": "Android SDK",
    ".ollama": "Ollama (modelos de IA)",
    ".local/share/containers": "Podman (imágenes y contenedores)",
    ".docker": "Docker (configuración de usuario)",
    ".wine": "Wine (programas de Windows)",
    ".local/share/lutris": "Lutris (juegos)",
    ".local/share/bottles": "Bottles (programas de Windows)",
    ".conda": "Conda (entornos de Python)",
    "anaconda3": "Anaconda (Python)",
    "miniconda3": "Miniconda (Python)",
    ".pyenv": "pyenv (versiones de Python)",
    ".local/lib": "Paquetes de Python instalados con pip --user",
    ".claude": "Claude Code (datos y sesiones)",
    ".thumbnails": "Miniaturas de imágenes (se pueden borrar)",
    ".local/share/Trash/files": "Archivos en la papelera",
    "Descargas": "Tus descargas", "Downloads": "Tus descargas",
    "Documentos": "Tus documentos", "Documents": "Tus documentos",
    "Imágenes": "Tus imágenes", "Pictures": "Tus imágenes",
    "Vídeos": "Tus vídeos", "Videos": "Tus vídeos",
    "Música": "Tu música", "Music": "Tu música",
    "Escritorio": "Tu escritorio", "Desktop": "Tu escritorio",
    ".config": "Configuración de aplicaciones",
    ".local/share": "Datos de aplicaciones",
    ".local/state": "Estado de aplicaciones",
    ".local/bin": "Programas instalados por el usuario",
}

# Carpetas cuyo primer nivel se describe con su nombre
HOME_DYNAMIC = {
    ".cache": "Caché de «{}»",
    ".config": "Configuración de «{}»",
    ".local/share": "Datos de «{}»",
    ".var/app": "App Flatpak «{}» (datos de usuario)",
}

SYSTEM_RULES = {
    "/var/cache/pacman/pkg": "Caché de paquetes de pacman (limpiable con «paccache -r» o «pacman -Sc»)",
    "/var/cache": "Cachés del sistema",
    "/var/log/journal": "Registros del sistema (journald) — limpiable con «journalctl --vacuum-size=200M»",
    "/var/log": "Registros (logs) del sistema",
    "/var/lib/flatpak": "Flatpak (aplicaciones del sistema)",
    "/var/lib/docker": "Docker (imágenes, contenedores y volúmenes)",
    "/var/lib/containers": "Podman (imágenes y contenedores)",
    "/var/lib/libvirt/images": "Discos de máquinas virtuales (libvirt)",
    "/var/lib/snapd": "Snap (paquetes)",
    "/var/lib/pacman": "Base de datos de pacman",
    "/var/lib/systemd/coredump": "Volcados de memoria de programas que fallaron (se pueden borrar)",
    "/var/tmp": "Archivos temporales persistentes",
    "/usr/lib/modules": "Módulos del kernel Linux",
    "/usr/lib/firmware": "Firmware de dispositivos",
    "/usr/lib": "Bibliotecas del sistema",
    "/usr/lib32": "Bibliotecas de 32 bits",
    "/usr/share/fonts": "Fuentes tipográficas",
    "/usr/share/icons": "Temas de iconos",
    "/usr/share/doc": "Documentación de programas",
    "/usr/share/locale": "Traducciones de programas",
    "/usr/share": "Datos compartidos de programas",
    "/usr/bin": "Programas del sistema (ejecutables)",
    "/usr/include": "Cabeceras para compilar (desarrollo)",
    "/usr/src": "Código fuente (kernel, módulos DKMS)",
    "/usr/local": "Programas instalados manualmente",
    "/usr": "Programas y bibliotecas del sistema",
    "/opt": "Programas de terceros (/opt)",
    "/home": "Carpetas personales de los usuarios",
    "/boot": "Arranque (kernel, initramfs y cargador)",
    "/efi": "Partición de arranque EFI",
    "/swapfile": "Archivo de intercambio (memoria swap)",
    "/tmp": "Archivos temporales",
    "/root": "Carpeta personal del administrador (root)",
    "/etc": "Configuración del sistema",
    "/srv": "Datos de servicios",
    "/lost+found": "Fragmentos recuperados por fsck",
    "/var": "Datos variables del sistema",
}

NAME_RULES = {
    "node_modules": "Dependencias de Node.js (se regeneran con «npm install»)",
    ".git": "Historial de un repositorio Git",
    "__pycache__": "Caché de Python (bytecode, se puede borrar)",
    ".venv": "Entorno virtual de Python",
    "venv": "Entorno virtual de Python",
    ".tox": "Entornos de pruebas de Python (tox)",
    ".gradle": "Caché de Gradle del proyecto",
    ".next": "Compilación de Next.js",
    "dist": "Archivos compilados / distribuibles",
    "build": "Archivos de compilación",
    ".idea": "Configuración de JetBrains IDE",
}

EXT_RULES = {
    ".iso": "Imagen de disco",
    ".img": "Imagen de disco",
    ".qcow2": "Disco de máquina virtual",
    ".vdi": "Disco de VirtualBox",
    ".vmdk": "Disco de VMware",
    ".gguf": "Modelo de IA",
    ".safetensors": "Modelo de IA",
    ".AppImage": "Aplicación AppImage",
}


def _prefix_match(path, prefix):
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def guess_purpose(path, name, is_dir):
    """Descripción heurística de a qué pertenece la ruta."""
    if name in NAME_RULES and is_dir:
        return NAME_RULES[name]
    if name.startswith(".Trash-") and is_dir:
        return "Papelera de este disco"
    if not is_dir:
        for ext, desc in EXT_RULES.items():
            if name.endswith(ext):
                return desc

    # Dentro de la carpeta personal
    if _prefix_match(path, HOME) and path != HOME:
        rel = path[len(HOME) + 1:]
        for base, tmpl in HOME_DYNAMIC.items():
            if rel.startswith(base + "/"):
                first = rel[len(base) + 1:].split("/", 1)[0]
                specific = None
                for k, v in HOME_RULES.items():
                    if k.startswith(base + "/") and _prefix_match(rel, k):
                        if specific is None or len(k) > len(specific[0]):
                            specific = (k, v)
                if specific:
                    return specific[1]
                return tmpl.format(first)
        best = None
        for k, v in HOME_RULES.items():
            if _prefix_match(rel, k) and (best is None or len(k) > len(best[0])):
                best = (k, v)
        if best:
            return best[1]
        return None
    if path == HOME:
        return "Tu carpeta personal"

    # Rutas del sistema
    m = None
    for k, v in SYSTEM_RULES.items():
        if _prefix_match(path, k) and (m is None or len(k) > len(m[0])):
            m = (k, v)
    if path.startswith("/opt/"):
        first = path[5:].split("/", 1)[0]
        return f"Programa de terceros «{first}» (/opt)"
    if path.startswith("/home/"):
        user = path[6:].split("/", 1)[0]
        return f"Carpeta personal del usuario «{user}»"
    if m:
        return m[1]
    return None


CATEGORIES = [
    # (nombre, color, extensiones)
    ("Vídeo", "#ef5d7a", {"mp4", "mkv", "avi", "mov", "webm", "flv", "wmv", "m4v", "mpg", "mpeg", "ts"}),
    ("Audio", "#f5a142", {"mp3", "flac", "wav", "ogg", "m4a", "aac", "opus", "wma"}),
    ("Imágenes", "#f2d04b", {"jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "tif", "tiff", "heic",
                             "raw", "cr2", "nef", "psd", "xcf", "ico", "avif"}),
    ("Documentos", "#59c98b", {"pdf", "doc", "docx", "odt", "xls", "xlsx", "ods", "ppt", "pptx", "odp",
                               "txt", "md", "epub", "csv", "rtf"}),
    ("Comprimidos e imágenes de disco", "#4bb8e8", {"zip", "tar", "gz", "xz", "zst", "bz2", "7z", "rar",
                                                     "iso", "img", "deb", "rpm", "appimage", "qcow2",
                                                     "vdi", "vmdk", "lz4", "tgz"}),
    ("Código", "#8f7bf0", {"py", "js", "ts", "jsx", "tsx", "c", "cpp", "h", "hpp", "rs", "go", "java",
                           "kt", "html", "css", "json", "xml", "sh", "yml", "yaml", "toml", "lua", "rb",
                           "php", "pyc"}),
    ("Programas y bibliotecas", "#d07be6", {"so", "a", "o", "bin", "exe", "dll", "jar", "ko", "zo",
                                            "efi", "wasm", "node"}),
    ("Bases de datos y modelos", "#5fd4c4", {"db", "sqlite", "sqlite3", "ldb", "gguf", "safetensors",
                                             "pt", "pth", "onnx", "ckpt", "pack", "idx"}),
]
OTHER_COLOR = "#8a93a8"
_EXT_MAP = {e: (name, color) for name, color, exts in CATEGORIES for e in exts}


def file_category(name):
    base = name.lower()
    if ".so." in base:
        return _EXT_MAP["so"]
    dot = base.rfind(".")
    if dot <= 0:
        return ("Otros", OTHER_COLOR)
    return _EXT_MAP.get(base[dot + 1:], ("Otros", OTHER_COLOR))
