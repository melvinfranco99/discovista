# Maintainer: melvinfranco99
pkgname=discovista
pkgver=1.0.0
pkgrel=1
pkgdesc="Explorador visual de discos, particiones y uso de espacio (mapa de árbol interactivo)"
arch=('any')
url="https://github.com/melvinfranco99/discovista"
license=('MIT')
depends=('python' 'python-pyqt6' 'util-linux')
source=("$pkgname-$pkgver.tar.gz::$url/releases/download/v$pkgver/$pkgname-$pkgver.tar.gz")
sha256sums=('SKIP')

package() {
  cd "$pkgname-$pkgver"
  install -d "$pkgdir/usr/share/discovista"
  cp -r discovista "$pkgdir/usr/share/discovista/"
  find "$pkgdir" -name '__pycache__' -prune -exec rm -rf {} +
  install -Dm755 bin/discovista "$pkgdir/usr/bin/discovista"
  install -Dm644 data/discovista.desktop "$pkgdir/usr/share/applications/discovista.desktop"
  install -Dm644 data/discovista.svg "$pkgdir/usr/share/icons/hicolor/scalable/apps/discovista.svg"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
}
