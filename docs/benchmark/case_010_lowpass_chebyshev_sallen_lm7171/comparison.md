# Comparison: case_010_lowpass_chebyshev_sallen_lm7171

- status: `needs_review`
- modern order: `5`
- modern stages: `3`

## Checks

- `legacy_netlist_present`: `pass`
- `modern_netlist_present`: `pass`
- `order_and_q`: `pass`
- `component_prefix_counts`: `review`

## Simulacion contra especificacion

| Netlist | Veredicto | Diagnostico | Ganancia (dB) | Rizo (dB) / limite | Atenuacion (dB) / minimo | Opamp ideal |
| --- | --- | --- | --- | --- | --- | --- |
| modern | `cumple_con_tolerancia` | `funciona` | 16.17 | 1.041 / 1 | 45.30 / 40 | `cumple_con_tolerancia` |
| legacy | `error_simulacion` | `no_simula` | | | | |
