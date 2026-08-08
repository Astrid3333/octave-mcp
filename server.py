#!/usr/bin/env python3
import subprocess, json, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lyapunov_tool import compute_lyapunov_exponent, LYAPUNOV_TOOL_SCHEMA
from stiff_ode_tool import integrate_stiff_ode, STIFF_ODE_TOOL_SCHEMA
from bifurcation_tool import compute_bifurcation_diagram, BIFURCATION_TOOL_SCHEMA
from hilbert_tool import compute_hilbert_transform, HILBERT_TOOL_SCHEMA
from auto_differentiation_tool import compute_gradient_hessian, compute_jacobian, GRADIENT_HESSIAN_TOOL_SCHEMA, JACOBIAN_TOOL_SCHEMA
from math_error_analyzer_tool import compute_math_error_analysis, MATH_ERROR_ANALYZER_TOOL_SCHEMA
from math_benchmark_tool import compute_math_benchmark, MATH_BENCHMARK_TOOL_SCHEMA
from math_interpolation_tool import compute_math_interpolation, MATH_INTERPOLATION_TOOL_SCHEMA
from math_pipeline_builder_tool import run_math_pipeline, PIPELINE_BUILDER_TOOL_SCHEMA
from math_interpreter_tool import interpret_math_query, MATH_INTERPRETER_TOOL_SCHEMA
from math_visualization_tool import compute_math_visualization, MATH_VISUALIZATION_TOOL_SCHEMA
from math_explainer_tool import interpret_and_explain, MATH_EXPLAINER_TOOL_SCHEMA
from machine_learning_math_tool import compute_machine_learning_math, MACHINE_LEARNING_TOOL_SCHEMA
from financial_math_tool import compute_financial_math, FINANCIAL_MATH_TOOL_SCHEMA
from game_theory_tool import compute_game_theory, GAME_THEORY_TOOL_SCHEMA
from tensor_calculus_tool import compute_tensor_calculus, TENSOR_CALCULUS_TOOL_SCHEMA
from network_science_tool import compute_network_science, NETWORK_SCIENCE_TOOL_SCHEMA
from population_genetics_tool import compute_population_genetics, POPULATION_GENETICS_TOOL_SCHEMA
from wavelet_tool import compute_wavelet, WAVELET_TOOL_SCHEMA
from percolation_theory_tool import compute_percolation_theory, PERCOLATION_THEORY_TOOL_SCHEMA
from reaction_diffusion_tool import compute_reaction_diffusion, REACTION_DIFFUSION_TOOL_SCHEMA
from stochastic_processes_tool import compute_stochastic_processes, STOCHASTIC_PROCESSES_TOOL_SCHEMA
from information_theory_tool import compute_information_theory, INFORMATION_THEORY_TOOL_SCHEMA
from control_theory_tool import compute_control_theory, CONTROL_THEORY_TOOL_SCHEMA
from optimal_control_tool import compute_optimal_control, OPTIMAL_CONTROL_TOOL_SCHEMA
from spatial_statistics_tool import compute_spatial_statistics, SPATIAL_STATISTICS_TOOL_SCHEMA
from text_analysis_math_tool import compute_text_analysis_math, TEXT_ANALYSIS_MATH_TOOL_SCHEMA
from archaeoastronomy_tool import compute_archaeoastronomy, ARCHAEOASTRONOMY_TOOL_SCHEMA
from quantum_information_tool import compute_quantum_information, QUANTUM_INFORMATION_TOOL_SCHEMA


