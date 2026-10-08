# Comparison: case_009_lowpass_butterworth_sallen_lm324

- status: `needs_review`
- modern order: `8`
- modern stages: `4`

## Checks

- `legacy_netlist_present`: `pass`
- `modern_netlist_present`: `pass`
- `order_and_q`: `pass`
- `component_prefix_counts`: `review`

## Simulacion contra especificacion

| Netlist | Veredicto | Diagnostico | Ganancia (dB) | Rizo (dB) / limite | Atenuacion (dB) / minimo | Opamp ideal |
| --- | --- | --- | --- | --- | --- | --- |
| modern | `cumple` | `funciona` | 16.73 | 0.995 / 1 | 42.38 / 40 | `cumple` |
| legacy | `no_cumple` | `error_de_diseno` | 16.80 | 1.546 / 1 | 44.23 / 40 | `no_cumple` |
