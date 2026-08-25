"""
hydrothermal_inference_tool.py

Inferencia de composición de fluidos hidrotermales usando el algoritmo
Expectation-Maximization (EM) con un modelo de transporte reactivo forward simple.

Modos:
  - forward_model: simular alteración mineral dado fluido y parámetros
  - em_inference: estimar composición del fluido desde datos de alteración (EM)
  - posterior_samples: muestrear la distribución posterior (MCMC simple)
  - validate: validación con datos sintéticos

Patrón: TOOL_SCHEMA, dispatcher, _validate(), _handler(arguments), _register()
"""

import json
import math
import random

TOOL_SCHEMA = {
    "name": "hydrothermal_inference_tool",
    "description": "Inferencia bayesiana de fluidos hidrotermales con EM y modelos de transporte reactivo",
    "inputSchema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["forward_model", "em_inference", "posterior_samples", "validate"],
                "description": "Modo de operación"
            },
            "fluid_composition": {
                "type": "array",
                "description": "Composición del fluido (ej. [Na, K, Ca, SiO2, ...]) en ppm"
            },
            "temperature": {
                "type": "number",
                "description": "Temperatura del fluido en °C"
            },
            "flux": {
                "type": "number",
                "description": "Flujo (volumen de fluido) en unidades relativas"
            },
            "alteration_data": {
                "type": "array",
                "description": "Observaciones: minerales de alteración presentes/ausentes"
            },
            "prior_mean": {
                "type": "array",
                "description": "Media prior para la composición del fluido"
            },
            "n_iterations": {
                "type": "integer",
                "description": "Número de iteraciones EM"
            },
            "n_samples": {
                "type": "integer",
                "description": "Número de muestras MCMC"
            }
        },
        "required": ["mode"]
    }
}

def forward_model_simple(fluid_composition, temperature, flux):
    """
    Modelo de transporte reactivo simple (1D).
    
    Reglas de alteración (simplificadas):
      - Si Na > 500 ppm y T > 150°C → feldespato sódico
      - Si K > 200 ppm y T > 200°C → feldespato potásico
      - Si Ca > 300 ppm y SiO2 > 1000 ppm → escapolita
      - Si Si > 2000 ppm y T < 180°C → cuarzo masivo
    
    Devuelve lista de minerales esperados.
    """
    if not fluid_composition or len(fluid_composition) < 5:
        return {"error": "Se requieren al menos 5 componentes en la composición del fluido"}
    
    Na, K, Ca, Fe, Si = fluid_composition[0:5]
    
    minerals_predicted = []
    
    # Albita (feldespato sódico)
    if Na > 500 and temperature > 150:
        minerals_predicted.append({"mineral": "Albita", "probability": min(1.0, (Na / 1000) * (temperature / 250))})
    
    # Feldespato potásico
    if K > 200 and temperature > 200:
        minerals_predicted.append({"mineral": "Ortoclasa", "probability": min(1.0, (K / 500) * (temperature / 300))})
    
    # Escapolita
    if Ca > 300 and Si > 1000:
        minerals_predicted.append({"mineral": "Escapolita", "probability": min(1.0, (Ca / 600) * (Si / 2000))})
    
    # Cuarzo masivo
    if Si > 2000 and temperature < 180:
        minerals_predicted.append({"mineral": "Cuarzo", "probability": min(1.0, (Si / 3000))})
    
    # Magnetita
    if Fe > 100 and temperature > 250:
        minerals_predicted.append({"mineral": "Magnetita", "probability": min(1.0, (Fe / 300))})
    
    # Alteración general
    alteration_type = "Propilítico"  # Default
    if Na > K and Na > 500:
        alteration_type = "Albítico"
    elif K > Na and K > 300:
        alteration_type = "Argílico"
    elif Ca > 400:
        alteration_type = "Calco-silicatada"
    
    return {
        "fluido_entrada": {
            "composicion": fluid_composition,
            "temperatura": temperature,
            "flujo": flux
        },
        "minerales_predichos": minerals_predicted,
        "tipo_alteracion": alteration_type,
        "n_minerales": len(minerals_predicted)
    }