def run_octave(code):
    result = subprocess.run(
        ["octave", "--no-gui", "--eval", code],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout + result.stderr


TOOLS = [
    {
        "name": "run_octave",
        "description": "Ejecuta codigo GNU Octave",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    LYAPUNOV_TOOL_SCHEMA,
    STIFF_ODE_TOOL_SCHEMA,
    BIFURCATION_TOOL_SCHEMA,
    HILBERT_TOOL_SCHEMA,
    GRADIENT_HESSIAN_TOOL_SCHEMA,
    JACOBIAN_TOOL_SCHEMA,
    MATH_ERROR_ANALYZER_TOOL_SCHEMA,
    MATH_BENCHMARK_TOOL_SCHEMA,
    MATH_INTERPOLATION_TOOL_SCHEMA,
    PIPELINE_BUILDER_TOOL_SCHEMA,
    MATH_INTERPRETER_TOOL_SCHEMA,
    MATH_VISUALIZATION_TOOL_SCHEMA,
    MATH_EXPLAINER_TOOL_SCHEMA,
    MACHINE_LEARNING_TOOL_SCHEMA,
    FINANCIAL_MATH_TOOL_SCHEMA,
    GAME_THEORY_TOOL_SCHEMA,
    TENSOR_CALCULUS_TOOL_SCHEMA,
    NETWORK_SCIENCE_TOOL_SCHEMA,
    POPULATION_GENETICS_TOOL_SCHEMA,
    WAVELET_TOOL_SCHEMA,
    PERCOLATION_THEORY_TOOL_SCHEMA,
    REACTION_DIFFUSION_TOOL_SCHEMA,
    STOCHASTIC_PROCESSES_TOOL_SCHEMA,
    INFORMATION_THEORY_TOOL_SCHEMA,
    CONTROL_THEORY_TOOL_SCHEMA,
    OPTIMAL_CONTROL_TOOL_SCHEMA,
    SPATIAL_STATISTICS_TOOL_SCHEMA,
    TEXT_ANALYSIS_MATH_TOOL_SCHEMA,
    ARCHAEOASTRONOMY_TOOL_SCHEMA,
    QUANTUM_INFORMATION_TOOL_SCHEMA,
]


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        req_id = req.get("id")
        method = req.get("method", "")
        if req_id is None:
            continue

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "octave-mcp", "version": "1.2"},
                },
            }

        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

        elif method == "tools/call":
            tool_name = req["params"]["name"]
            args = req["params"].get("arguments", {})

            if tool_name == "run_octave":
                output = run_octave(args["code"])
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": output or "(sin salida)"}]},
                }

            elif tool_name == "compute_lyapunov_exponent":
                result = compute_lyapunov_exponent(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "integrate_stiff_ode":
                result = integrate_stiff_ode(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "compute_bifurcation_diagram":
                result = compute_bifurcation_diagram(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "compute_hilbert_transform":
                result = compute_hilbert_transform(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "compute_gradient_hessian":
                result = compute_gradient_hessian(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "compute_jacobian":
                result = compute_jacobian(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "math_error_analyzer":
                result = compute_math_error_analysis(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "math_benchmark":
                result = compute_math_benchmark(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "math_interpolation":
                result = compute_math_interpolation(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "run_math_pipeline":
                result = run_math_pipeline(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "math_interpreter":
                result = interpret_math_query(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "math_visualization":
                result = compute_math_visualization(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "math_explainer":
                result = interpret_and_explain(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "machine_learning_math":
                result = compute_machine_learning_math(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }
            elif tool_name == "financial_math":
                result = compute_financial_math(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "game_theory":
                result = compute_game_theory(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "tensor_calculus":
                result = compute_tensor_calculus(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "network_science":
                result = compute_network_science(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "population_genetics":
                result = compute_population_genetics(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "wavelet":
                result = compute_wavelet(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "percolation_theory":
                result = compute_percolation_theory(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "reaction_diffusion":
                result = compute_reaction_diffusion(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "stochastic_processes":
                result = compute_stochastic_processes(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "information_theory":
                result = compute_information_theory(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "control_theory":
                result = compute_control_theory(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "optimal_control":
                result = compute_optimal_control(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "spatial_statistics":
                result = compute_spatial_statistics(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "text_analysis_math":
                result = compute_text_analysis_math(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            elif tool_name == "archaeoastronomy":
                result = compute_archaeoastronomy(**args)
            elif tool_name == "quantum_information":
                result = compute_quantum_information(**args)
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]},
                }

            else:
                resp = {
                    "jsonrpc": "2.0", "id": req_id,
                    "error": {"code": -32601, "message": f"Tool desconocido: {tool_name}"},
                }

        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

        print(json.dumps(resp), flush=True)

    except Exception as e:
        print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}), flush=True)
