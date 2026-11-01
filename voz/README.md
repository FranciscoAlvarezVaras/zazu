# voz — hablar con Zazu

| Archivo | Qué hace |
|---|---|
| `stt.py` | De audio a texto (reconocimiento de voz). Lo usan los audios de WhatsApp y de la web. |
| `stt_servicio.py` | **Dictado rápido** (servicio `zazu-stt`, `127.0.0.1:8794`): Whisper «small» ya cargado en memoria, con un vocabulario de ayuda (Zazu, Fran, Hermes…). Lo usa el Hub para el micro del cuadro de escribir; si no está, el Hub cae a `stt.py`. Se descarga de la memoria tras 15 min sin uso y se vuelve a cargar al empezar a grabar. Pruebas: `cd voz && python3 -m unittest tests.test_stt_servicio`. |
| `tts.sh` | De texto a voz (Zazu habla): `tts.sh TEXTO.txt SALIDA.wav`. |
| `tts-kokoro.sh` | Alternativa a `tts.sh` con Kokoro (misma interfaz). Llama a `tts_kokoro.py`. |
| `kokoro-venv/` | Entorno aparte de Kokoro (1,3 GB con torch CPU; no en git). El modelo (313 MB) está en `~/.cache/huggingface`. |
| `muestras/` | La misma frase con Piper y con Kokoro, para comparar de oído (no en git). |
| `voces/` | Modelos de voz (pesados; no se guardan en git). |
| `venv/` | Entorno de Python de la voz (se puede recrear; no en git). |

`~/voz` es un enlace a esta carpeta, así los scripts antiguos siguen funcionando.

Prueba rápida de la voz:

```bash
echo "Hola Fran" > /tmp/hola.txt
bash ~/Spirit/voz/tts.sh /tmp/hola.txt /tmp/hola.wav     # texto → audio (voz Piper es_MX)
```

## Kokoro (alternativa a Piper, sin activar)

Adaptado de OpenJarvis (https://github.com/open-jarvis/openjarvis), Apache-2.0: en Kokoro la primera
letra de la voz es el idioma, y las españolas empiezan por «e»: `ef_dora` (mujer, la de por defecto),
`em_alex` y `em_santa` (hombre). Pronuncia en castellano (con «z» de España); Piper usa una voz mexicana.

Compara de oído `muestras/piper-es_MX-claude.wav`, `muestras/kokoro-ef_dora.wav` y `muestras/kokoro-em_alex.wav`
(la frase está en `muestras/frase.txt`). Tiempos en este PC (CPU, frase de ~6,5 s de audio):
Piper ≈ 1 s; Kokoro ≈ 6 s por llamada (3,6 s cargar el modelo + 1,6 s sintetizar), 15 s la primera vez.

**Para activarlo**, en `~/.hermes/config.yaml`, dentro de `tts.providers.piper-local`, cambia la línea

```yaml
      command: /home/server/voz/tts.sh {input_path} {output_path}
```
por
```yaml
      command: /home/server/voz/tts-kokoro.sh {input_path} {output_path}
```
y reinicia hermes-gateway. Para otra voz: `command: env KOKORO_VOZ=em_alex /home/server/voz/tts-kokoro.sh {input_path} {output_path}`.
Para volver a Piper, deshaz el cambio.

**Medidas del 30 de octubre de 2026** (6,3 s de voz, esta CPU): con `stt.py` y `large-v3-turbo` arrancando de cero, 15 s; con el modelo grande ya cargado, 8 s (más lento que lo que dura el audio); con `small` ya cargado, 2,8 s y acierta «Zazu». Para un texto que luego se revisa en el cuadro de escribir, `small` basta.
