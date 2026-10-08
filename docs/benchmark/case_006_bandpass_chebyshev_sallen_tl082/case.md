# Caso case_006_bandpass_chebyshev_sallen_tl082

## Estado

- estado: `needs_review`
- nuevo: `cumple`
- legado: `no_cumple`

## Objetivo

Comparar un bandpass chebyshev en sallen_key con TL082 entre SOFIA original y la version en Python, y revisar que cada uno cumpla la especificacion.

## Entrada

- kind: bandpass
- approx: chebyshev
- frecuencias (Hz): fp1=800, fp2=1200, fs1=500, fs2=2000
- ap: 1 dB
- as: 30 dB
- topology: sallen_key
- opamp: TL082
- cap: 1e-8
- resistor_series: E96
- allow_resistor_arrays: False
- auto_stage_capacitor: True

## Salida legado

- archivo: `legacy.cir`
- origen: SOFIA original (Sofia.exe, Version3.5) capturado con `scripts/legacy_capture.py`, tolerancia 5%
- orden: 6
- Q por etapa: [10.1049, 4.9568, 10.1049]
- avisos de SOFIA: ['menu_topologia']
- simulacion: `no_cumple` (error_de_diseno): rizo 0.00 dB (limite 1), atenuacion 0.0 dB (minimo 30), ganancia -600.0 dB
- observaciones: SOFIA avisa que Sallen-Key no soporta pasa banda, pero al cambiar el capacitor se reactiva Execute y genera un netlist que solo trae las lineas de los opamps (salida en cero).

## Salida nueva

- archivo JSON: `result.json`
- archivo netlist: `generated.cir`
- orden: 6
- Q por etapa: [7.4478, 3.6418, 7.4478]
- simulacion: `cumple` (funciona): rizo 0.72 dB (limite 1), atenuacion 34.8 dB (minimo 30), ganancia 0.5 dB; con opamp ideal rizo 0.71 dB, atenuacion 34.8 dB
- avisos: Etapa 1: Con Q = 7.45 este Sallen-Key pasa banda es muy sensible a la tolerancia de las resistencias y al ancho de banda del opamp; MFB o Tow-Thomas son más robustos.; Etapa 3: Con Q = 7.45 este Sallen-Key pasa banda es muy sensible a la tolerancia de las resistencias y al ancho de banda del opamp; MFB o Tow-Thomas son más robustos.

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: distintos (legado {'order': 6, 'q': [4.95676941988241, 10.104890951937, 10.1048925010178]}, nuevo {'order': 6, 'q': [3.6418146013594472, 7.44781895831603, 7.447818958316032]})
- topologia: misma peticion (sallen_key)
- opamp: TL082; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 15 V / 7.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa un solo resistor E96 (1%) por posicion, con margen de diseno y capacitor E12 elegido para que las resistencias caigan cerca de valores comerciales
- capacitores: el legado usa el capacitor pedido; el nuevo elige un valor E12 por etapa
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: el nuevo cumple la especificacion y el legado no
- que falta corregir: nada en el nuevo. En el legado: SOFIA avisa que Sallen-Key no soporta pasa banda, pero al cambiar el capacitor se reactiva Execute y genera un netlist que solo trae las lineas de los opamps (salida en cero).
