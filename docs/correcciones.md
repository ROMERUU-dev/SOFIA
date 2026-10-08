# Correcciones encontradas con el banco de pruebas

El banco ahora simula cada netlist con SPICE (LTspice XVII en Windows) y lo revisa contra su
especificacion. Con la version de GitHub (`dad1156`) solo **1 de 12** casos cumplia; despues de estas
correcciones **10 de 12** cumplen con el modelo real del opamp y **12 de 12** con opamp ideal (los 2
restantes son limitaciones del TL082, ver al final). El SOFIA original no cumple en ninguno (ver la
seccion del legado mas abajo).

| Caso | Python antes | Python despues | SOFIA original |
| --- | --- | --- | --- |
| 001 pasa bajas Butterworth Sallen-Key TL082 | salida muerta (-465 dB) | cumple | salida muerta (5 V) |
| 002 pasa bajas Chebyshev Sallen-Key TL082 | salida muerta, orden 8 | cumple, orden 5 | no simula (R = 0 ohm) |
| 003 pasa altas Butterworth Sallen-Key TL082 | salida muerta | cumple | salida muerta; corte mal calculado |
| 004 pasa altas Chebyshev Sallen-Key TL082 | no cumple | cumple | no simula (R = 0 ohm) |
| 005 pasa banda Butterworth MFB TL082 | salida en cero | cumple, 0 dB al centro | no cumple (entradas invertidas) |
| 006 pasa banda Chebyshev Sallen-Key TL082 | salida muerta | limitacion del opamp (Q = 10) | no soportado (si se fuerza, salida en cero) |
| 007 rechaza banda Butterworth Tow-Thomas TL082 | salida en cero | limitacion del opamp (> 15 kHz) | no cumple (rizo 4.5 dB) |
| 008 pasa bajas Butterworth MFB uA741 | salida en cero | cumple | no soportado (sin netlist) |
| 009 pasa bajas Butterworth Sallen-Key LM324 | cumple | cumple | no cumple (rizo 1.55 dB) |
| 010 pasa bajas Chebyshev Sallen-Key LM7171 | no simula | cumple | no simula (R = 0 ohm) |
| 011 pasa banda Butterworth Sallen-Key TL082 | salida muerta | cumple, 0 dB al centro | no soportado (si se fuerza, salida en cero) |
| 01 pasa bajas Butterworth (duplicado de 001) | salida muerta | cumple | salida muerta (5 V) |

## Errores de calculo

1. **Orden Chebyshev con la formula de Butterworth.** `_estimate_order` usaba `log` para ambas
   aproximaciones. Chebyshev usa `acosh`: el caso 002 pedia orden 5 y salia 8.
2. **Butterworth pasa banda / rechaza banda sin escalar por epsilon.** El prototipo quedaba normalizado
   a -3 dB, asi que los bordes de banda caian 3 dB en lugar de `ap`. Ahora se escala por
   `epsilon^(-1/n)` como ya se hacia en pasa bajas / pasa altas.
3. **Polos reales en filtros de banda muy anchos** se convertian en etapas de primer orden que no
   existen en pasa banda. Ahora se agrupan en etapas de segundo orden (Q < 0.5).
4. **`resistors.py` truena con valores menores a ~0.01 ohm** (`IndexError`, lista de candidatos vacia).

## Errores en los circuitos (netlist)

5. **Alimentacion de 5 V para todos los opamps.** TL082, uA741, LM318 y los National no polarizan con
   tierra virtual de 2.5 V (fuera de su rango de modo comun): el TL082 se quedaba saturado. Ahora se usa
   15 V con tierra virtual de 7.5 V; el LM324 conserva 5 V / 2.5 V.
6. **Nombres de subcircuito incorrectos** para LM7171, LM6164, LM6165 y LM6171 (los modelos los definen
   como `LM7171B/NS`, etc.). Con esos opamps el netlist no simulaba.
7. **Barrido AC fijo de 1 Hz a 500 Hz**, debajo de las frecuencias de todos los casos. Ahora va de
   `min(frecuencias)/10` a `max(frecuencias)*10`.
