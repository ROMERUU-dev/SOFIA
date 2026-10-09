# SOFIA Filter Studio

Programa para diseñar filtros activos analogicos: de la especificacion a las etapas, los componentes
comerciales, el netlist SPICE, el esquematico y la placa. Es una version en Python del programa SOFIA
original; funciona en Windows, Linux, macOS y en el navegador.

- calculo de orden, epsilon, polos y etapas para Butterworth y Chebyshev I
- filtros `lowpass`, `highpass`, `bandpass` y `bandstop`
- topologias Sallen-Key, MFB, Tow-Thomas y Antoniou (GIC), elegidas por etapa segun su Q
- sintesis por etapa con un solo resistor comercial por posicion (E12, E24, E48 o E96; E96 por defecto)
- margen de diseno: el orden extra se reparte entre banda de paso y de rechazo, y el capacitor de cada
  etapa se elige de la serie E12 para que las resistencias caigan cerca de valores comerciales
- netlist SPICE con el modelo del opamp, listo para LTspice o ngspice (modelos en `resources/models/`)
- esquematico (SVG y proyecto de KiCad), lista de materiales y PCB ruteada con Gerber, en SMD o through-hole
- interfaz de escritorio con PySide6: calculo en vivo, grafica de respuesta con la especificacion marcada,
  etapas con sus componentes, esquematico y placa
- linea de comandos; arreglos serie/paralelo solo como opcion de ella (`--resistor-arrays`)

## Instaladores

