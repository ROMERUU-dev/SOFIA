# Caso case_008_lowpass_butterworth_mfb_ua741

## Estado

- estado: `legacy_unsupported`
- nuevo: `cumple`
- legado: `no_soportado`

## Objetivo

Comparar un lowpass butterworth en mfb con uA741 entre SOFIA original y la version en Python, y revisar que cada uno cumpla la especificacion.

## Entrada

- kind: lowpass
- approx: butterworth
- frecuencias (Hz): fp=1000, fs=2000
- ap: 1 dB
- as: 40 dB
- topology: mfb
- opamp: uA741
- cap: 1e-7
- resistor_series: E96
- allow_resistor_arrays: False
- auto_stage_capacitor: True

## Salida legado

- archivo: no hay (SOFIA no genera netlist)
- origen: SOFIA original (Sofia.exe, Version3.5) capturado con `scripts/legacy_capture.py`, tolerancia 5%
- orden: 8
- Q por etapa: [2.5629, 0.9, 0.6013, 0.5098]
- avisos de SOFIA: ['menu_topologia']
- simulacion: sin netlist
- observaciones: SOFIA no soporta MFB pasa bajas: avisa y no genera netlist.

## Salida nueva

- archivo JSON: `result.json`
- archivo netlist: `generated.cir`
- orden: 8
- Q por etapa: [2.5629, 0.9, 0.6013, 0.5098]
- simulacion: `cumple` (funciona): rizo 0.81 dB (limite 1), atenuacion 41.4 dB (minimo 40), ganancia 0.0 dB; con opamp ideal rizo 0.84 dB, atenuacion 41.2 dB
- avisos: ninguno

## Comparacion

- archivo automatico: `comparison.json`
- orden y Q: iguales
- topologia: misma peticion (mfb)
- opamp: uA741; el legado alimenta con 5 V y tierra virtual de 2.5 V, el nuevo con 15 V / 7.5 V
- resistencias: el legado redondea cada una a un valor de 5%; el nuevo usa un solo resistor E96 (1%) por posicion, con margen de diseno y capacitor E12 elegido para que las resistencias caigan cerca de valores comerciales
- capacitores: el legado usa el capacitor pedido; el nuevo elige un valor E12 por etapa
- netlist: estructura distinta (nodos y conteo de componentes no coinciden), ver `comparison.md`
- comportamiento esperado: cumplir rizo <= ap y atenuacion >= as en la simulacion AC

## Conclusion

- veredicto: no_equivalente: el legado no soporta este caso
- que falta corregir: nada en el nuevo. En el legado: SOFIA no soporta MFB pasa bajas: avisa y no genera netlist.
