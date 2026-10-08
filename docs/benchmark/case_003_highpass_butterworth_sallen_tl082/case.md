# Caso case_003_highpass_butterworth_sallen_tl082

## Estado

- estado: `needs_review`
- nuevo: `cumple`
- legado: `no_cumple`

## Objetivo

Comparar un highpass butterworth en sallen_key con TL082 entre SOFIA original y la version en Python, y revisar que cada uno cumpla la especificacion.

## Entrada

- kind: highpass
- approx: butterworth
- frecuencias (Hz): fp=2000, fs=1000
- ap: 1 dB
- as: 40 dB
- topology: sallen_key
- opamp: TL082
- cap: 1e-7
- resistor_series: E24
- allow_resistor_arrays: True
- auto_stage_capacitor: True

## Salida legado

- archivo: `legacy.cir`
- origen: SOFIA original (Sofia.exe, Version3.5) capturado con `scripts/legacy_capture.py`, tolerancia 5%
- orden: 8
- Q por etapa: [2.5629, 0.9, 0.6013, 0.5098]
- avisos de SOFIA: ninguno
- simulacion: `no_cumple` (error_de_diseno): rizo 25.99 dB (limite 1), atenuacion 38.1 dB (minimo 40), ganancia -253.7 dB; con opamp ideal rizo 5.65 dB, atenuacion 52.3 dB
- observaciones: Ademas de la fuente de 5 V, el pasa altas Butterworth usa la frecuencia de corte del pasa bajas (`wo = 2*pi*wp/eps^(1/n)`, algoritmos.cpp:114); con opamp ideal el borde de banda queda ~5.6 dB abajo.

## Salida nueva

- archivo JSON: `result.json`
- archivo netlist: `generated.cir`
- orden: 8
- Q por etapa: [2.5629, 0.9, 0.6013, 0.5098]
- simulacion: `cumple` (funciona): rizo 0.98 dB (limite 1), atenuacion 42.2 dB (minimo 40), ganancia 16.7 dB; con opamp ideal rizo 1.00 dB, atenuacion 42.3 dB
- avisos: ninguno

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: iguales
- topologia: misma peticion (sallen_key)
- opamp: TL082; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 15 V / 7.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa arreglos serie/paralelo E24 de hasta 2 resistencias
- capacitores: el legado usa el capacitor pedido; el nuevo lo ajusta por decadas segun el rango de resistencias
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: el nuevo cumple la especificacion y el legado no
- que falta corregir: nada en el nuevo. En el legado: Ademas de la fuente de 5 V, el pasa altas Butterworth usa la frecuencia de corte del pasa bajas (`wo = 2*pi*wp/eps^(1/n)`, algoritmos.cpp:114); con opamp ideal el borde de banda queda ~5.6 dB abajo.
