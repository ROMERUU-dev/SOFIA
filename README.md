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
