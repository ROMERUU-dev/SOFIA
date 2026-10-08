# Caso case_007_bandstop_butterworth_tow_thomas_tl082

## Estado

- estado: `needs_review`
- nuevo: `cumple`
- legado: `no_cumple`

## Objetivo

Comparar un bandstop butterworth en tow_thomas con TL082 entre SOFIA original y la version en Python, y revisar que cada uno cumpla la especificacion.

## Entrada

- kind: bandstop
- approx: butterworth
- frecuencias (Hz): fp1=600, fp2=1600, fs1=900, fs2=1100
- ap: 1 dB
- as: 40 dB
- topology: tow_thomas
- opamp: TL082
- cap: 1e-7
- resistor_series: E96
- allow_resistor_arrays: False
- auto_stage_capacitor: True

## Salida legado

- archivo: `legacy.cir`
- origen: SOFIA original (Sofia.exe, Version3.5) capturado con `scripts/legacy_capture.py`, tolerancia 5%
- orden: 8
- Q por etapa: [2.8388, 1.0859, 1.0859, 2.8388]
- avisos de SOFIA: ninguno
- simulacion: `no_cumple` (error_de_diseno): rizo 4.52 dB (limite 1), atenuacion 44.1 dB (minimo 40), ganancia 0.2 dB; con opamp ideal rizo 4.53 dB, atenuacion 44.2 dB
- observaciones: Butterworth rechaza banda sin escalar por epsilon (algoritmos.cpp:257-307): los bordes de banda caen a -3 dB en lugar de -1 dB; con opamp ideal el rizo es de ~4.5 dB. Ademas fuente de 5 V.

## Salida nueva

- archivo JSON: `result.json`
- archivo netlist: `generated.cir`
- orden: 8
- Q por etapa: [3.5053, 1.3792, 1.3792, 3.5053]
- simulacion: `cumple` (funciona): rizo 0.85 dB (limite 1), atenuacion 43.2 dB (minimo 40), ganancia 0.2 dB; con opamp ideal rizo 0.82 dB, atenuacion 43.2 dB
- avisos: ninguno

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: distintos (legado {'order': 8, 'q': [1.08588406098898, 1.08588411027855, 2.83884561611264, 2.83884623078153]}, nuevo {'order': 8, 'q': [1.3792325735613817, 1.379232573561382, 3.505261563765972, 3.505261563765974]})
- topologia: misma peticion (tow_thomas)
- opamp: TL082; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 15 V / 7.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa un solo resistor E96 (1%) por posicion, con margen de diseno y capacitor E12 elegido para que las resistencias caigan cerca de valores comerciales
- capacitores: el legado usa el capacitor pedido; el nuevo elige un valor E12 por etapa
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: el nuevo cumple la especificacion y el legado no
- que falta corregir: nada en el nuevo. En el legado: Butterworth rechaza banda sin escalar por epsilon (algoritmos.cpp:257-307): los bordes de banda caen a -3 dB en lugar de -1 dB; con opamp ideal el rizo es de ~4.5 dB. Ademas fuente de 5 V.
