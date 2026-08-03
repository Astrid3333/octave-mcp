# octave-mcp

Servidor MCP que expone GNU Octave a Claude Desktop, con tools para:
- `run_octave`: ejecutar código Octave arbitrario
- `compute_lyapunov_exponent`: exponente de Lyapunov máximo de sistemas dinámicos (Chen-Lee, Burke-Shaw, Lorenz, Rössler, o ecuaciones custom)
- `integrate_stiff_ode`: integración de EDOs rígidas (ode15s/lsode)
- `compute_bifurcation_diagram`: diagramas de bifurcación para mapas iterativos 1D

## Requisitos
- GNU Octave instalado
- Python 3

## Uso
Configurar en `claude_desktop_config.json` apuntando a `server.py`.