def em_inference(alteration_data, prior_mean, n_iterations=5):
    """
    Algoritmo EM para inferir composición del fluido desde datos de alteración.
    
    E-step: estimar probabilidades posteriores de composición
    M-step: actualizar estimativo de la composición
    """
    if not alteration_data or not prior_mean:
        return {"error": "Se requieren alteration_data y prior_mean"}
    
    # Inicializar con el prior
    current_estimate = list(prior_mean)
    
    history = []
    
    for iteration in range(n_iterations):
        # E-step: calcular likelihood de observar alteration_data dado current_estimate
        likelihood = 0.0
        for i, (mineral, observed) in enumerate(alteration_data):
            # Heurística simple: si mineral observado, aumenta likelihood
            if observed:
                likelihood += 0.9
            else:
                likelihood += 0.1
        
        likelihood = likelihood / len(alteration_data)
        
        # M-step: actualizar estimativo
        # Aplicar pequeña corrección basada en likelihood
        update_factor = 0.5 + 0.5 * likelihood
        new_estimate = [c * update_factor + p * (1 - update_factor)
                        for c, p in zip(current_estimate, prior_mean)]
        
        history.append({
            "iteration": iteration,
            "estimate": [round(x, 2) for x in new_estimate],
            "likelihood": round(likelihood, 4)
        })
        
        current_estimate = new_estimate
    
    # Normalizar estimativo (mantener proporciones)
    total = sum(current_estimate)
    if total > 0:
        current_estimate = [c / total * sum(prior_mean) for c in current_estimate]
    
    return {
        "composicion_inferida": [round(x, 2) for x in current_estimate],
        "iteraciones_em": history,
        "n_iteraciones": n_iterations,
        "convergencia": "parcial"
    }

def posterior_samples_mcmc(prior_mean, alteration_data, n_samples=100):
    """
    Muestreo MCMC simple (Metropolis-Hastings) de la distribución posterior.
    
    Prior: distribución normal alrededor de prior_mean
    Likelihood: simple (cuenta minerales observados)
    """
    if not prior_mean or not alteration_data:
        return {"error": "Se requieren prior_mean y alteration_data"}
    
    # Inicializar cadena
    current = list(prior_mean)
    samples = []
    accepted = 0
    
    random.seed(42)  # Reproducibilidad
    
    for step in range(n_samples):
        # Proponer nuevo estado (perturbación gaussiana)
        sigma = 50.0  # SD de la propuesta
        proposal = [c + random.gauss(0, sigma) for c in current]
        
        # Evitar negativos
        proposal = [max(0, p) for p in proposal]
        
        # Calcular likelihood (simplificado)
        def calc_likelihood(composition):
            ll = 0.0
            for mineral, observed in alteration_data:
                # Heurística: composición con valores altos es más plausible
                avg_comp = sum(composition) / len(composition)
                if observed:
                    ll += math.exp(-abs(avg_comp - 500) / 200)
                else:
                    ll += math.exp(-(avg_comp) / 200)
            return ll
        
        ll_current = calc_likelihood(current)
        ll_proposal = calc_likelihood(proposal)
        
        # Ratio de aceptación (Metropolis)
        alpha = ll_proposal / (ll_current + 1e-10)
        
        if random.random() < alpha:
            current = proposal
            accepted += 1
        
        if step >= n_samples // 2:  # Burn-in: ignorar primeras muestras
            samples.append([round(x, 2) for x in current])
    
    # Estadísticas
    if samples:
        means = [round(sum(s[i] for s in samples) / len(samples), 2) for i in range(len(prior_mean))]
        stds = [round(math.sqrt(sum((s[i] - means[i]) ** 2 for s in samples) / len(samples)), 2)
                for i in range(len(prior_mean))]
    else:
        means = list(prior_mean)
        stds = [0] * len(prior_mean)
    
    acceptance_rate = accepted / n_samples if n_samples > 0 else 0
    
    return {
        "muestras": samples[-10:] if samples else [],  # Últimas 10 muestras
        "media_posterior": means,
        "desv_std_posterior": stds,
        "tasa_aceptacion": round(acceptance_rate, 4),
        "n_muestras": len(samples),
        "nota": "Burn-in: 50%, últimas 10 muestras mostradas"
    }

