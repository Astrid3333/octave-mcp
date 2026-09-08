
# Ethnomath
from .ethnomath.ethnomath_tool import ethnomath_hybrid_tool, TOOL_SCHEMA
tool_registry.register_tool(
    name=TOOL_SCHEMA['name'],
    handler=lambda args: ethnomath_hybrid_tool(args),
    schema=TOOL_SCHEMA,
    category='mathematics/ethnomathematics',
    tags=['persian', 'hebrew', 'base60', 'gematria']
)

from .ethnomath.ethnomath_comparative_tool import ethnomath_comparative_tool, TOOL_SCHEMA as COMP
tool_registry.register_tool(
    name=COMP['name'],
    handler=lambda args: ethnomath_comparative_tool(args),
    schema=COMP,
    tags=['persan', 'ternary', 'canaanite', 'comparative']
)

from .ethnomath.ethnomath_comparative_tool import ethnomath_comparative_tool, TOOL_SCHEMA as COMP
tool_registry.register_tool(
    name=COMP['name'],
    handler=lambda args: ethnomath_comparative_tool(args),
    schema=COMP,
    tags=['persan', 'ternary', 'canaanite', 'comparative']
)

# Ternary Hamming code
from .ternary_codes.ternary_hamming_tool import ternary_hamming_tool, TOOL_SCHEMA as TERNARY_HAMMING
tool_registry.register_tool(
    name=TERNARY_HAMMING['name'],
    handler=lambda args: ternary_hamming_tool(args),
    schema=TERNARY_HAMMING,
    category='information_theory/coding',
    tags=['ternary', 'hamming', 'error_correction', 'landauer']
)
