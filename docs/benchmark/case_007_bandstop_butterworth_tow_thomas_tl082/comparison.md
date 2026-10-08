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
| modern | `no_cumple` | `limitacion_del_opamp` | 0.52 | 1.520 / 1 | 46.01 / 40 | `cumple_con_tolerancia` |
| legacy | `no_cumple` | `error_de_diseno` | 0.20 | 4.523 / 1 | 44.10 / 40 | `no_cumple` |
