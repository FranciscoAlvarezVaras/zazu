# zazu — la persona y sus oficios

Zazu es el asistente de Fran (por el gato abisinio). Aquí está todo lo que hace de forma propia, aparte de Hermes. (Entre el 10 y el 11 de octubre se llamó «Byte»; si algo antiguo dice «Byte», es lo mismo.)

## Qué hay

| Carpeta | Qué es | Cómo se activa |
|---|---|---|
| `vigia/` | **zv** — el vigía del correo: lee lo que llega, detecta facturas, plazos, suscripciones, entrevistas; guarda avisos y registro. | Temporizador `zazu-vigia` (cada 30 min en tu horario despierto). Orden: `zv status`, `zv --help` |
| `bandeja/` | **zb** — la bandeja de tareas/calendario: ordena, propone, archiva. | Temporizador `zazu-bandeja`. Orden: `zb` |
| `scripts/` | Los oficios sueltos: `zazu-dia.py` (tu día/semana), `zazu-rapido.py`, `archivador.py` (ordena archivos), `recoger-*.sh` (rutinas de la mañana/noche), `cerebro-ordenar.py` (ordena Obsidian), `estado-servidor.py`, `revisar-zazu.py`, respaldos y mantenimiento. | Rutinas de Hermes (`hermes cron list`) y temporizadores |
| `evals/` | Mini-pruebas de regresión (30 casos inventados) para correo y órdenes: `python3 evals/correr.py --modelo <modelo>`. | A mano, tras actualizar o cambiar de modelo |
| `scripts/ficha-de-fran.py`, `scripts/para-fran.py` | La ficha compartida (USER.md sin datos sensibles) y el buzón «para Fran» de los asistentes (aviso en la app + notificación), sin IA. | A mano / desde los asistentes |
| `skills-de-zazu/` | Enlace a las **habilidades** (`~/.hermes/skills/…`): cada una es una carpeta con un `SKILL.md` que enseña a Zazu a hacer algo. | Zazu las carga cuando hacen falta |

`scripts/` está plano a propósito: muchos scripts se importan entre sí con rutas relativas. No lo reorganices en subcarpetas sin probar.

## Estado de los vigías (2026-10-12)
`zv status`: WhatsApp y **correo** en modo activo (entrega real por WhatsApp); agenda en sombra. Bandeja (`zb`) y archivador en sombra. Para volver el correo a sombra: `zv modo correo sombra`.

## Rutinas sin IA (gratis, previsibles)

`zazu-dia.py`, `zazu-rapido.py` y las `recoger-*.sh` no llaman a ningún modelo: leen el calendario, el correo y tus datos y escriben el resultado. Se pueden ejecutar a mano:

```bash
python3 ~/Spirit/zazu/scripts/zazu-dia.py
zv status
zb
```

## Cómo aprende Zazu

Resumen: **memorias** (lo que sabe de ti), **habilidades** (lo que sabe hacer) y **el uso** (el vigía registra y propone; tú aceptas).

## Con cuidado

- Las claves y tokens de Google, WhatsApp, etc. no están aquí (viven en `~/.hermes/.env` y en el almacén de cada herramienta).
- Los datos del vigía (`avisos.db`, estado) están en `~/.hermes/state/`, no aquí.
- Si cambias un script que corre en una rutina, pruébalo a mano antes de dejarlo.
