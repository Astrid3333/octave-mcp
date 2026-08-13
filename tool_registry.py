"""
tool_registry.py

Registro central de tools MCP para octave-mcp.

Problema que resuelve: hasta ahora, agregar una tool nueva a server.py
requeria 3 ediciones coordinadas (import del modulo, entrada en la lista
TOOLS, bloque elif en el dispatch de tools/call). Olvidar una de las tres
rompe la tool en silencio -- ver el bug de fractional_fourier_tool
corregido en este mismo commit como ejemplo real.

Con este registro, cada modulo de tool se registra a si mismo al ser
importado, con UNA sola linea:

    from tool_registry import register_tool

    def compute_mi_tool(mode, params=None):
        ...

    MI_TOOL_SCHEMA = {...}

    register_tool(
        name="mi_tool",
        schema=MI_TOOL_SCHEMA,
        handler=lambda args: compute_mi_tool(args.get("mode"), args.get("params")),
    )

El handler SIEMPRE recibe el dict `args` completo (los argumentos crudos
de tools/call) y devuelve el resultado ya serializable a JSON. Esto
uniformiza tools que usan firma (mode, params) y tools que usan **args --
la adaptacion se hace en el lambda de cada modulo, no aca.

En server.py, la migracion es:

    import tool_registry
    ...
    TOOLS = [ ...lista legacy que todavia no se migro... ] + tool_registry.get_schemas()
    ...
    if tool_name in tool_registry.REGISTRY:
        result = tool_registry.REGISTRY[tool_name]["handler"](args)
        resp = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [
            {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
        ]}}
    elif tool_name == "...":  # cadena vieja, se va vaciando en tandas siguientes
        ...

Estrategia de migracion ("strangler fig"): las tools YA migradas se sacan
de la lista TOOLS legacy y de la cadena elif (quedan solo en el registro).
Las que faltan migrar siguen andando exactamente igual que hoy. No hace
falta migrar las ~150 tools de una vez ni tocar nada mas.
"""

REGISTRY = {}


def register_tool(name, schema, handler):
    """Registra una tool. Llamar una vez por modulo, a nivel de import.

    name: string, debe coincidir con el 'name' del schema y con el que
          el cliente MCP usa en tools/call.
    schema: dict con la forma esperada por tools/list (name, description,
            inputSchema).
    handler: funcion que recibe el dict `args` de tools/call y devuelve
             el resultado (dict serializable a JSON).
    """
    if name in REGISTRY:
        raise ValueError(
            f"Tool '{name}' ya esta registrada -- colision de nombre entre "
            f"modulos. Revisar imports duplicados o nombres repetidos."
        )
    if schema.get("name") != name:
        raise ValueError(
            f"Inconsistencia de nombre en '{name}': el schema declara "
            f"name='{schema.get('name')}'."
        )
    REGISTRY[name] = {"schema": schema, "handler": handler}


def get_schemas():
    """Lista de schemas (para el campo 'tools' de tools/list), en el orden
    en que se registraron (orden de import)."""
    return [entry["schema"] for entry in REGISTRY.values()]


def get_names():
    return set(REGISTRY.keys())
