# Caso case_011_bandpass_butterworth_sallen_tl082

## Estado

- estado: `needs_review`
- nuevo: `cumple`
- legado: `no_cumple`

## Objetivo

Comparar un bandpass butterworth en sallen_key con TL082 entre SOFIA original y la version en Python, y revisar que cada uno cumpla la especificacion.

## Entrada

- kind: bandpass
- approx: butterworth
- frecuencias (Hz): fp1=900, fp2=1100, fs1=600, fs2=1600
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
- Q por etapa: [13.0561, 5.3888, 5.3888, 13.0561]
- avisos de SOFIA: ['menu_topologia']
- simulacion: `no_cumple` (error_de_diseno): rizo 0.00 dB (limite 1), atenuacion 0.0 dB (minimo 40), ganancia -600.0 dB
- observaciones: SOFIA avisa que Sallen-Key no soporta pasa banda, pero al cambiar el capacitor se reactiva Execute y genera un netlist que solo trae las lineas de los opamps (salida en cero).

## Salida nueva

- archivo JSON: `result.json`
- archivo netlist: `generated.cir`
- orden: 8
- Q por etapa: [9.6675, 3.9785, 3.9785, 9.6675]
- simulacion: `cumple` (funciona): rizo 0.96 dB (limite 1), atenuacion 45.4 dB (minimo 40), ganancia 0.8 dB; con opamp ideal rizo 0.97 dB, atenuacion 45.3 dB
- avisos: Etapa 1: Con Q = 9.67 este Sallen-Key pasa banda es muy sensible a la tolerancia de las resistencias y al ancho de banda del opamp; MFB o Tow-Thomas son más robustos.; Etapa 4: Con Q = 9.67 este Sallen-Key pasa banda es muy sensible a la tolerancia de las resistencias y al ancho de banda del opamp; MFB o Tow-Thomas son más robustos.

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: distintos (legado {'order': 8, 'q': [5.38884900104616, 5.38884919787753, 13.0561406715818, 13.0561434311882]}, nuevo {'order': 8, 'q': [3.9784768844526477, 3.978476884452648, 9.667521376850477, 9.667521376850479]})
- topologia: misma peticion (sallen_key)
- opamp: TL082; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 15 V / 7.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa un solo resistor E96 (1%) por posicion, con margen de diseno y capacitor E12 elegido para que las resistencias caigan cerca de valores comerciales
- capacitores: el legado usa el capacitor pedido; el nuevo elige un valor E12 por etapa
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: el nuevo cumple la especificacion y el legado no
- que falta corregir: nada en el nuevo. En el legado: SOFIA avisa que Sallen-Key no soporta pasa banda, pero al cambiar el capacitor se reactiva Execute y genera un netlist que solo trae las lineas de los opamps (salida en cero).
