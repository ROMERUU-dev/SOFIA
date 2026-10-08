# Caso case_004_highpass_chebyshev_sallen_tl082

## Estado

- estado: `needs_review`
- nuevo: `cumple`
- legado: `error_simulacion`

## Objetivo

Comparar un highpass chebyshev en sallen_key con TL082 entre SOFIA original y la version en Python, y revisar que cada uno cumpla la especificacion.

## Entrada

- kind: highpass
- approx: chebyshev
- frecuencias (Hz): fp=2000, fs=1000
- ap: 1 dB
- as: 40 dB
- topology: sallen_key
- opamp: TL082
- cap: 1e-7
- resistor_series: E96
- allow_resistor_arrays: False
- auto_stage_capacitor: True

## Salida legado

- archivo: `legacy.cir`
- origen: SOFIA original (Sofia.exe, Version3.5) capturado con `scripts/legacy_capture.py`, tolerancia 5%
- orden: 5
- Q por etapa: [5.5564, 1.3988]
- avisos de SOFIA: ninguno
- simulacion: `error_simulacion`: Simulator produced no raw file. Log:
Circuit: * Prepared for simulation from legacy.cir

Fatal Error: R13: Resistance must not be zero.
- observaciones: Orden impar: la etapa de primer orden sale con resistencias de 0 ohm (`r13`, `r23`) porque sus valores solo se calculan con el flujo del Integrador, que no corre al elegir Sallen-Key. SPICE rechaza el netlist.

## Salida nueva

- archivo JSON: `result.json`
- archivo netlist: `generated.cir`
- orden: 5
- Q por etapa: [1.2126, 4.7062]
- simulacion: `cumple` (funciona): rizo 0.64 dB (limite 1), atenuacion 42.6 dB (minimo 40), ganancia 15.6 dB; con opamp ideal rizo 0.69 dB, atenuacion 42.7 dB
- avisos: ninguno

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: distintos (legado {'order': 5, 'q': [1.39879200547903, 5.55644115215602]}, nuevo {'order': 5, 'q': [1.2125908920247528, 4.706248062374639]})
- topologia: misma peticion (sallen_key)
- opamp: TL082; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 15 V / 7.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa un solo resistor E96 (1%) por posicion, con margen de diseno y capacitor E12 elegido para que las resistencias caigan cerca de valores comerciales
- capacitores: el legado usa el capacitor pedido; el nuevo elige un valor E12 por etapa
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: el nuevo cumple la especificacion y el legado no
- que falta corregir: nada en el nuevo. En el legado: Orden impar: la etapa de primer orden sale con resistencias de 0 ohm (`r13`, `r23`) porque sus valores solo se calculan con el flujo del Integrador, que no corre al elegir Sallen-Key. SPICE rechaza el netlist.
