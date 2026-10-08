# Comparison: case_005_bandpass_butterworth_mfb_tl082

- status: `needs_review`
- modern order: `8`
- modern stages: `4`

## Checks

- `legacy_netlist_present`: `pass`
- `modern_netlist_present`: `pass`
- `order_and_q`: `review`
- `component_prefix_counts`: `review`

## Simulacion contra especificacion

| Netlist | Veredicto | Diagnostico | Ganancia (dB) | Rizo (dB) / limite | Atenuacion (dB) / minimo | Opamp ideal |
| --- | --- | --- | --- | --- | --- | --- |
| modern | `cumple_con_tolerancia` | `funciona` | 0.03 | 1.043 / 1 | 38.20 / 30 | `cumple_con_tolerancia` |
| legacy | `no_cumple` | `error_de_diseno` | -457.99 | 13.091 / 1 | -63.77 / 30 | `no_cumple` |
