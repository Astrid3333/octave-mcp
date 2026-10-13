"""
opencl_utils.py
Utilidad compartida para backends OpenCL opcionales en los tools de
mcp-octave-real.

Si pyopencl no esta instalado, o esta instalado pero no hay ninguna
plataforma/dispositivo OpenCL disponible (caso tipico: notebook sin GPU
dedicada ni ICD configurado), OPENCL_AVAILABLE queda en False y ningun
otro modulo se entera de que esto existe -- ningun tool cambia de
comportamiento ni falla por esto.

Uso tipico dentro de un tool:

    from opencl_utils import OPENCL_AVAILABLE, get_opencl_context

    if backend == "opencl":
        if not OPENCL_AVAILABLE:
            raise ValueError(
                "backend='opencl' pedido pero no hay pyopencl+dispositivo "
                "disponible. Usar backend='numpy' (default) o 'numba'."
            )
        ctx, queue = get_opencl_context()
        ...
"""

try:
    import pyopencl as cl
    _platforms = cl.get_platforms()
    _devices = [d for p in _platforms for d in p.get_devices()]
    OPENCL_AVAILABLE = len(_devices) > 0
except Exception:
    # Cubre ImportError (pyopencl no instalado) y cualquier excepcion de
    # inicializacion de la plataforma OpenCL (drivers ausentes, ICD mal
    # configurado, sin permisos sobre el dispositivo, etc.). En todos los
    # casos backend='opencl' simplemente no debe quedar disponible.
    cl = None
    OPENCL_AVAILABLE = False

_CACHED_CONTEXT = None
_CACHED_QUEUE = None


def get_opencl_context(prefer_gpu=True):
    """
    Devuelve (context, queue), cacheados tras la primera llamada dentro del
    proceso (crear un contexto OpenCL tiene overhead no trivial y no hace
    falta repetirlo por cada sweep/llamada).

    Lanza RuntimeError si se llama sin chequear OPENCL_AVAILABLE antes --
    eso es responsabilidad del tool que llama, para poder dar un mensaje
    de error especifico al dominio (ej. "usa backend=numpy en su lugar").
    """
    global _CACHED_CONTEXT, _CACHED_QUEUE
    if not OPENCL_AVAILABLE:
        raise RuntimeError(
            "get_opencl_context() llamado sin OPENCL_AVAILABLE=True. "
            "El tool que llama deberia chequear OPENCL_AVAILABLE primero."
        )
    if _CACHED_CONTEXT is not None:
        return _CACHED_CONTEXT, _CACHED_QUEUE

    devices = []
    for platform in cl.get_platforms():
        devices.extend(platform.get_devices())

    if prefer_gpu:
        gpu_devices = [d for d in devices if d.type & cl.device_type.GPU]
        device = gpu_devices[0] if gpu_devices else devices[0]
    else:
        device = devices[0]

    ctx = cl.Context([device])
    queue = cl.CommandQueue(ctx)
    _CACHED_CONTEXT = ctx
    _CACHED_QUEUE = queue
    return ctx, queue


def opencl_device_info():
    """
    Info legible del dispositivo OpenCL activo (nombre, tipo, vendor,
    unidades de computo). Util para incluir en el output de un tool cuando
    backend='opencl', asi queda registrado en que hardware corrio -- sirve
    para debug remoto sin acceso directo a la maquina.
    Devuelve None si OPENCL_AVAILABLE es False.
    """
    if not OPENCL_AVAILABLE:
        return None
    ctx, _ = get_opencl_context()
    device = ctx.devices[0]
    return {
        "name": device.name.strip(),
        "type": "GPU" if device.type & cl.device_type.GPU else "CPU",
        "vendor": device.vendor.strip(),
        "max_compute_units": device.max_compute_units,
    }
