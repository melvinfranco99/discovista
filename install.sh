#!/usr/bin/env bash
# Instalador de DiscoVista
#   ./install.sh              instala para tu usuario (~/.local), sin sudo
#   sudo ./install.sh --system   instala para todo el sistema (/usr/local)
#   ./install.sh --uninstall  desinstala (añade --system si lo instalaste así)
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE=user
ACTION=install
for a in "$@"; do
  case "$a" in
    --system) MODE=system ;;
    --uninstall) ACTION=uninstall ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
  esac
done

if [ "$MODE" = system ]; then
  PREFIX=/usr/local
else
  PREFIX="$HOME/.local"
fi
APPDIR="$PREFIX/share/discovista"
BIN="$PREFIX/bin/discovista"
DESKTOP="$PREFIX/share/applications/discovista.desktop"
ICON="$PREFIX/share/icons/hicolor/scalable/apps/discovista.svg"

if [ "$ACTION" = uninstall ]; then
  rm -rf "$APPDIR" "$BIN" "$DESKTOP" "$ICON"
  command -v update-desktop-database >/dev/null && update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
  echo "DiscoVista desinstalado de $PREFIX"
  exit 0
fi

# Dependencias
if ! command -v python3 >/dev/null; then
  echo "Falta python3. Instálalo con el gestor de paquetes de tu distribución." >&2; exit 1
fi
if ! python3 -c "import PyQt6.QtWidgets" 2>/dev/null; then
  echo "Falta PyQt6. Instálalo con uno de estos comandos:"
  echo "  Arch/Manjaro:  sudo pacman -S python-pyqt6"
  echo "  Debian/Ubuntu: sudo apt install python3-pyqt6"
  echo "  Fedora:        sudo dnf install python3-pyqt6"
  echo "  Otros:         pip install --user PyQt6"
  exit 1
fi
command -v lsblk >/dev/null || echo "Aviso: no se encuentra «lsblk» (paquete util-linux); no se mostrarán los discos."

install -d "$APPDIR"
rm -rf "$APPDIR/discovista"
cp -r "$SRC/discovista" "$APPDIR/"
find "$APPDIR" -name '__pycache__' -prune -exec rm -rf {} +
install -d "$(dirname "$BIN")"
sed "s|/usr/share/discovista|$APPDIR|" "$SRC/bin/discovista" > "$BIN"
chmod 755 "$BIN"
install -Dm644 "$SRC/data/discovista.desktop" "$DESKTOP"
sed -i "s|^Exec=discovista|Exec=$BIN|" "$DESKTOP"
install -Dm644 "$SRC/data/discovista.svg" "$ICON"
command -v update-desktop-database >/dev/null && update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q "$PREFIX/share/icons/hicolor" 2>/dev/null || true

echo "DiscoVista instalado en $PREFIX"
echo "Ejecútalo con: discovista   (o búscalo en el menú de aplicaciones)"
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) echo "Nota: $PREFIX/bin no está en tu PATH; usa $BIN" ;; esac