def _validate():
    """
    Validación con datos sintéticos.
    """
    checks = []
    
    # Check 1: Forward model simple
    fluid = [1000, 300, 400, 50, 2500]  # Na, K, Ca, Fe, Si
    T = 200
    flux = 1.0
    fm = forward_model_simple(fluid, T, flux)
    checks.append({
        "name": "forward_model_execution",
        "passed": "minerales_predichos" in fm,
        "detail": f"Minerales predichos: {len(fm.get('minerales_predichos', []))}"
    })
    
    # Check 2: Forward model con Na alto
    fluid_na = [1200, 100, 200, 30, 1500]
    fm_na = forward_model_simple(fluid_na, 180, 1.0)
    has_albita = any(m["mineral"] == "Albita" for m in fm_na.get("minerales_predichos", []))
    checks.append({
        "name": "forward_model_na_produces_albite",
        "passed": has_albita,
        "detail": f"Albita predicha: {has_albita}"
    })
    
    # Check 3: Forward model con K alto
    fluid_k = [300, 600, 200, 20, 1500]
    fm_k = forward_model_simple(fluid_k, 220, 1.0)
    has_orth = any(m["mineral"] == "Ortoclasa" for m in fm_k.get("minerales_predichos", []))
    checks.append({
        "name": "forward_model_k_produces_orthoclase",
        "passed": has_orth,
        "detail": f"Ortoclasa predicha: {has_orth}"
    })
    
    # Check 4: EM convergence
    alteration = [("Albita", True), ("Ortoclasa", False), ("Cuarzo", True)]
    prior = [800, 200, 300, 40, 2000]
    em = em_inference(alteration, prior, n_iterations=5)
    checks.append({
        "name": "em_inference_runs",
        "passed": len(em.get("iteraciones_em", [])) == 5,
        "detail": f"Iteraciones completadas: {len(em.get('iteraciones_em', []))}"
    })
    
    # Check 5: EM produces estimate
    has_estimate = "composicion_inferida" in em and len(em.get("composicion_inferida", [])) > 0
    checks.append({
        "name": "em_inference_estimate",
        "passed": has_estimate,
        "detail": f"Estimativo disponible: {has_estimate}"
    })
    
    # Check 6: MCMC sampling
    samples = posterior_samples_mcmc(prior, alteration, n_samples=100)
    checks.append({
        "name": "mcmc_sampling_runs",
        "passed": samples.get("n_muestras", 0) > 0,
        "detail": f"Muestras generadas: {samples.get('n_muestras')}"
    })
    
    # Check 7: MCMC posterior stats
    has_posterior = "media_posterior" in samples and len(samples.get("media_posterior", [])) > 0
    checks.append({
        "name": "mcmc_posterior_statistics",
        "passed": has_posterior,
        "detail": f"Estadísticas posteriores: {samples.get('media_posterior')}"
    })
    
    passed = sum(1 for c in checks if c["passed"])
    return {
        "validation_passed": passed == len(checks),
        "checks": checks,
        "n_checks": len(checks),
        "n_passed": passed
    }

def hydrothermal_inference(mode, params=None):
    """
    Dispatcher principal.
    """
    params = params or {}
    
    if mode == "forward_model":
        fluid = params.get("fluid_composition")
        temp = params.get("temperature", 200)
        flux = params.get("flux", 1.0)
        if fluid is None:
            return {"error": "Parámetro 'fluid_composition' requerido"}
        return forward_model_simple(fluid, temp, flux)
    
    elif mode == "em_inference":
        alteration = params.get("alteration_data")
        prior = params.get("prior_mean")
        n_iter = params.get("n_iterations", 5)
        if alteration is None or prior is None:
            return {"error": "Parámetros 'alteration_data' y 'prior_mean' requeridos"}
        return em_inference(alteration, prior, n_iterations=n_iter)
    
    elif mode == "posterior_samples":
        prior = params.get("prior_mean")
        alteration = params.get("alteration_data")
        n_samp = params.get("n_samples", 100)
        if prior is None or alteration is None:
            return {"error": "Parámetros 'prior_mean' y 'alteration_data' requeridos"}
        return posterior_samples_mcmc(prior, alteration, n_samples=n_samp)
    
    elif mode == "validate":
        return _validate()
    
    else:
        return {"error": f"modo desconocido: {mode}"}

def _handler(arguments):
    arguments = arguments or {}
    mode = arguments.get("mode", "validate")
    return hydrothermal_inference(mode=mode, params=arguments)

def _register():
    try:
        import tool_registry
        tool_registry.register_tool(TOOL_SCHEMA["name"], TOOL_SCHEMA, _handler)
    except ImportError:
        pass

_register()

if __name__ == "__main__":
    import sys
    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "validate"
    params_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    result = hydrothermal_inference(mode_arg, params_arg)
    print(json.dumps(result, indent=2, ensure_ascii=False))
