# SOFIA Filter Studio

Reescritura moderna en Python del software legado `SOFIA`, originalmente construido en Borland C++ Builder para sintesis preliminar de filtros analogicos.

Esta base ya deja resueltos los puntos que mas penalizaban al sistema anterior:

- arquitectura separada entre dominio, CLI y GUI
- compatibilidad multiplataforma con Python 3.11+ en Windows, Linux y macOS
- entrada moderna por linea de comandos
- GUI inicial de escritorio con `tkinter`
- calculo de orden, epsilon, polos y etapas para Butterworth y Chebyshev I
- soporte para filtros `lowpass`, `highpass`, `bandpass` y `bandstop`
- sintesis inicial por etapa con ajuste de resistencias a series comerciales
- opcion de arreglos resistivos serie/paralelo para aproximar mejor valores objetivo
- generacion inicial de netlists SPICE con comentarios estructurados
- preservacion de modelos SPICE heredados en `resources/models/`

## Ejecutable para Windows

En [Releases](https://github.com/ROMERUU-dev/SOFIA/releases) esta `SOFIA-Filter-Studio.exe`: un solo
archivo, no necesita Python. Al abrirlo muestra la ventana de diseno; el netlist que guarda ya trae el
modelo del opamp incluido, asi que se abre directo en LTspice o ngspice.

Para generarlo desde el codigo (requiere Python 3.11+ de python.org, con tkinter):

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_exe.ps1
```

El resultado queda en `dist\SOFIA-Filter-Studio.exe`.

## Estructura

- `docs/legacy_analysis.md`: analisis funcional y tecnico del software original
- `src/sofia_filter_studio/`: nueva implementacion
- `resources/models/`: modelos `.cir` heredados para migracion
- `tests/`: pruebas base del motor de calculo

## Uso rapido

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
sofia --kind lowpass --approx butterworth --fp 1000 --fs 2000 --ap 1 --as 40
sofia-gui
```

En Windows (PowerShell) se activa con `.venv\Scripts\Activate.ps1`. Sin instalar nada tambien funciona
desde la raiz del repo:

```powershell
$env:PYTHONPATH = "src"
python -m sofia_filter_studio --kind lowpass --approx butterworth --fp 1000 --fs 2000 --ap 1 --as 40 --netlist-out filtro.cir
python -m unittest discover -s tests
```

Las pruebas de `tests/test_simulation.py` simulan los netlists con SPICE y se saltan si no hay simulador
(LTspice o ngspice; ruta configurable con `SOFIA_SPICE`).

Cada netlist usa una sola fuente con tierra virtual a la mitad: 5 V para LM324 y 15 V para los demas
opamps, que no polarizan con 5 V. Las correcciones hechas con el banco estan en `docs/correcciones.md`.

## Estado de la migracion

La base nueva no intenta replicar al 100% la UI de VCL ni los acoplamientos del codigo original. En esta primera modernizacion:

- se migro el nucleo de sintesis y analisis a un dominio limpio
- se formalizaron modelos y topologias
- se preparo el terreno para seguir portando calculo de componentes comerciales, Monte Carlo y OTA

Lo que sigue despues de esta base:

1. portar ajuste a componentes comerciales y tolerancias
2. completar equivalencias exactas por topologia
3. agregar empaquetado nativo por sistema operativo
4. integrar graficas Bode y exportacion avanzada

## Banco de comparacion

Hay una base lista en:

- `docs/benchmark/`
- `scripts/benchmark_case.py`
- `scripts/simulate_case.py` (simula y revisa contra la especificacion)
- `scripts/run_benchmark_suite.py` (corre todo y escribe `docs/benchmark/report.md`)

Ejemplo:

```bash
python3 scripts/benchmark_case.py \
  --case-id case_01_lowpass_butterworth \
  --kind lowpass \
  --approx butterworth \
  --fp 1000 \
  --fs 2000 \
  --ap 1 \
  --as 40 \
  --topology sallen_key \
  --opamp TL082 \
  --cap 1e-7
```