8. **Sallen-Key siempre dibujaba un pasa bajas**, aunque se pidiera pasa altas o pasa banda. Ahora hay
   pasa altas (C y R intercambiados) y pasa banda (realimentacion positiva, `K = 4 - sqrt(2)/Q`).
9. **MFB con las entradas del opamp invertidas** (realimentacion positiva) y **entrada en el nodo `10`,
   que no estaba conectado** a la fuente. Ademas el MFB pasa bajas usaba la topologia de pasa banda.
   Ahora hay MFB pasa bajas, pasa altas y pasa banda con sus ecuaciones exactas.
10. **Tow-Thomas sin inversor** (el lazo quedaba abierto salvo en pasa banda), salida tomada del
    integrador equivocado y la resistencia de muesca calculada pero nunca escrita. Ahora tiene pasa
    bajas, pasa banda, pasa altas y rechaza banda (con alimentacion directa `Cff`, `Rff`).
11. **Antoniou con entrada flotante** (nodo `10`) y `R5` con el valor de `Rq`. Ahora es el GIC completo
    con salida reforzada, para los cuatro tipos.
12. **Etapas de primer orden** (orden impar) tronaban con `KeyError` en Sallen-Key. Ahora cada topologia
    tiene su etapa de primer orden.
13. **Rechaza banda con Sallen-Key o MFB**: esas topologias no pueden poner un cero de transmision.
    La etapa se arma como Tow-Thomas y se avisa en `warnings`.
14. **Ganancia en pasa banda**: normalizar cada etapa a su propio pico deja la cascada en -18 a -25 dB al
    centro, porque las etapas estan escalonadas. Y el Sallen-Key pasa banda de componentes iguales tiene
    ganancia natural `K/(4-K)`, que crece con Q (el caso 011 daba +84 dB y se saturaria con cualquier
    senal). Ahora cada etapa tiene ganancia 1 en el centro de la banda: divisor de entrada en Sallen-Key,
    `R3` en MFB, `R1` en Tow-Thomas y amplificador de salida en Antoniou.
15. **Corriente de polarizacion.** Con LM7171 (3 uA) y resistencias de 150 kohm el offset de DC saturaba
    la cascada. La seleccion automatica de capacitor ahora limita la resistencia para que cada
    resistencia agregue a lo mas ~10 mV de offset, segun la corriente medida de cada modelo.
16. **Punto de operacion falso en SPICE.** El macro-modelo del TL082 admite una solucion de DC con la
    salida pegada al riel; el simulador a veces convergia ahi. El netlist ahora incluye `.nodeset` en
    las salidas de los opamps.

## Scripts del banco

17. `simulate_case.py` (nuevo) simula `generated.cir` y `legacy.cir`, con modelo real y con opamp ideal.
18. `run_benchmark_suite.py` genera, simula y compara; `report.md` trae el veredicto de cada version.
19. Los scripts usaban `Path.resolve()`, que en Windows puede convertir la ruta en una de mas de 260
    caracteres y fallar; ahora usan `Path.absolute()`.
20. El netlist incluye el modelo con ruta relativa a donde se guarda, para abrirlo directo en LTspice.

21. **Opamps que oscilan.** LM6164 y LM6165 son descompensados (estables solo con ganancia >= 5 y >= 25);
    en simulacion transitoria oscilan a 15-105 MHz en todas las topologias. LM7171 y LM6171 no asientan en
    MFB / Tow-Thomas. El diseno ahora lo avisa en `warnings`.

## Errores en SOFIA original (Sofia.exe, Version3.5)

El banco captura `legacy.cir` corriendo el `Sofia.exe` original con `scripts/legacy_capture.py` (mismos
clics que una persona, sin tocar controles deshabilitados). **Ningun caso del legado cumple la
especificacion**; 3 casos no son soportados por el legado. Las lineas son de los fuentes originales.

Confirmados por la simulacion del banco:

