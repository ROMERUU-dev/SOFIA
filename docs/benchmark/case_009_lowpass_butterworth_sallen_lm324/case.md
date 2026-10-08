# Caso case_009_lowpass_butterworth_sallen_lm324

## Estado

- estado: `needs_review`
- nuevo: `cumple`
- legado: `no_cumple`

## Objetivo

Comparar un lowpass butterworth en sallen_key con LM324 entre SOFIA original y la version en Python, y revisar que cada uno cumpla la especificacion.

## Entrada

- kind: lowpass
- approx: butterworth
- frecuencias (Hz): fp=1000, fs=2000
- ap: 1 dB
- as: 40 dB
- topology: sallen_key
- opamp: LM324
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
- simulacion: `no_cumple` (error_de_diseno): rizo 1.55 dB (limite 1), atenuacion 44.2 dB (minimo 40), ganancia 16.8 dB; con opamp ideal rizo 1.53 dB, atenuacion 44.1 dB
- observaciones: El LM324 si polariza con 5 V. Falla solo por el rizo (~1.55 dB): cada resistencia se redondea a un solo valor de 5% y `Ajuste` compara distancias truncadas con `abs()` entero.

## Salida nueva

- archivo JSON: `result.json`
- archivo netlist: `generated.cir`
- orden: 8
- Q por etapa: [2.5629, 0.9, 0.6013, 0.5098]
- simulacion: `cumple` (funciona): rizo 0.84 dB (limite 1), atenuacion 41.7 dB (minimo 40), ganancia 16.8 dB; con opamp ideal rizo 0.86 dB, atenuacion 41.6 dB
- avisos: ninguno

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: iguales
- topologia: misma peticion (sallen_key)
- opamp: LM324; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 5 V / 2.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa un solo resistor E96 (1%) por posicion, con margen de diseno y capacitor E12 elegido para que las resistencias caigan cerca de valores comerciales
- capacitores: el legado usa el capacitor pedido; el nuevo elige un valor E12 por etapa
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: el nuevo cumple la especificacion y el legado no
- que falta corregir: nada en el nuevo. En el legado: El LM324 si polariza con 5 V. Falla solo por el rizo (~1.55 dB): cada resistencia se redondea a un solo valor de 5% y `Ajuste` compara distancias truncadas con `abs()` entero.
