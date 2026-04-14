# Captura en Windows

Usa este flujo en el equipo con SOFIA original instalado.

## Preparacion

1. Instala SOFIA original y verifica que abre `Sofia.exe`.
2. Copia este repo o descarga la misma revision que esta en GitHub.
3. Abre cada carpeta `docs/benchmark/case_*`.
4. Usa `input.json` como fuente unica de parametros.

## Por cada caso

1. Captura en SOFIA original los parametros de `input.json`.
2. Selecciona la misma topologia y el mismo opamp cuando aplique.
3. Genera o abre el netlist desde SOFIA original.
4. Guarda ese netlist como `legacy.cir` dentro de la carpeta del caso.
5. Anota diferencias visibles en `notes.txt`.
6. Ejecuta:

```bash
python3 scripts/compare_case.py docs/benchmark/NOMBRE_DEL_CASO --write-markdown
```

## Actualizar resumen

Despues de capturar varios `legacy.cir`, ejecuta:

```bash
python3 scripts/run_benchmark_suite.py --skip-run
```

Esto actualiza `comparison.json`, `comparison.md` y `report.md` sin regenerar los netlists modernos.
