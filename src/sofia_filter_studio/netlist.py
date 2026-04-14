from __future__ import annotations

from pathlib import Path

from .models import DesignInputs, DesignResult, FilterKind, Stage, Topology


MODEL_FILE_MAP = {
    "LM324": "oplm324.cir",
    "LM318": "LM318.cir",
    "uA741": "ua741.cir",
    "TL082": "TL082.cir",
    "LM7171": "LM7171.cir",
    "LM6164": "LM6164.cir",
    "LM6165": "LM6165.cir",
    "LM6171": "LM6171.cir",
}


def model_path_for(inputs: DesignInputs) -> Path:
    filename = MODEL_FILE_MAP[inputs.opamp.value]
    return Path("resources") / "models" / filename


def _stage_comment(stage: Stage, kind: FilterKind) -> str:
    q_text = f"{stage.q:.5f}" if stage.q is not None else "first-order"
    return f"* Stage {stage.index}: {kind.value}, f0={stage.natural_frequency_hz:.5f} Hz, Q={q_text}, order={stage.order}"


def _format_resistor_network(name: str, node_a: str, node_b: str, realized_name: str, network) -> list[str]:
    if network.connection == "single":
        return [f"{realized_name} {node_a} {node_b} {network.realized_ohms:.6f}"]

    midpoint = f"{realized_name}_MID"
    lines = [f"* {name}: {network.connection} array for target {network.target_ohms:.6f} ohm"]
    if network.connection == "series":
        current_a = node_a
        for index, value in enumerate(network.parts_ohms, start=1):
            current_b = node_b if index == len(network.parts_ohms) else f"{midpoint}{index}"
            lines.append(f"{realized_name}{index} {current_a} {current_b} {value:.6f}")
            current_a = current_b
        return lines

    for index, value in enumerate(network.parts_ohms, start=1):
        lines.append(f"{realized_name}{index} {node_a} {node_b} {value:.6f}")
    return lines


def _stage_ports(stage: Stage, total_stages: int) -> tuple[str, str]:
    stage_input = "IN" if stage.index == 1 else f"STAGE{stage.index - 1}_OUT"
    stage_output = "OUT" if stage.index == total_stages else f"STAGE{stage.index}_OUT"
    return stage_input, stage_output


def render_netlist(inputs: DesignInputs, result: DesignResult) -> str:
    lines: list[str] = []
    lines.append("* SOFIA Filter Studio generated netlist")
    lines.append(f"* Topology request: {inputs.topology.value}")
    lines.append(f"* Filter kind: {inputs.kind.value}")
    lines.append(f"* Approximation: {inputs.approximation.value}")
    lines.append(f"* Filter order: {result.order}")
    lines.append(f"* Epsilon: {result.epsilon:.8f}")
    lines.append(f'.include "{model_path_for(inputs).as_posix()}"')
    lines.append("")
    lines.append("* polarizacion de tierra virtual")
    lines.append("Vin IN 0 DC 2.5 AC 1")
    lines.append("VTIERRA VREF 0 2.5V")
    lines.append("VCC VCC 0 DC 5")
    lines.append("RLOAD OUT 0 100k")
    lines.append("")

    if inputs.topology is Topology.OTA:
        lines.append("* OTA flow migrated as a parameterized placeholder.")
        lines.append(f".param C1={inputs.stage_capacitor_f:.9e}")
        lines.append("* TODO: port legacy OTA sizing equations and transistor-level export.")
    else:
        total_stages = len(result.stages)
        for stage in result.stages:
            lines.append(_stage_comment(stage, inputs.kind))
            lines.extend(_render_stage_template(inputs, stage, total_stages))
            lines.append("")

    lines.append(".ac dec 100 1Hz 500Hz")
    lines.append(".probe V(OUT)")
    lines.append(".end")
    return "\n".join(lines)


