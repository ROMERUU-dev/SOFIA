# Banco de Comparacion

Este directorio sirve para comparar la salida del software legado contra la nueva version en Python.

La idea no es comparar opiniones sino evidencia:

- mismas especificaciones de entrada
- misma topologia si aplica
- mismo opamp si aplica
- mismo capacitor base si aplica
- netlist del legado
- netlist de la nueva version
- observaciones tecnicas

## Estructura recomendada

Cada caso vive en su propia carpeta:

- `case_001_lowpass_butterworth_sallen_tl082/`
- `case_002_lowpass_chebyshev_sallen_tl082/`
- `case_003_highpass_butterworth_sallen_tl082/`

Dentro de cada carpeta se recomienda guardar:

- `case.md`: ficha del caso
- `input.json`: entrada usada en la nueva version
- `result.json`: salida JSON de la nueva version
- `generated.cir`: netlist generado por la nueva version
- `legacy.cir`: netlist exportado por el software viejo
- `legacy_capture.json`: bitacora de la captura del software viejo (avisos, orden, Q, componentes)
- `simulation.json`: simulacion de ambos netlists contra la especificacion
- `notes.txt`: observaciones libres
- `comparison.json`: resumen automatico de comparacion
- `comparison.md`: resumen legible de comparacion

## Criterios de evaluacion

Cada caso debe marcarse con uno de estos estados:

- `equivalente`
- `cercano`
- `parcial`
- `no_equivalente`

## Que revisar

1. Orden del filtro
2. Numero de etapas
3. Q de cada etapa
4. Valores resistivos ideales
5. Valores resistivos comerciales
6. Uso de arreglos serie/paralelo
7. Modelo de opamp
8. Forma del netlist SPICE
9. Riesgos de realizacion

## Simulacion contra la especificacion

Comparar netlists componente por componente no dice si un filtro funciona. Por eso cada caso tambien se
simula con SPICE (`scripts/simulate_case.py`, LTspice o ngspice) y se revisa contra `input.json`:

- rizo en banda de paso <= `ap` (tolerancia por defecto 0.15 dB)
- atenuacion en banda de rechazo >= `as` (tolerancia por defecto 0.5 dB)

El mismo circuito se simula dos veces: con el modelo real del opamp y con un opamp ideal. Eso separa
los errores de diseno de las limitaciones del opamp. El resultado queda en `simulation.json` y en el
campo `diagnosis`:

- `funciona`: cumple con el modelo real
- `limitacion_del_opamp`: solo cumple con el opamp ideal (ancho de banda, Q muy alto, etc.)
- `error_de_diseno`: no cumple ni con el opamp ideal
- `no_simula`: el simulador no pudo resolver el circuito

El simulador se busca solo (LTspice en `Program Files`, o `ngspice` en el PATH). Para otra ruta usa
`--spice RUTA` o la variable `SOFIA_SPICE`.

## Flujo recomendado

1. Crear o actualizar el caso con `scripts/benchmark_case.py`.
2. Capturar `legacy.cir` del SOFIA original con `scripts/legacy_capture.py --sofia RUTA\Sofia.exe`
   (o a mano, ver `windows_capture.md`).
3. Revisar `legacy_capture.json`: avisos que mostro SOFIA y si genero netlist.
4. Ejecutar `scripts/simulate_case.py` para revisar ambos netlists contra la especificacion.
5. Ejecutar `scripts/compare_case.py` para generar `comparison.json`.
6. Llenar observaciones en `notes.txt` y ajustar el veredicto en `case.md`.
7. Ejecutar `scripts/run_benchmark_suite.py --skip-run` para actualizar `report.md`.

## Flujo Windows/Linux

- Windows: usar el SOFIA original como referencia y capturar `legacy.cir`.
- Linux/macOS/Windows moderno: ejecutar `sofia-modern` y los scripts del banco.
- Git: versionar cada carpeta de caso completa para preservar evidencia reproducible.

## Herramienta auxiliar

Puedes usar:

```bash
python3 scripts/benchmark_case.py --help
```

Ese script crea la carpeta del caso y guarda la salida de la nueva version automaticamente.

Para comparar un caso:

```bash
python3 scripts/compare_case.py docs/benchmark/case_001_lowpass_butterworth_sallen_tl082 --write-markdown
```

Para simular un caso contra su especificacion:

```bash
python3 scripts/simulate_case.py docs/benchmark/case_001_lowpass_butterworth_sallen_tl082
```

Para actualizar todos los casos (genera, simula, compara y escribe `report.md`):

```bash
python3 scripts/run_benchmark_suite.py
```

En Windows usa `python` o `py` en lugar de `python3`.
