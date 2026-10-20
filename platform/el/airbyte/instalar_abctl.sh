#!/usr/bin/env bash
# Descarga abctl (versión fijada) en platform/el/airbyte/.bin y comprueba su SHA-256 con el
# fichero de sumas de la publicación. Solo para el perfil full.
set -euo pipefail
VERSION="v0.30.4"
cd "$(dirname "$0")"
so=$(uname -s | tr '[:upper:]' '[:lower:]')
case "$(uname -m)" in
  x86_64|amd64) arq=amd64 ;;
  aarch64|arm64) arq=arm64 ;;
  *) echo "Arquitectura no admitida: $(uname -m)" >&2; exit 1 ;;
esac
paquete="abctl-${VERSION}-${so}-${arq}.tar.gz"
base="https://github.com/airbytehq/abctl/releases/download/${VERSION}"
mkdir -p .bin/descarga
curl -fsSL "$base/$paquete" -o ".bin/descarga/$paquete"
curl -fsSL "$base/abctl_${VERSION#v}_checksums.txt" -o .bin/descarga/checksums.txt
cd .bin/descarga
if command -v sha256sum >/dev/null; then
  grep " $paquete\$" checksums.txt | sha256sum -c -
else
  grep " $paquete\$" checksums.txt | shasum -a 256 -c -
fi
tar -xzf "$paquete"
find . -type f -name abctl -exec install -m 0755 {} ../abctl \;
cd ../..
./.bin/abctl version
