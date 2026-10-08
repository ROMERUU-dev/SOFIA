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
| modern | `cumple` | `funciona` | 0.03 | 0.813 / 1 | 41.44 / 40 | `cumple` |
