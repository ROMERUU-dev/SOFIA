# Benchmark Report

Generated from the benchmark case folders. Cases marked `pending_legacy` still need `legacy.cir` from the original SOFIA on Windows.

Spec columns come from `scripts/simulate_case.py`: each netlist is simulated (AC) and checked against
`input.json` (passband ripple <= Ap, stopband attenuation >= As). `limitacion_del_opamp` means the same
circuit meets the spec with ideal op amps, so the deviation comes from the op amp model, not the design.

| Case | Structure vs legacy | New version | Legacy |
| --- | --- | --- | --- |
| `case_001_lowpass_butterworth_sallen_tl082` | `needs_review` | `cumple` | `no_cumple` (error_de_diseno) |
| `case_002_lowpass_chebyshev_sallen_tl082` | `needs_review` | `cumple_con_tolerancia` | `error_simulacion` (no_simula) |
| `case_003_highpass_butterworth_sallen_tl082` | `needs_review` | `cumple` | `no_cumple` (error_de_diseno) |
| `case_004_highpass_chebyshev_sallen_tl082` | `needs_review` | `cumple_con_tolerancia` | `error_simulacion` (no_simula) |
| `case_005_bandpass_butterworth_mfb_tl082` | `needs_review` | `cumple_con_tolerancia` | `no_cumple` (error_de_diseno) |
| `case_006_bandpass_chebyshev_sallen_tl082` | `needs_review` | `no_cumple` (limitacion_del_opamp) | `no_cumple` (error_de_diseno) |
| `case_007_bandstop_butterworth_tow_thomas_tl082` | `needs_review` | `no_cumple` (limitacion_del_opamp) | `no_cumple` (error_de_diseno) |
| `case_008_lowpass_butterworth_mfb_ua741` | `legacy_unsupported` | `cumple` | `no_soportado` |
| `case_009_lowpass_butterworth_sallen_lm324` | `needs_review` | `cumple` | `no_cumple` (error_de_diseno) |
| `case_010_lowpass_chebyshev_sallen_lm7171` | `needs_review` | `cumple_con_tolerancia` | `error_simulacion` (no_simula) |
| `case_011_bandpass_butterworth_sallen_tl082` | `needs_review` | `cumple_con_tolerancia` | `no_cumple` (error_de_diseno) |
| `case_01_lowpass_butterworth` | `needs_review` | `cumple` | `no_cumple` (error_de_diseno) |
