# Comparison: case_007_bandstop_butterworth_tow_thomas_tl082

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
| modern | `cumple` | `funciona` | 0.19 | 0.850 / 1 | 43.16 / 40 | `cumple` |
| legacy | `no_cumple` | `error_de_diseno` | 0.20 | 4.523 / 1 | 44.10 / 40 | `no_cumple` |
