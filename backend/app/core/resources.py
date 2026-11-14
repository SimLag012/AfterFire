"""Optional Unix process telemetry; absence must not fail an analysis."""
def peak_rss_kib():
    try:
        import resource
    except ImportError:
        return None
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
