# Comparison: case_01_lowpass_butterworth

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
| modern | `cumple` | `funciona` | 16.72 | 0.854 / 1 | 41.59 / 40 | `cumple` |
| legacy | `no_cumple` | `error_de_diseno` | -303.89 | 126.311 / 1 | -26.96 / 40 | `no_cumple` |