| Error | Donde | Casos |
| --- | --- | --- |
| Fuente de 5 V con tierra virtual de 2.5 V para todos los opamps (solo el LM324 polariza) | Esqueleto1.cpp:271, 497, 589, 801 | 001, 003, 005, 006, 007, 011, 01 |
| Barrido `.ac dec 100 1Hz 500Hz` fijo | Esqueleto1.cpp:272, 498, 590, 802 | todos |
| Orden impar: etapa de primer orden con resistencias de 0 ohm (solo se calculan en el flujo del Integrador) | Unit3.cpp:71-83, Unit5.cpp:184-195 | 002, 004, 010 |
| Pasa altas Butterworth con la frecuencia de corte del pasa bajas (`wo = 2*pi*wp/eps^(1/n)`) | algoritmos.cpp:114 | 003 (rizo 5.6 dB con opamp ideal) |
| Butterworth pasa banda / rechaza banda sin escalar por epsilon (bordes a -3 dB) | algoritmos.cpp:172-226, 257-307 | 007 (rizo 4.5 dB con opamp ideal) |
| MFB con entradas del opamp invertidas | Esqueleto1.cpp:525-553 | 005 |
| Valores comerciales de un solo resistor de 5% y comparacion con `abs()` entero (trunca distancias) | algoritmos.cpp:1634-1635 | 009 (rizo 1.55 dB con LM324) |
| Sallen-Key pasa banda: avisa que no lo soporta, pero al cambiar el capacitor deja continuar y el netlist solo trae los opamps | Unit3.cpp:345-352, Esqueleto1.cpp:331-428 | 006, 011 |

Encontrados revisando el codigo (no los cubre ningun caso del banco):

- Seleccion de orden en pasa banda / rechaza banda usando solo un borde de rechazo (`f4` o `f3`); ignora el
  otro y puede quedar corto (algoritmos.cpp:151, 236, 453, 522).
- Chebyshev pasa banda con Tow-Thomas / Antoniou / MFB: ganancia al centro de +6 a +11 dB porque la
  normalizacion solo vale para Butterworth (algoritmos.cpp:1344-1366, 1487).
- MFB pasa banda con `R2` aproximada (le falta el termino 1/R1): w0 sube hasta ~8% con Q bajo
  (algoritmos.cpp:1525-1531).
- `LM6171/NS` en el netlist, pero el modelo define `LM6171A/NS` (Esqueleto1.cpp:105).
- Arreglos de 10/20 elementos: un orden mayor a 20 solo avisa y sigue escribiendo fuera del arreglo.
- Valores entre 91 y 100 (por decada) siempre se redondean a 100 (algoritmos.cpp:1804).
- La sintesis lee el tipo de filtro, la aproximacion y la unidad (Hz/kHz/MHz) de la ventana principal en
  ese momento, no los del diseno: cambiar la unidad despues escala todas las resistencias.
- Antoniou de orden impar escribe el capacitor dos veces; Tow-Thomas de orden impar deja nodos flotando
  con LM7171/LM616x/LM6171; `.MC` mide la primera etapa en lugar de la salida.
- El editor de netlist pega el modelo del opamp a traves del portapapeles de Windows.

De estos, la version en Python ya traia los mismos errores 5, 7, 9 y el de Butterworth en banda (2). Los
de orden Chebyshev (1) y nombres de subcircuito (6) eran solo de la version en Python: el legado los tiene
bien (salvo LM6171).

El codigo del legado no se modifico: no hay compilador de C++ Builder 5 en este equipo para probar
cambios. La version en Python ya funciona correctamente en todos esos puntos.

## Limitaciones que quedan (no son errores de diseno)

- **006, Sallen-Key pasa banda con Q = 10 y TL082:** rizo de 1.22 dB contra 1 dB. Con opamp ideal cumple.
  El Sallen-Key pasa banda es muy sensible con Q alto; el programa ahora lo avisa y sugiere MFB o
  Tow-Thomas.
- **007, Tow-Thomas rechaza banda con TL082:** la ganancia sube +0.5 dB cerca de 16 kHz por el ancho de
  banda de 3 MHz del TL082. Con opamp ideal cumple.
