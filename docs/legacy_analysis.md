# Analisis del Software Legado

## Identidad y proposito

El proyecto legado corresponde a una aplicacion de escritorio llamada `SOFIA`, compilada como `Sofia.exe` sobre Borland C++ Builder 5. Su objetivo principal es asistir el diseno preliminar de filtros analogicos activos:

- estima orden y parametros de aproximacion
- descompone el filtro en etapas
- propone topologias analogicas
- genera netlists SPICE
- permite editar y guardar dichos netlists
- incluye un flujo alterno para OTA

No es solo una calculadora de filtros. Es un flujo de sintesis semi asistida para llevar especificaciones electricas hasta una representacion SPICE editable.

## Stack del sistema original

- lenguaje: C++ Builder/VCL
- interfaz: formularios `.dfm`
- proyecto: `ProjecFiltro.bpr`
- ejecutable incluido: `Sofia.exe`
- calculo: `algoritmos.cpp/.h`
- generacion de netlists: `Esqueleto1.cpp/.h`
- modelos: carpeta `modelos/` con subcircuitos SPICE

## Modulos y ventanas

### `Unit1`

Formulario principal. Recibe:

- tipo de filtro: pasa bajas, pasa altas, pasa banda, rechaza banda
- aproximacion: Butterworth, Chebyshev y una eliptica incompleta
- frecuencias de paso y rechazo
- ripple/atenuacion
- rango de frecuencia: Hz, KHz, MHz, GHz

Desde aqui se disparan tres flujos:

- calculo de aproximacion
- visualizacion de respuesta
- sintesis por topologia o flujo OTA

### `Unit2`

Ventana de respuesta en frecuencia.

- grafica magnitud
- grafica fase
- permite escala logaritmica o lineal
- cambia forma de trazado entre pixel y linea
- usa un `TImage` como lienzo, no un motor de graficas especializado

### `Unit3`

Ventana de sintesis del circuito activo.

- seleccion de topologia
- seleccion de modelo de opamp
- definicion de capacitancia base y, en algunos casos, resistencia base
- validacion de valores resistivos pequenos
- acceso a generacion de netlist
- replot del filtro una vez elegida la realizacion

Topologias detectadas:

- Integrador
- Sallen-Key
- Antoniou
- MFB
- Tow-Thomas

Modelos de opamp detectados:

- LM324
- LM318
- uA741
- TL082
- LM7171
- LM6164
- LM6165
- LM6171

### `Unit5`

Editor de texto tipo scratchpad para netlists.

- abrir
- guardar
- guardar como
- imprimir
- copiar/pegar
- carga automatica del modelo SPICE y del netlist generado

### `Unit6`

Flujo OTA.

- recibe `C1`, `VDD`, `VSS`
- calcula `Gm`, `Gm4` y otros parametros
- permite abrir netlist OTA
- muestra una referencia grafica adicional

### `Unit7`

Ventana visual auxiliar para OTA.

### `Unit8`

Pantalla de carga.

### `Unit4`

Dialogo `About`.

## Funcionalidades implementadas

### Sintesis matematica

La clase `TAlgoritmos` concentra la logica numerica:

- `Butterworth(...)`
- `Chebyshev(...)`
- `Eliptico(...)`
- `Dibujar()`
- `DibujarFase()`
- `Antoniou(...)`
- `Sallen(...)`
- `MFB(...)`
- `Integrador(...)`
- `PA(...)`
- `Generar()`
- `OPAMP(...)`
- `OTA(...)`

Capacidades reales observadas:

- calculo de `epsilon`
- estimacion de orden
- polos y bicuadraticos desnormalizados
- calculo de `Q`
- formulas separadas por tipo de filtro
- exportacion de datos de respuesta a archivos `.txt`

### Generacion SPICE

La clase `TEsqueleto1` escribe netlists como:

- `Antonious.cir`
- `SallenKey.cir`
- `TowThomas.cir`
- `Mfb.cir`

La generacion mezcla:

- topologia elegida
- tipo de filtro
- aproximacion
- modelo de opamp
- valores ideales o Monte Carlo por tolerancia

### Edicion de netlist

El editor carga primero un modelo SPICE y luego concatena el netlist de la topologia elegida en el portapapeles y el memo. Es funcional, pero fragil.

## Hallazgos tecnicos importantes

### 1. Acoplamiento extremo UI-logica

El motor numerico escribe directamente sobre controles de formularios:

- `frmFiltro->LBQ`
- `frmFiltro->LBdesnor`
- `frmFiltro->Button1`

Eso impide pruebas unitarias reales, reutilizacion y automatizacion.

### 2. Estado global y mutable

La clase `TAlgoritmos` acumula decenas de arreglos y banderas como estado compartido:

- `Coef`, `Coeficiente`, `Calidad`, `Res1`, `Res2`, `Res3`
- `n`, `orden`, `d`, `h`

El diseno depende del orden de los clics de la interfaz.

### 3. Validaciones debiles

- se permiten conversiones directas `Text.ToDouble()` sin proteccion robusta
- hay mensajes, pero poco control de errores
- varias ramas solo deshabilitan botones

### 4. Portabilidad nula

- depende de VCL y Borland antiguo
- hay rutas absolutas de Windows
- nombres y flujos estan anclados a esa plataforma

### 5. Mantenibilidad baja

- formulas, UI y archivos estan mezclados
- nombres inconsistentes
- repeticion alta por modelo de opamp y topologia
- casi sin abstracciones reutilizables

### 6. Aproximacion eliptica incompleta

Existe codigo para `Eliptico`, pero el flujo esta claramente incompleto frente a Butterworth y Chebyshev.

## Evaluacion funcional

El software sigue una secuencia coherente para un entorno academico o de laboratorio:

1. capturar especificaciones
2. elegir aproximacion
3. observar respuesta
4. elegir topologia activa
5. escoger opamp o flujo OTA
6. generar netlist
7. editar/exportar

La idea del producto es valida. El problema no es el proposito, sino la deuda tecnica.

## Estrategia recomendada de modernizacion

### Mantener

- el dominio del problema
- el catalogo de topologias
- la compatibilidad con modelos SPICE
- el flujo de trabajo de especificacion a netlist

### Reemplazar

- VCL por una GUI moderna y portable
- estado global por modelos tipados
- formulas embebidas en formularios por servicios puros
- escritura ad hoc por generadores estructurados

### Nueva arquitectura propuesta

- `models.py`: tipos del dominio
- `design.py`: motor de sintesis
- `netlist.py`: plantillas y exportacion SPICE
- `cli.py`: automatizacion y uso batch
- `gui/`: cliente desktop portable

## Conclusion

`SOFIA` es un sintetizador de filtros activos con generacion SPICE, no una simple practica academica aislada. El rediseño correcto consiste en conservar el know-how del dominio y reemplazar casi por completo la estructura del software.
