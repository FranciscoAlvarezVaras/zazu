#!/usr/bin/env bash
# Fabrica la app de Android de Zazu.
#   build.sh            → versión real (APK firmado) en ~/.local/share/zazu-android/zazu.apk, que el Hub ofrece en /zazu.apk (para instalar a mano)
#   build.sh aab        → Android App Bundle firmado en ~/.local/share/zazu-android/zazu.aab (esto es lo que se sube a Google Play)
#   build.sh debug      → versión de pruebas (apunta a http://localhost:8931: móvil por USB con `adb reverse tcp:8931 tcp:8931` hacia un Hub de pruebas)
# La llave de firma (~/.config/zazu-app) se crea la primera vez y NO se pierde: con otra llave el móvil no deja actualizar encima y habría que desinstalar.
# El APK y el AAB se firman con la MISMA llave (el bloque signingConfigs.release de app/build.gradle), así que ambos valen para actualizar encima.
set -euo pipefail
source "$HOME/.local/share/zazu-android/env.sh"
AQUI="$(cd "$(dirname "$0")" && pwd)"
CFG="$HOME/.config/zazu-app"
KS="$CFG/zazu.keystore"
if [ ! -f "$KS" ]; then
  umask 077
  mkdir -p "$CFG"
  python3 -c 'import secrets; print(secrets.token_urlsafe(24))' > "$CFG/keystore.pass"
  keytool -genkeypair -keystore "$KS" -alias zazu -keyalg RSA -keysize 2048 -validity 10950 \
    -storepass "$(cat "$CFG/keystore.pass")" -keypass "$(cat "$CFG/keystore.pass")" -dname "CN=Zazu, O=Fran, C=ES" >/dev/null 2>&1
  echo "llave de firma creada en $CFG (guárdala: está incluida en la copia de seguridad)"
fi
export ZAZU_KEYSTORE="$KS" ZAZU_KS_PASS="$(cat "$CFG/keystore.pass")"
cd "$AQUI"
MODO="${1:-release}"
if [ "$MODO" = "debug" ]; then
  gradle --no-daemon -q assembleDebug
  echo "$AQUI/app/build/outputs/apk/debug/app-debug.apk"
elif [ "$MODO" = "aab" ]; then
  # Android App Bundle para Google Play. bundleRelease usa el signingConfig.release
  # (la MISMA llave de ~/.config/zazu-app), así que el .aab sale ya firmado; no hace falta jarsigner.
  gradle --no-daemon -q bundleRelease
  DEST="$HOME/.local/share/zazu-android/zazu.aab"
  cp app/build/outputs/bundle/release/app-release.aab "$DEST"
  echo "listo: $DEST ($(du -h "$DEST" | cut -f1))"
  sha256sum "$DEST" | cut -d' ' -f1
else
  gradle --no-daemon -q assembleRelease
  APK="$HOME/.local/share/zazu-android/zazu.apk"
  # se copia a un temporal y se renombra: el Hub nunca sirve un APK a medio escribir
  cp app/build/outputs/apk/release/app-release.apk "$APK.tmp" && mv "$APK.tmp" "$APK"
  # zazu.json: versión LEÍDA del propio APK (aapt2) + sha256 + tamaño. El Hub lo da en /api/movil/apk-version y la app se actualiza sola.
  AAPT2="$(ls -d "$ANDROID_HOME"/build-tools/*/aapt2 | sort -V | tail -1)"
  "$AAPT2" dump badging "$APK" | head -1 | python3 -c '
import json, os, re, sys, hashlib
l = sys.stdin.read(); apk = sys.argv[1]
d = {"versionCode": int(re.search(r"versionCode=.(\d+)", l).group(1)), "versionName": re.search(r"versionName=.([^\x27]+)", l).group(1),
     "sha256": hashlib.sha256(open(apk, "rb").read()).hexdigest(), "tam": os.path.getsize(apk)}
open(apk[:-4] + ".json.tmp", "w").write(json.dumps(d)); os.replace(apk[:-4] + ".json.tmp", apk[:-4] + ".json"); print(d)' "$APK"
  echo "listo: $APK ($(du -h "$APK" | cut -f1))"
  sha256sum "$APK" | cut -d' ' -f1
fi
