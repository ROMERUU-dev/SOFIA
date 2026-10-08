# Comparison: case_008_lowpass_butterworth_mfb_ua741

- status: `legacy_unsupported`
- modern order: `8`
- modern stages: `4`

## Checks

- `legacy_netlist_present`: `unsupported`
- `modern_netlist_present`: `pass`
- `order_and_q`: `pass`

## Simulacion contra especificacion

| Netlist | Veredicto | Diagnostico | Ganancia (dB) | Rizo (dB) / limite | Atenuacion (dB) / minimo | Opamp ideal |
| --- | --- | --- | --- | --- | --- | --- |
| modern | `cumple` | `funciona` | 0.04 | 0.999 / 1 | 42.49 / 40 | `cumple_con_tolerancia` |
