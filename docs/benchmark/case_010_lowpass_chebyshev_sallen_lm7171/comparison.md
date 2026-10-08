# Comparison: case_010_lowpass_chebyshev_sallen_lm7171

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
| modern | `cumple` | `funciona` | 15.67 | 0.781 / 1 | 42.75 / 40 | `cumple` |
| legacy | `error_simulacion` | `no_simula` | | | | |
