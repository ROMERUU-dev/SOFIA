# Comparison: case_004_highpass_chebyshev_sallen_tl082

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
| modern | `cumple_con_tolerancia` | `funciona` | 16.13 | 1.002 / 1 | 45.28 / 40 | `cumple_con_tolerancia` |
| legacy | `error_simulacion` | `no_simula` | | | | |
