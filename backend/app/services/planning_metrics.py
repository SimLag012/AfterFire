"""Per-plan measurements shared with concurrent catalog tasks through context propagation."""
from contextvars import ContextVar
metrics=ContextVar('planning_metrics',default=None)


def record(name,seconds):
    current=metrics.get()
    if current is not None:
        current[name]=round(current.get(name,0)+seconds,6)
