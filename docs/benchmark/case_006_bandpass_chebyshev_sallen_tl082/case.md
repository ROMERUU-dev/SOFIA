# Caso case_006_bandpass_chebyshev_sallen_tl082

## Estado

- estado: `needs_review`
- nuevo: `no_cumple`
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
- resistor_series: E24
- allow_resistor_arrays: True
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
- Q por etapa: [10.1049, 4.9568, 10.1049]
- simulacion: `no_cumple` (limitacion_del_opamp): rizo 1.22 dB (limite 1), atenuacion 38.6 dB (minimo 30), ganancia -0.0 dB; con opamp ideal rizo 1.12 dB, atenuacion 38.6 dB
- avisos: At least one section has high Q; a Tow-Thomas or MFB realization may be safer than unity-gain Sallen-Key.; Stage 1: Q = 10.10 makes this Sallen-Key band-pass very sensitive to resistor tolerance and op amp bandwidth; MFB or Tow-Thomas is more robust.; Stage 3: Q = 10.10 makes this Sallen-Key band-pass very sensitive to resistor tolerance and op amp bandwidth; MFB or Tow-Thomas is more robust.

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

- veredicto: no_equivalente: con el TL082 ninguno cumple; el nuevo cumple con opamp ideal (limitacion del opamp) y el legado no
- que falta corregir: nada de diseno en el nuevo; la desviacion viene del ancho de banda del TL082 (ver `simulation.json`). En el legado: SOFIA avisa que Sallen-Key no soporta pasa banda, pero al cambiar el capacitor se reactiva Execute y genera un netlist que solo trae las lineas de los opamps (salida en cero).
