# Captura en Windows

El `legacy.cir` de cada caso se obtiene del SOFIA original (`Sofia.exe`). Hay dos formas.

## Automatica (recomendada)

`scripts/legacy_capture.py` abre `Sofia.exe` y hace los mismos clics que una persona: especificacion,
tipo, aproximacion, "Pole and Zero Generation", "Frequency Response", "Topologies", menu de topologia,
capacitor, "Execute", tolerancia de 5%, "Commercial Value", menu de opamp y "Netlist". Nunca presiona un
control deshabilitado, asi que cada netlist es uno que un usuario puede obtener.

```powershell
python scripts/legacy_capture.py --sofia C:\ruta\a\Version3.5\Sofia.exe
python scripts/run_benchmark_suite.py --skip-run
```

- `--case-id NOMBRE` captura solo ese caso (se puede repetir).
- Junto a `Sofia.exe` debe estar su carpeta `modelos\`; si no, se usan los modelos de `resources/models`.
- Mientras corre se abren y cierran ventanas de SOFIA. El editor de netlist de SOFIA copia el modelo del
  opamp por el **portapapeles de Windows**, asi que el portapapeles se sobrescribe.

Por cada caso se escriben:

- `legacy.cir`: el netlist tal como lo escribe SOFIA, con una linea `.include` del modelo al inicio (en
  SOFIA el editor pega el modelo desde el portapapeles).
- `legacy_capture.json`: estado (`capturado`, `capturado_con_aviso`, `sin_netlist`), los avisos que mostro
  SOFIA y en que paso, orden, epsilon y Q que muestra la ventana principal, y los valores de componentes.

Si SOFIA no genera netlist (por ejemplo MFB pasa bajas, que no soporta), el caso queda como
`legacy_unsupported` en el reporte.

## Manual

1. Abre `Sofia.exe` y captura los parametros de `input.json`:
   - Amax = `-ap`, Amin = `-as` (en SOFIA son negativos).
   - Pasa bajas / pasa altas: Fp y Fs.
   - Pasa banda: f1 = fs1, f2 = fp1, f3 = fp2, f4 = fs2.
   - Rechaza banda: f1 = fp1, f2 = fs1, f3 = fs2, f4 = fp2.
2. "Pole and Zero Generation", luego "Frequency Response" (es lo que habilita "Topologies").
3. En "Topologies" elige la topologia en el menu, escribe el capacitor y presiona "Execute".
4. Elige "5% of Tolerance", "Commercial Value", el opamp en el menu y "Netlist".
5. Guarda el texto del editor como `legacy.cir` dentro de la carpeta del caso.
6. Ejecuta `python scripts/run_benchmark_suite.py --skip-run`.
