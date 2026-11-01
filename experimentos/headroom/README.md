# Headroom (experimento, 2026-10-12)

**Qué es:** un proxy local (https://github.com/chopratejas/headroom, Apache 2.0, v0.40) que se pone entre Hermes y la API de Anthropic y **comprime el contexto** (salidas de herramientas, JSON, logs) antes de enviarlo, para gastar menos tokens. Lo hizo un ingeniero de Netflix; no es un producto de Netflix.

**Cómo está montado aquí**
- Instalado aislado en `venv/` (Python 3.13 con `uv`). Datos y registros en `datos/` (originales comprimidos, log del proxy).
- Escucha solo en `127.0.0.1:8787`. Telemetría apagada (`HEADROOM_BEACON=off`, `DO_NOT_TRACK=1`). Nada sale de casa salvo la llamada normal a Anthropic.
- Solo lo usa el perfil **`viajes`** (`model.base_url: http://127.0.0.1:8787` en su `config.yaml`). El resto de Zazu sigue hablando directo con Anthropic.
- Servicio: `servidor/unidades/headroom-proxy.service` (enlázalo y actívalo solo si el experimento convence).

**Cómo se mide:** el mismo plan de viaje (Lisboa, 3 días) con y sin proxy, comparando tokens (`hermes -p viajes --usage-file …`) y la calidad del itinerario.

**Para deshacer:** en `~/.hermes/profiles/viajes/config.yaml` volver a `base_url: https://api.anthropic.com` y parar el proxy (`systemctl --user disable --now headroom-proxy` o matar el proceso). Copia previa: `~/Respaldos/viajes-config.yaml.antes-headroom-*`.

## Cómo se conectó (lo difícil)
Tu acceso a Anthropic es por **suscripción (OAuth)**, no por clave de API. Hermes, al ver una dirección que no es `api.anthropic.com`, dejaba de usar la suscripción y mandaba una clave de API (401). Hicieron falta dos parches pequeños en el núcleo de Hermes (en `pagina-web/ops/parches-hermes/aplicar.py`, se reaplican tras cada actualización): un proxy en `127.0.0.1` no cuenta como «tercero» y conserva la identidad OAuth. Además la URL del perfil debe terminar en `/anthropic`: `model.base_url: http://127.0.0.1:8787/anthropic` (manteniendo `provider: anthropic`; un `custom_provider` no vale porque manda x-api-key).

## Resultados (2026-10-12, mismo plan de Lisboa, Sonnet 5.5)
| | Sin proxy (2 tandas) | Con Headroom |
|---|---|---|
| Tokens totales | 58 218 · 56 081 | **41 842** (−27 %) |
| Entrada sin caché | 8 · 8 | 6 695 |
| Caché leída | 27 404 · 27 404 | 15 060 |
| Caché escrita | 27 874 · 25 438 | 16 953 |
| Salida | 2 932 · 3 231 | 3 134 |
| **Coste aprox.** | **0,10 $ · 0,099 $** | **0,089 $ (−10 %)** |
| Calidad | itinerario completo | itinerario completo, 5 enlaces, sin marcas raras |

Lectura: Headroom quita unos 5 900 tokens de definiciones de herramientas por llamada (lo que dice su propio registro), pero al reescribir el principio de cada petición rompe parte de la caché de Anthropic (los 6 695 tokens «sin caché» salen de ahí). Resultado neto: **−27 % de tokens, −10 % de dinero**. Con una sola tanda por lado; hay ruido.

**Veredicto:** funciona y no estropea la respuesta, pero el ahorro es modesto y cuesta dos parches en el núcleo y un servicio más. Se queda **solo en `viajes`** como experimento (servicio `headroom-proxy`, activo al arrancar). Si en un mes el ahorro no compensa, se quita: restaurar `base_url` en el perfil y `systemctl --user disable --now headroom-proxy`.
