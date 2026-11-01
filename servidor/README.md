# servidor — encender, apagar y vigilar la máquina

Equipo: Geekom A8 MAX (Ubuntu, 14 GB de RAM). Todo lo que corre es **servicios de usuario** de systemd (`systemctl --user …`).

## Qué hay

| Carpeta | Qué es |
|---|---|
| `bin/spirit` | El panel de mandos (`spirit estado`, `encender`, `reiniciar`, `logs`, `probar`, `guardar`, `foto`). |
| `bin/zv`, `bin/zgog` | Atajos a programas del servidor (`zv`: vigía de Zazu; `zgog`: Google). |
| `bin/nube-actualizar` | Actualiza Nextcloud (nube.holazazu.app) dentro de su rama y blinda Apache: `sudo bin/nube-actualizar` (o `--solo-apache`). Copia de seguridad en `/var/backups/nextcloud/<fecha>`, comprueba SHA256 y firma GPG del paquete y vuelve atrás solo si algo falla. El 2026-10-25 pasó de 34.0.4 a 34.0.5. |
| `bin/visor` | El visor de registros a pantalla completa (`visor`; `?` dentro para las teclas, `visor --md` para el resumen). Lo que lee lo junta `pagina-web/visor.py`; el resumen fijo está en `VISOR.md`. |
| `bin/respaldo-externo`, `bin/respaldo-pc` | Copias de seguridad al disco externo y al PC. |
| `unidades/` | Los servicios y temporizadores de systemd (`*.service`, `*.timer`) **de verdad**: `~/.config/systemd/user/<nombre>` es un enlace a este archivo. Se editan aquí. |
| `unidades/gestionadas-por-hermes/` | `hermes-gateway` y `hermes-dashboard`: los escribe Hermes al actualizarse; aquí solo hay una **copia para mirar**. No las edites aquí. |
| `panel-servidor/` | El panel de control web del servidor (puerto 8765; su propio git). Antes estaba en `~/Documentos/panel-servidor` (ahora enlace). |
| `cloudflared/` | `config.yml` es un enlace a la configuración real del túnel (`~/.cloudflared/config.yml`); `config.ingress.yml` es solo la tabla dominio → puerto. Las credenciales NO están aquí. |
| `servicios/` | Enlace a `~/Servicios` (Nextcloud, carpeta compartida, Open WebUI, red). Son datos y programas de terceros: solo para mirar. |

Los atajos de `~/.local/bin/` (`spirit`, `zv`, `zgog`, `visor`, `respaldo-*`) son enlaces a `bin/`.

## Encender todo / comprobar

```bash
spirit estado
spirit encender
```

Tras un apagón o reinicio del equipo todo debe subir solo. Si no:

```bash
loginctl show-user server -p Linger     # debe decir Linger=yes
spirit encender
```

(Si dice `Linger=no`, un administrador debe ejecutar `sudo loginctl enable-linger server`. Pídeselo a Claude, que te dará la orden exacta.)

## Los servicios importantes

| Servicio | Qué es | Reiniciar |
|---|---|---|
| `hermes-gateway` | El cerebro | `spirit reiniciar gateway` |
| `hermes-hub` | La página | `spirit reiniciar web` |
| `cloudflared-zazu` | El túnel a `holazazu.app` | `spirit reiniciar tunel` |
| `hermes-dashboard` | Panel de Hermes (puerto 9119, solo local) | `systemctl --user restart hermes-dashboard` |
| `panel-servidor` | Panel de control del servidor (puerto 8765, solo local) | `systemctl --user restart panel-servidor` |
| `syncthing` | Sincroniza con el móvil | `systemctl --user restart syncthing` |

Temporizadores: `zazu-vigia`, `zazu-bandeja`, `archivador`, `zazu-estado`, `zazu-exportar`, `zazu-propuestas`, `zazu-vigilante`, `hermes-actualizar`, `respaldo-*`.

Ver todos: `systemctl --user list-timers`.

## Si cambias una unidad de systemd

1. Edita el archivo de `~/Spirit/servidor/unidades/<nombre>.service` (el de `~/.config/systemd/user/` es un enlace a él).
2. `systemctl --user daemon-reload && systemctl --user restart <nombre>`.
3. `systemctl --user cat <nombre>` te enseña lo que systemd ha cargado.

(Para un servicio nuevo: crea el archivo aquí, enlázalo con `ln -s ~/Spirit/servidor/unidades/<nombre>.service ~/.config/systemd/user/` y actívalo con `systemctl --user enable --now <nombre>`.)

## Dominio y túnel

`holazazu.app` y `nube.holazazu.app` salen por Cloudflare (túnel `zazu`, configuración real en `~/.cloudflared/config.yml`, credenciales en `~/.cloudflared/`, **no copiadas aquí**). Si algún día cambias el dominio hay que tocar: la configuración del túnel, la URL de redirección de Google (OAuth) y los dominios de confianza de Nextcloud.

## Copias de seguridad

```bash
spirit foto                 # copia de Spirit en ~/Respaldos
respaldo-externo            # al disco externo
respaldo-pc                 # al PC
```
