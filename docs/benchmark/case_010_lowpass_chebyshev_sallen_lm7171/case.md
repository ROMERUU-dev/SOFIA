# Caso case_010_lowpass_chebyshev_sallen_lm7171

## Estado

- estado: `needs_review`
- nuevo: `cumple_con_tolerancia`
- legado: `error_simulacion`

## Objetivo

Comparar un lowpass chebyshev en sallen_key con LM7171 entre SOFIA original y la version en Python, y revisar que cada uno cumpla la especificacion.

## Entrada

- kind: lowpass
- approx: chebyshev
- frecuencias (Hz): fp=1000, fs=2000
- ap: 1 dB
- as: 40 dB
- topology: sallen_key
- opamp: LM7171
- cap: 1e-7
- resistor_series: E24
- allow_resistor_arrays: True
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
- Q por etapa: [5.5564, 1.3988]
- simulacion: `cumple_con_tolerancia` (funciona): rizo 1.04 dB (limite 1), atenuacion 45.3 dB (minimo 40), ganancia 16.2 dB; con opamp ideal rizo 1.02 dB, atenuacion 45.3 dB
- avisos: Stage 1 uses resistors up to 18200 ohm; the LM7171 bias current adds about 56 mV of DC offset. A larger capacitor would lower it.; Stage 2 uses resistors up to 12851 ohm; the LM7171 bias current adds about 40 mV of DC offset. A larger capacitor would lower it.

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: iguales
- topologia: misma peticion (sallen_key)
- opamp: LM7171; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 15 V / 7.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa arreglos serie/paralelo E24 de hasta 2 resistencias
- capacitores: el legado usa el capacitor pedido; el nuevo lo ajusta por decadas segun el rango de resistencias
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: el nuevo cumple la especificacion y el legado no
- que falta corregir: nada en el nuevo. En el legado: Orden impar: la etapa de primer orden sale con resistencias de 0 ohm (`r13`, `r23`) porque sus valores solo se calculan con el flujo del Integrador, que no corre al elegir Sallen-Key. SPICE rechaza el netlist.
