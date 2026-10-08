# Caso case_007_bandstop_butterworth_tow_thomas_tl082

## Estado

- estado: `needs_review`
- nuevo: `no_cumple`
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
- resistor_series: E24
- allow_resistor_arrays: True
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
- Q por etapa: [3.2683, 1.2757, 1.2757, 3.2683]
- simulacion: `no_cumple` (limitacion_del_opamp): rizo 1.52 dB (limite 1), atenuacion 46.0 dB (minimo 40), ganancia 0.5 dB; con opamp ideal rizo 1.02 dB, atenuacion 45.6 dB
- avisos: ninguno

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: distintos (legado {'order': 8, 'q': [1.08588406098898, 1.08588411027855, 2.83884561611264, 2.83884623078153]}, nuevo {'order': 8, 'q': [1.2756843627300019, 1.2756843627300019, 3.2682811491572066, 3.268281149157207]})
- topologia: misma peticion (tow_thomas)
- opamp: TL082; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 15 V / 7.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa arreglos serie/paralelo E24 de hasta 2 resistencias
- capacitores: el legado usa el capacitor pedido; el nuevo lo ajusta por decadas segun el rango de resistencias
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: con el TL082 ninguno cumple; el nuevo cumple con opamp ideal (limitacion del opamp) y el legado no
- que falta corregir: nada de diseno en el nuevo; la desviacion viene del ancho de banda del TL082 (ver `simulation.json`). En el legado: Butterworth rechaza banda sin escalar por epsilon (algoritmos.cpp:257-307): los bordes de banda caen a -3 dB en lugar de -1 dB; con opamp ideal el rizo es de ~4.5 dB. Ademas fuente de 5 V.
