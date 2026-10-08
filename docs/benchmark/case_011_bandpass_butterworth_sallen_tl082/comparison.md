# Comparison: case_011_bandpass_butterworth_sallen_tl082

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
| modern | `cumple_con_tolerancia` | `funciona` | 0.04 | 1.051 / 1 | 49.52 / 40 | `cumple` |
| legacy | `no_cumple` | `error_de_diseno` | -600.00 | 0.000 / 1 | 0.00 / 40 | `error_simulacion` |
