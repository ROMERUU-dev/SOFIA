# Caso case_005_bandpass_butterworth_mfb_tl082

## Estado

- estado: `needs_review`
- nuevo: `cumple`
- legado: `no_cumple`

## Objetivo

Comparar un bandpass butterworth en mfb con TL082 entre SOFIA original y la version en Python, y revisar que cada uno cumpla la especificacion.

## Entrada

- kind: bandpass
- approx: butterworth
- frecuencias (Hz): fp1=800, fp2=1200, fs1=500, fs2=2000
- ap: 1 dB
- as: 30 dB
- topology: mfb
- opamp: TL082
- cap: 1e-8
- resistor_series: E96
- allow_resistor_arrays: False
- auto_stage_capacitor: True

## Salida legado

- archivo: `legacy.cir`
- origen: SOFIA original (Sofia.exe, Version3.5) capturado con `scripts/legacy_capture.py`, tolerancia 5%
- orden: 8
- Q por etapa: [6.5143, 2.6597, 2.6597, 6.5143]
- avisos de SOFIA: ninguno
- simulacion: `no_cumple` (error_de_diseno): rizo 13.09 dB (limite 1), atenuacion -63.8 dB (minimo 30), ganancia -458.0 dB; con opamp ideal rizo 5.99 dB, atenuacion 44.2 dB
- observaciones: En el MFB las entradas del opamp estan invertidas (`Xao1k 3k 100`, Esqueleto1.cpp:525-553): realimentacion positiva. Ademas fuente de 5 V. Con opamp ideal el rizo es de ~6 dB.

## Salida nueva

- archivo JSON: `result.json`
- archivo netlist: `generated.cir`
- orden: 8
- Q por etapa: [4.9582, 2.0028, 2.0028, 4.9582]
- simulacion: `cumple` (funciona): rizo 0.45 dB (limite 1), atenuacion 34.0 dB (minimo 30), ganancia 0.1 dB; con opamp ideal rizo 0.44 dB, atenuacion 34.0 dB
- avisos: ninguno

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: distintos (legado {'order': 8, 'q': [2.65968075231494, 2.65968085213198, 6.51431517730633, 6.51431656006484]}, nuevo {'order': 8, 'q': [2.00277895077042, 2.00277895077042, 4.958225532239518, 4.958225532239518]})
- topologia: misma peticion (mfb)
- opamp: TL082; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 15 V / 7.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa un solo resistor E96 (1%) por posicion, con margen de diseno y capacitor E12 elegido para que las resistencias caigan cerca de valores comerciales
- capacitores: el legado usa el capacitor pedido; el nuevo elige un valor E12 por etapa
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: el nuevo cumple la especificacion y el legado no
- que falta corregir: nada en el nuevo. En el legado: En el MFB las entradas del opamp estan invertidas (`Xao1k 3k 100`, Esqueleto1.cpp:525-553): realimentacion positiva. Ademas fuente de 5 V. Con opamp ideal el rizo es de ~6 dB.
