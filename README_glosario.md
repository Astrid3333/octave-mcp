# glosario_tecnico

Glosario técnico-científico multilingüe.

## Por qué el diseño cambió de "componer" a "guardar completo"

La idea original era: traducir el adjetivo, traducir el sustantivo,
reordenar según una regla por idioma (alemán/ruso/afrikáans antes,
español/portugués/árabe/hebreo/persa después). Eso se cae por dos lados:

1. **Chino y japonés no usan espacios.** Un tokenizador que corta por
   espacios no tiene con qué aislar "la palabra adjetivo" para moverla.
2. **Concordancia.** "Ideal" en alemán no es una palabra fija — es
   "ideales" (neutro), "idealer" (masculino), "ideale" (femenino/plural)
   según el sustantivo que acompañe. Lo mismo en ruso y en árabe/hebreo
   (que además concuerdan en definitud). Una regla de reordenamiento no
   resuelve eso — hace falta la forma flexionada correcta para cada
   término, no una plantilla genérica.

Confirmado además contra un caso real (`carpentries/glosario`, glosario
comunitario de cómputo/ciencia de datos, ~500KB, curado por traductores):
ninguna entrada multilingüe se compone por regla — cada idioma guarda el
término completo, tal como lo entregó quien tradujo. Es el patrón que
sigue este proyecto.

**Consecuencia práctica:** cada término es un string atómico por
idioma. Un idioma vacío en `terminos.json` significa "no verificado
todavía" — nunca se completa por inferencia desde otro idioma, ni por
regla de orden, ni por patrón de otro término.

## Estructura

- `idiomas.json` — metadata de cada idioma: estado (`base` /
  `pendiente_verificacion` / `excluido`), y el orden de adjetivo como
  dato *informativo* para quien verifique (no se usa para generar nada).
- `terminos.json` — los términos, cada uno con las traducciones
  verificadas que tiene hasta ahora.
- `glosario.py` — carga, consulta (`termino`), escritura
  (`agregar_traduccion`) y `reporte_cobertura()` para ver de un vistazo
  qué falta.

## Uso

```python
from glosario import termino, agregar_traduccion, reporte_cobertura

termino("gas_ideal", "es")   # "gas ideal"
termino("gas_ideal", "ru")   # None -> no verificado, no inventado

agregar_traduccion("presion", "pt", "pressão")

print(reporte_cobertura())
```

## Estado actual

- `es` / `en`: base, completos.
- `de`: `gas_ideal` verificado a modo de ejemplo del flujo de trabajo
  (`ideales Gas`) — el resto pendiente.
- `pt`, `af`, `ru`, `ar`, `he`, `fa`, `zh`, `ja`: estructura lista,
  todas las traducciones pendientes de verificación.
- `ps` (pastún), `arn` (mapudungún): excluidos, con motivo documentado
  en `idiomas.json`.

## Pendiente de decidir

- Fuente de verificación por idioma: para `zh` y `ja`, el comité
  nacional de terminología científica (中国 全国科学技术名词审定委员会)
  y los glosarios académicos del MEXT/JIS cumplen el rol que le faltó
  al mapudungún — cuerpos normativos con autoridad, no hablantes
  sueltos. Para los demás idiomas, falta definir la fuente equivalente
  antes de cargar traducciones en volumen.
