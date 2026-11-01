#!/usr/bin/env bash
# Rutina semanal SIN IA: avisa a Fran solo si hay cambios IMPORTANTES en lo que manda sobre Zazu (SOUL, hook, plugins, rutinas, permisos).
# Los cambios de memoria o scripts (REVISAR) no molestan: se ven cuando se le pregunta a Zazu «¿ha cambiado algo?».
set -u
out=$(/usr/bin/python3 "$HOME/.hermes/skills/productivity/vigilar-persistencia/scripts/vigilar_persistencia.py" 2>&1) || { echo "⚠ El vigilante de cambios de Zazu falló. Mira: python3 ~/.hermes/skills/productivity/vigilar-persistencia/scripts/vigilar_persistencia.py"; exit 0; }
case "$out" in
  *"IMPORTANTE ("*) printf '🛡 Zazu: cambios importantes desde la última revisión\n%s\n' "$(printf '%s\n' "$out" | sed -n '/^IMPORTANTE/,/^REVISAR/p' | grep -v '^REVISAR' | head -14)"
                    echo "Pregúntame «¿ha cambiado algo en Zazu?» y lo revisamos; si son cambios tuyos, dímelo y los doy por buenos." ;;
  *) : ;;   # sin cambios importantes: no se manda nada
esac