Los instaladores estan en [Releases](https://github.com/ROMERUU-dev/SOFIA/releases/latest).

| Sistema | Archivo | Como se instala |
| --- | --- | --- |
| Windows | `SOFIA-Filter-Studio-<version>-windows.exe` | Un solo archivo, no se instala ni necesita Python. |
| Ubuntu y Debian | `sofia-filter-studio_<version>_amd64.deb` | `sudo apt install ./sofia-filter-studio_<version>_amd64.deb`. Queda en el menu de aplicaciones; se quita con `sudo apt remove sofia-filter-studio`. Ubuntu 22.04 o mas reciente, Debian 12 o mas reciente. |
| macOS | `SOFIA-Filter-Studio-<version>-macos-arm64.dmg` (Apple Silicon) o `-x86_64.dmg` (Intel) | Abrir el `.dmg` y arrastrar la app a Aplicaciones. |

Los tres abren la ventana de diseno; con argumentos funcionan como la linea de comandos (las mismas opciones
de `sofia`). El netlist que guardan ya trae el modelo del opamp, asi que se abre directo en LTspice o ngspice.

La app de macOS no esta firmada con una cuenta de desarrollador de Apple, asi que la primera vez macOS no la
deja abrir: en Ajustes del Sistema > Privacidad y seguridad aparece "Abrir de todos modos". Desde la terminal
tambien se puede: `xattr -dr com.apple.quarantine "/Applications/SOFIA Filter Studio.app"`.

Cada instalador se arma con PyInstaller en su propio sistema:

```bash
powershell -ExecutionPolicy Bypass -File packaging\windows\build_exe.ps1   # Windows: dist\*.exe
bash packaging/linux/build_deb.sh                                          # Ubuntu 22.04: dist/*.deb
bash packaging/macos/build_dmg.sh                                          # macOS: dist/*.dmg
```

Los tres prueban el programa empaquetado antes de terminar (abren la ventana, dibujan el esquematico y
rutean la placa). El flujo `.github/workflows/instaladores.yml` los arma en GitHub Actions (Windows,
Ubuntu 22.04, macOS Apple Silicon e Intel), instala el `.deb` en Ubuntu 22.04, 24.04 y 26.04 y en Debian 12
y 13 limpios, y deja los archivos como artefactos de la ejecucion; de ahi se suben al release. Se lanza a mano
desde la pestana Actions, con un push a la rama `instaladores` o con una etiqueta `v*`.

## Esquematico, materiales y PCB

A partir del mismo circuito que se simula (`circuit.py`), SOFIA arma la placa completa (`board.py`): las
etapas mas la alimentacion con desacoplo, la tierra virtual (divisor y seguidor), el acoplamiento de entrada
y salida, los opamps empaquetados en encapsulados dobles o cuadruples y las huellas SMD o through-hole.

- `schematic.py` dibuja el esquematico con una plantilla por topologia y lo exporta a SVG y a KiCad 8
  (`.kicad_sch`). Una revision de conectividad reconstruye las redes desde los cables y pines del dibujo y
  las compara con el circuito (`tests/test_schematic.py` lo hace para 80 disenos).
- `board.py` tambien genera la lista de materiales en CSV.
- `pcb.py` coloca los componentes (cada opamp con sus pasivos junto a los pines que usan), `router.py` rutea
  en dos capas (A* con vias y rip-up and reroute) y una revision de reglas mide el cobre real: separaciones,
  borde, barrenos y que cada red quede unida. Pistas de 0.3 mm, separacion de 0.25 mm, vias de 0.8/0.4 mm.
- `pcbfiles.py` escribe los Gerber (RS-274X con atributos X2, plano de tierra en la capa inferior), los
  barrenos Excellon, la placa de KiCad (`.kicad_pcb`) y el archivo de posiciones para ensamble SMD.
- `kicad.py` junta todo en un proyecto de KiCad (ZIP con `.kicad_pro`, esquematico, placa y la biblioteca de
  simbolos `SOFIA.kicad_sym`). Las redes de la placa llevan los nombres que KiCad deduce del esquematico y las
  huellas tienen los mismos pads que las de la biblioteca de KiCad, asi que el ERC, el DRC y la revision de
  paridad esquematico-placa de KiCad salen sin errores ni avisos.

## Sitio web

[romeruu-dev.github.io/SOFIA](https://romeruu-dev.github.io/SOFIA/) tiene tres partes:

- `/`: pagina de presentacion (`web/index.html`, `web/landing.css`, capturas en `web/img/`).
- `/app/`: la misma interfaz en una pagina estatica (`web/app/`). El paquete de Python corre en el
  navegador con [Pyodide](https://pyodide.org), asi que el calculo es identico al de la version de
  escritorio y no hay servidor. La primera visita descarga unos 6 MB; despues el navegador lo guarda. El
  enlace de la app lleva el diseno actual, de modo que se puede compartir un filtro con un link.
- `/SOFIA-manual.pdf`: manual de uso. La fuente es `docs/manual/manual.html`; el PDF se regenera con
  `python scripts/build_manual.py` (necesita Edge o Chrome) y se guarda en el repositorio.

El flujo `.github/workflows/pages.yml` corre las pruebas, arma el sitio y lo publica en GitHub Pages en
cada push a `main` (en Settings > Pages, la fuente debe ser "GitHub Actions"). Para probarlo en local:

```bash
python scripts/build_web.py
python -m http.server -d _site 8000
```

y abrir `http://localhost:8000`.

## Estructura

- `src/sofia_filter_studio/`: el programa (`forms.py`: validacion y vista que comparten la ventana de
  escritorio y la pagina web)
- `web/`: sitio web: presentacion en la raiz y la app en `web/app/` (el calculo lo hace el paquete de
  Python con Pyodide)
- `docs/manual/`: manual de uso (HTML fuente y el PDF generado)
- `packaging/`: instaladores de Windows, Linux y macOS, y el icono
- `resources/models/`: modelos SPICE de los opamps
- `scripts/`: sitio web, manual y simulacion de netlists
- `tests/`: pruebas

## Uso rapido

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[gui]"
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

Cada netlist usa una sola fuente con tierra virtual a la mitad: 5 V para LM324 y 15 V para los demas
opamps, que no polarizan con 5 V.

## Simular un netlist

`scripts/simulate.py` simula un netlist con LTspice o ngspice (ruta configurable con `SOFIA_SPICE`) y lo
revisa contra la especificacion, con el modelo real del opamp y con opamps ideales; asi separa un error de
diseno de una limitacion del opamp:

```bash
python scripts/simulate.py filtro.cir --kind lowpass --fp 1000 --fs 2000 --ap 1 --as 40
python scripts/simulate.py banda.cir --kind bandpass --fp 800 1200 --fs 500 2000 --ap 1 --as 30
```

Las pruebas de `tests/test_simulation.py` usan las mismas funciones para simular todas las combinaciones de
tipo de filtro, aproximacion y topologia, y se saltan si no hay simulador.
