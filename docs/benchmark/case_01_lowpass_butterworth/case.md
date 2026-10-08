# Caso case_01_lowpass_butterworth

## Estado

- estado: `needs_review`
- nuevo: `cumple`
- legado: `no_cumple`

## Objetivo

Comparar un lowpass butterworth en sallen_key con TL082 entre SOFIA original y la version en Python, y revisar que cada uno cumpla la especificacion.

## Entrada

- kind: lowpass
- approx: butterworth
- frecuencias (Hz): fp=1000, fs=2000
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
- orden: 8
- Q por etapa: [2.5629, 0.9, 0.6013, 0.5098]
- avisos de SOFIA: ninguno
- simulacion: `no_cumple` (error_de_diseno): rizo 126.31 dB (limite 1), atenuacion -27.0 dB (minimo 40), ganancia -303.9 dB; con opamp ideal rizo 1.53 dB, atenuacion 44.1 dB
- observaciones: El TL082 no polariza con la fuente de 5 V y tierra virtual de 2.5 V que escribe SOFIA (salida muerta). Con opamp ideal el rizo sube a ~1.5 dB por redondear cada resistencia a un solo valor comercial de 5% (R = 1462.7 a 1500 ohm) y por el error de `abs()` en Ajuste.

## Salida nueva

- archivo JSON: `result.json`
- archivo netlist: `generated.cir`
- orden: 8
- Q por etapa: [2.5629, 0.9, 0.6013, 0.5098]
- simulacion: `cumple` (funciona): rizo 0.85 dB (limite 1), atenuacion 41.6 dB (minimo 40), ganancia 16.7 dB; con opamp ideal rizo 0.86 dB, atenuacion 41.6 dB
- avisos: ninguno

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: iguales
- topologia: misma peticion (sallen_key)
- opamp: TL082; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 15 V / 7.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa un solo resistor E96 (1%) por posicion, con margen de diseno y capacitor E12 elegido para que las resistencias caigan cerca de valores comerciales
- capacitores: el legado usa el capacitor pedido; el nuevo elige un valor E12 por etapa
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: el nuevo cumple la especificacion y el legado no
- que falta corregir: nada en el nuevo. En el legado: El TL082 no polariza con la fuente de 5 V y tierra virtual de 2.5 V que escribe SOFIA (salida muerta). Con opamp ideal el rizo sube a ~1.5 dB por redondear cada resistencia a un solo valor comercial de 5% (R = 1462.7 a 1500 ohm) y por el error de `abs()` en Ajuste.
