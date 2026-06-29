"""Señales de error canónicas para disponibilidad del LLM.

Módulo liviano, sin dependencias internas, importable desde cualquier capa.
"""


class LLMUnavailableError(RuntimeError):
    """El LLM no está disponible por cuota agotada o error irrecuperable en ambas claves.

    Se lanza cuando ``call_groq_json`` falla con ``GroqRateLimitError`` en la clave
    primaria y en el backup simultáneamente (límite TPD compartido o ambas claves inválidas).
    El worker Celery la captura como señal de abort silencioso: no se envía respuesta
    al candidato, no se persisten facts, solo se registra en logs bajo ``[LLM_GATE]``.
    """
