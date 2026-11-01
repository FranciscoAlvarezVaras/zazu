#!/bin/bash
# «Papeles: lo que vence» (lunes a las 9:30): qué documentos o trámites caducan en 30 días, en el chat de Papeles.
NOMBRE="Papeles" exec "$(dirname "$0")/asistente-rutina.sh" papeles "Esta rutina se lanza los lunes por la mañana; si hoy es otro día, usa la fecha de hoy. Revisa qué documentos, seguros, suscripciones o trámites de Fran caducan o vencen en los próximos 30 días, según lo que tienes guardado, y dile en una lista corta qué toca hacer y cuándo. Si no vence nada, dilo en una línea. No rellenes ni envíes nada: solo avisa."