def _render_stage_template(inputs: DesignInputs, stage: Stage, total_stages: int) -> list[str]:
    realization = stage.realization
    topology = realization.topology if realization is not None else inputs.topology
    stage_input, stage_output = _stage_ports(stage, total_stages)
    stage_tag = f"S{stage.index}"
    lines = [f"* Stage input: {stage_input}", f"* Stage output: {stage_output}"]

    if realization is not None:
        for note in realization.notes:
            lines.append(f"* {note}")

    if topology is Topology.SALLEN_KEY and realization is not None:
        c1 = realization.capacitor_values_f["C1"]
        c2 = realization.capacitor_values_f["C2"]
        in_node = "IN" if stage.index == 1 else f"1{stage.index - 1}"
        out_node = "OUT" if stage.index == total_stages else f"1{stage.index}"
        node_2 = f"2{stage.index}"
        node_3 = f"3{stage.index}"
        node_4 = f"4{stage.index}"
        lines.append(f"Xao1{stage.index} {node_3} {node_4} VCC 0 {out_node} {inputs.opamp.value}")
        lines.append(f"c1{stage.index} {node_3} VREF {c1:.9e}")
        lines.append(f"c2{stage.index} {node_2} {out_node} {c2:.9e}")
        lines.extend(_format_resistor_network("R1", in_node, node_2, f"r3{stage.index}", realization.resistor_networks["R1"]))
        lines.extend(_format_resistor_network("R2", node_2, node_3, f"r4{stage.index}", realization.resistor_networks["R2"]))
        lines.extend(_format_resistor_network("Rg", node_4, "VREF", f"r1{stage.index}", realization.resistor_networks["Rg"]))
        lines.extend(_format_resistor_network("Rf", node_4, out_node, f"r2{stage.index}", realization.resistor_networks["Rf"]))
    elif topology is Topology.TOW_THOMAS and realization is not None:
        in_node = "IN" if stage.index == 1 else f"1{stage.index - 1}"
        out_node = "OUT" if stage.index == total_stages else f"1{stage.index}"
        n2 = f"2{stage.index}"
        n3 = f"3{stage.index}"
        n4 = f"4{stage.index}"
        n6 = f"6{stage.index}"
        n7 = f"7{stage.index}"
        lines.append(f"Xao1{stage.index} VREF {n2} VCC 0 {n3} {inputs.opamp.value}")
        lines.append(f"Xao2{stage.index} VREF {n4} VCC 0 {out_node} {inputs.opamp.value}")
        lines.append(f"Xao3{stage.index} VREF {n6} VCC 0 {n7} {inputs.opamp.value}")
        lines.append(f"c1{stage.index} {n2} {n3} {realization.capacitor_values_f['C1']:.9e}")
        lines.append(f"c2{stage.index} {n4} {out_node} {realization.capacitor_values_f['C2']:.9e}")
        if "Rbase" in realization.resistor_networks:
            lines.extend(_format_resistor_network("Rbase", in_node, n2, f"r1{stage.index}", realization.resistor_networks["Rbase"]))
            lines.extend(_format_resistor_network("Rbase", n2, n7, f"r2{stage.index}", realization.resistor_networks["Rbase"]))
            lines.extend(_format_resistor_network("Rbase", n3, n4, f"r3{stage.index}", realization.resistor_networks["Rbase"]))
        if "Rq" in realization.resistor_networks:
            lines.extend(_format_resistor_network("Rq", n2, n3, f"r4{stage.index}", realization.resistor_networks["Rq"]))
        if "Rbw" in realization.resistor_networks:
            lines.extend(_format_resistor_network("Rbw", out_node, n6, f"r5{stage.index}", realization.resistor_networks["Rbw"]))
            lines.extend(_format_resistor_network("Rbw", n6, n7, f"r6{stage.index}", realization.resistor_networks["Rbw"]))
    elif topology is Topology.MFB and realization is not None:
        in_node = "10" if stage.index == 1 else f"1{stage.index - 1}"
        out_node = "OUT" if stage.index == total_stages else f"1{stage.index}"
        n2 = f"2{stage.index}"
        n3 = f"3{stage.index}"
        lines.append(f"Xao1{stage.index} {n3} VREF VCC 0 {out_node} {inputs.opamp.value}")
        lines.append(f"c1{stage.index} {n2} {n3} {realization.capacitor_values_f['C1']:.9e}")
        lines.append(f"c2{stage.index} {n2} {out_node} {realization.capacitor_values_f['C2']:.9e}")
        lines.extend(_format_resistor_network("R1", n3, out_node, f"r1{stage.index}", realization.resistor_networks["R1"]))
        lines.extend(_format_resistor_network("R2", n2, "VREF", f"r2{stage.index}", realization.resistor_networks["R2"]))
        lines.extend(_format_resistor_network("R3", in_node, n2, f"r3{stage.index}", realization.resistor_networks["R3"]))
    elif topology is Topology.ANTONIOU and realization is not None:
        in_node = "10" if stage.index == 1 else f"1{stage.index - 1}"
        out_node = "OUT" if stage.index == total_stages else f"1{stage.index}"
        n2 = f"2{stage.index}"
        n3 = f"3{stage.index}"
        n4 = f"4{stage.index}"
        n5 = f"5{stage.index}"
        n6 = f"6{stage.index}"
        lines.append(f"Xao1{stage.index} {n2} {n4} VCC 0 {n5} {inputs.opamp.value}")
        lines.append(f"Xao2{stage.index} {n6} {n4} VCC 0 {n3} {inputs.opamp.value}")
        lines.append(f"Xao3{stage.index} {n6} {out_node} VCC 0 {out_node} {inputs.opamp.value}")
        if "R1" in realization.resistor_networks:
            lines.extend(_format_resistor_network("R1", n5, n6, f"r1{stage.index}", realization.resistor_networks["R1"]))
        if "R2" in realization.resistor_networks:
            lines.extend(_format_resistor_network("R2", n4, n5, f"r2{stage.index}", realization.resistor_networks["R2"]))
        if "R3" in realization.resistor_networks:
            lines.extend(_format_resistor_network("R3", n3, n4, f"r3{stage.index}", realization.resistor_networks["R3"]))
        if "Rq" in realization.resistor_networks:
            lines.extend(_format_resistor_network("Rq", in_node, n2, f"r5{stage.index}", realization.resistor_networks["Rq"]))
            lines.extend(_format_resistor_network("Rq", n6, "VREF", f"r6{stage.index}", realization.resistor_networks["Rq"]))
        if "Rbw" in realization.resistor_networks:
            lines.extend(_format_resistor_network("Rbw", n6, out_node, f"r7{stage.index}", realization.resistor_networks["Rbw"]))
        if "Rnotch" in realization.resistor_networks:
            lines.extend(_format_resistor_network("Rnotch", in_node, out_node, f"r8{stage.index}", realization.resistor_networks["Rnotch"]))
        lines.append(f"c4{stage.index} {n2} {n3} {realization.capacitor_values_f['C1']:.9e}")
        lines.append(f"c6{stage.index} {n6} VREF {realization.capacitor_values_f['C2']:.9e}")
    elif topology is Topology.SALLEN_KEY:
        lines.extend(
            [
                f"R{stage_tag}1 {stage_input} {stage_tag}_A 10k",
                f"R{stage_tag}2 {stage_tag}_A {stage_output} 10k",
                f"C{stage_tag}1 {stage_tag}_A 0 10n",
                f"C{stage_tag}2 {stage_output} 0 10n",
                f"X{stage_tag}BUF {stage_output} {stage_output} VCC 0 {stage_output} {inputs.opamp.value}",
            ]
        )
    elif topology is Topology.TOW_THOMAS:
        lines.extend(
            [
                f"R{stage_tag}B {stage_input} {stage_tag}_SUM 10k",
                f"C{stage_tag}1 {stage_tag}_INT1 0 10n",
                f"C{stage_tag}2 {stage_tag}_INT2 0 10n",
                f"X{stage_tag}A {stage_tag}_SUM {stage_tag}_INT1 VCC 0 {stage_tag}_SUMO {inputs.opamp.value}",
                f"X{stage_tag}B {stage_tag}_INT1 {stage_tag}_INT2 VCC 0 {stage_tag}_INTO {inputs.opamp.value}",
                f"X{stage_tag}C {stage_tag}_INT2 {stage_output} VCC 0 {stage_output} {inputs.opamp.value}",
            ]
        )
    elif topology is Topology.MFB:
        lines.extend(
            [
                f"R{stage_tag}1 {stage_input} {stage_tag}_INV 10k",
                f"R{stage_tag}2 {stage_output} {stage_tag}_INV 10k",
                f"R{stage_tag}3 {stage_tag}_INV 0 10k",
                f"C{stage_tag}1 {stage_input} {stage_tag}_INV 10n",
                f"C{stage_tag}2 {stage_output} {stage_tag}_INV 10n",
                f"X{stage_tag}MFB VREF {stage_tag}_INV VCC 0 {stage_output} {inputs.opamp.value}",
            ]
        )
    elif topology is Topology.ANTONIOU:
        lines.extend(
            [
                f"R{stage_tag}1 {stage_input} {stage_tag}_A 10k",
                f"R{stage_tag}2 {stage_input} {stage_tag}_B 10k",
                f"C{stage_tag}1 {stage_tag}_A 0 10n",
                f"C{stage_tag}2 {stage_tag}_B 0 10n",
                f"X{stage_tag}A {stage_tag}_A {stage_tag}_B VCC 0 {stage_tag}_AO {inputs.opamp.value}",
                f"X{stage_tag}B {stage_tag}_B {stage_output} VCC 0 {stage_output} {inputs.opamp.value}",
            ]
        )
    else:
        lines.append("* Unknown topology")
    return lines
