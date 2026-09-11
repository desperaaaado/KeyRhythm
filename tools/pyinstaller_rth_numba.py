"""Keep Numba JIT active but disable disk caches in PyInstaller archives."""

import numba


def _without_disk_cache(decorator):
    def wrapper(*args, **kwargs):
        kwargs["cache"] = False
        return decorator(*args, **kwargs)

    return wrapper


for _name in ("jit", "njit", "vectorize", "guvectorize"):
    setattr(numba, _name, _without_disk_cache(getattr(numba, _name)))
numba._keyrhythm_no_cache = True
