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

## Flujo recomendado

1. Crear o actualizar el caso con `scripts/benchmark_case.py`.
2. Ejecutar el software viejo en Windows con la misma entrada.
3. Exportar o copiar el netlist viejo y guardarlo como `legacy.cir`.
4. Ejecutar `scripts/compare_case.py` para generar `comparison.json`.
5. Llenar observaciones en `notes.txt` y ajustar el veredicto en `case.md`.
6. Ejecutar `scripts/run_benchmark_suite.py --skip-run` para actualizar `report.md`.

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

Para actualizar todos los casos:

```bash
python3 scripts/run_benchmark_suite.py
```
