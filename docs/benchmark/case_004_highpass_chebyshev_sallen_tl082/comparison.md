# Comparison: case_004_highpass_chebyshev_sallen_tl082

- status: `needs_review`
- modern order: `5`
- modern stages: `3`

## Checks

- `legacy_netlist_present`: `pass`
- `modern_netlist_present`: `pass`
- `order_and_q`: `review`
- `component_prefix_counts`: `pass`

## Simulacion contra especificacion

| Netlist | Veredicto | Diagnostico | Ganancia (dB) | Rizo (dB) / limite | Atenuacion (dB) / minimo | Opamp ideal |
| --- | --- | --- | --- | --- | --- | --- |
| modern | `cumple` | `funciona` | 15.62 | 0.638 / 1 | 42.61 / 40 | `cumple` |
| legacy | `error_simulacion` | `no_simula` | | | | |
