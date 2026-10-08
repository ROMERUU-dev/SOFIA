# Comparison: case_005_bandpass_butterworth_mfb_tl082

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
| modern | `cumple` | `funciona` | 0.05 | 0.450 / 1 | 33.97 / 30 | `cumple` |
| legacy | `no_cumple` | `error_de_diseno` | -457.99 | 13.091 / 1 | -63.77 / 30 | `no_cumple` |
