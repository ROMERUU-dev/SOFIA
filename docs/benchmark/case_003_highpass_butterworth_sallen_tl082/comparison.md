# Comparison: case_003_highpass_butterworth_sallen_tl082

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
| modern | `cumple` | `funciona` | 16.67 | 0.981 / 1 | 42.22 / 40 | `cumple` |
| legacy | `no_cumple` | `error_de_diseno` | -253.71 | 25.994 / 1 | 38.11 / 40 | `no_cumple` |
