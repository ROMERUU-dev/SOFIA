# Comparison: case_006_bandpass_chebyshev_sallen_tl082

- status: `needs_review`
- modern order: `6`
- modern stages: `3`

## Checks

- `legacy_netlist_present`: `pass`
- `modern_netlist_present`: `pass`
- `order_and_q`: `pass`
- `component_prefix_counts`: `review`

## Simulacion contra especificacion

| Netlist | Veredicto | Diagnostico | Ganancia (dB) | Rizo (dB) / limite | Atenuacion (dB) / minimo | Opamp ideal |
| --- | --- | --- | --- | --- | --- | --- |
| modern | `no_cumple` | `limitacion_del_opamp` | -0.00 | 1.218 / 1 | 38.58 / 30 | `cumple_con_tolerancia` |
| legacy | `no_cumple` | `error_de_diseno` | -600.00 | 0.000 / 1 | 0.00 / 30 | `error_simulacion` |
