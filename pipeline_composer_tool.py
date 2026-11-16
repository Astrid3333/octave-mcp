#!/usr/bin/env python3
"""
pipeline_composer_tool.py — Compositor de pipelines para octave-mcp.

Permite encadenar cualquier herramienta registrada en el servidor MCP,
pasando el resultado de un paso como argumento del siguiente. Los campos
de resultados previos se referencian con ${nombre_paso.campo} o
${nombre_paso} (todo el resultado).

Esto correlaciona herramientas que antes estaban aisladas (Goertzel,
ancestral_octave, middle_square_weyl, lyapunov, fft, etc.) en un solo
flujo de ejecución.

Ejemplo de uso:
  {
    "steps": [
      {
        "tool": "ancestral_octave",
        "arguments": {"preset": "liu_hui_pi", "params": {"iterations": 10, "levels": 3}},
        "as": "pi_val"
      },
      {
        "tool": "goertzel_scan",
        "arguments": {"signal": [1, 2, 3, 4, 5], "w": "${pi_val.pi_liu_hui}"},
        "as": "goertzel_result"
      }
    ]
  }
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

# Import perezoso para evitar ciclo: server importa este modulo, y este
# modulo necesita run_octave / tool_registry de server.
def _get_run_octave():
    from server import run_octave
    return run_octave


def _get_tool_registry():
    import tool_registry
    return tool_registry


PIPELINE_COMPOSER_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "pipeline_composer",
    "description": (
        "Encadena cualquier herramienta registrada en octave-mcp en un "
        "flujo de ejecucion secuencial. Cada paso especifica una tool y "
        "sus argumentos; los resultados de pasos previos se pueden "
        "referenciar con ${nombre_paso.campo} o ${nombre_paso}. "
        "Permite correlacionar herramientas que antes estaban aisladas "
        "(Goertzel, ancestral_octave, middle_square_weyl, lyapunov, etc.) "
        "en un solo flujo."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "description": "Lista de pasos a ejecutar en orden.",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {
                            "type": "string",
                            "description": "Nombre de la herramienta MCP a llamar.",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Argumentos para la herramienta. "
                                           "Pueden contener referencias "
                                           "${paso.campo} o ${paso}.",
                            "default": {},
                        },
                        "as": {
                            "type": "string",
                            "description": "Nombre bajo el cual guardar el "
                                           "resultado para referenciarlo en "
                                           "pasos posteriores.",
                            "default": None,
                        },
                    },
                    "required": ["tool"],
                    "additionalProperties": False,
                },
            },
            "stop_on_error": {
                "type": "boolean",
                "description": "Si true, detiene el pipeline ante el primer "
                               "error. Si false, continua registrando el "
                               "error en el paso.",
                "default": True,
            },
        },
        "required": ["steps"],
        "additionalProperties": False,
    },
}


def _resolve_refs(value: Any, results: Dict[str, Any]) -> Any:
    """Reemplaza referencias ${paso.campo} o ${paso} en valor por el
    resultado correspondiente de results."""
    if isinstance(value, str):
        # Si el valor entero es una sola referencia, devolver el valor nativo
        m_full = re.match(r'^\$\{([a-zA-Z0-9_.]+)\}$', value)
        if m_full:
            ref = m_full.group(1)
            if '.' in ref:
                step_name, field = ref.split('.', 1)
                step_result = results.get(step_name)
                if isinstance(step_result, dict):
                    return step_result.get(field, f"<{ref} no encontrado>")
                return step_result
            val = results.get(ref)
            if val is None:
                return f"<{ref} no encontrado>"
            return val

        # Si hay referencias embebidas dentro de un string mas grande,
        # sustituir por su representacion en texto
        def _repl(m):
            ref = m.group(1)
            if '.' in ref:
                step_name, field = ref.split('.', 1)
                step_result = results.get(step_name)
                if isinstance(step_result, dict):
                    return str(step_result.get(field, f"<{ref} no encontrado>"))
                return str(step_result)
            step_result = results.get(ref)
            if step_result is None:
                return f"<{ref} no encontrado>"
            return json.dumps(step_result, ensure_ascii=False)
        return re.sub(r'\$\{([a-zA-Z0-9_.]+)\}', _repl, value)
    if isinstance(value, dict):
        return {k: _resolve_refs(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(v, results) for v in value]
    return value


def _call_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Llama a una herramienta registrada en tool_registry o legacy."""
    tool_registry_mod = _get_tool_registry()
    reg = tool_registry_mod.REGISTRY
    if tool_name in reg:
        handler = reg[tool_name]["handler"]
        return handler(arguments)
    raise ValueError(f"Herramienta no registrada: {tool_name}")


def pipeline_composer(steps: List[Dict[str, Any]], stop_on_error: bool = True) -> Dict[str, Any]:
    """Ejecuta una lista de pasos secuencialmente, correlacionando herramientas."""
    results: Dict[str, Any] = {}
    step_results: List[Dict[str, Any]] = []

    for i, step in enumerate(steps):
        step_name = step.get("as") or f"paso_{i}"
        tool_name = step.get("tool")
        arguments = step.get("arguments", {}) or {}

        # Resolver referencias a resultados previos
        resolved_args = _resolve_refs(arguments, results)

        step_entry: Dict[str, Any] = {
            "paso": i,
            "tool": tool_name,
            "argumentos_entrada": resolved_args,
        }

        try:
            result = _call_tool(tool_name, resolved_args)
            step_entry["resultado"] = result
            step_entry["error"] = None
            results[step_name] = result
        except Exception as exc:
            step_entry["resultado"] = None
            step_entry["error"] = str(exc)
            results[step_name] = {"error": str(exc)}
            if stop_on_error:
                step_entry["detenido"] = True
                step_results.append(step_entry)
                break

        step_results.append(step_entry)

    return {
        "pasos_ejecutados": len(step_results),
        "pasos_totales": len(steps),
        "detenido_temprano": (
            len(step_results) < len(steps)
            or any(entry.get("detenido") for entry in step_results)
        ),
        "resultados_por_paso": step_results,
        "resultados": results,
    }


try:
    from tool_registry import register_tool
except ImportError:
    def register_tool(name, schema, handler):
        pass


register_tool(
    name="pipeline_composer",
    schema=PIPELINE_COMPOSER_TOOL_SCHEMA,
    handler=lambda args: pipeline_composer(
        steps=args.get("steps", []),
        stop_on_error=args.get("stop_on_error", True),
    ),
)