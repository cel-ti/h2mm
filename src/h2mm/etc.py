import os


class CacheOnModifiedDate:
    """A decorator that caches function results based on the modification date of a file path.
    The first parameter of the decorated function must be a string path.
    Cache is invalidated if the file's modification time changes."""

    def __init__(self):
        self.cache = {}
        self.mtimes = {}

    def __call__(self, func):
        def wrapper(path: str, *args, **kwargs):
            if not isinstance(path, str):
                raise TypeError("First argument must be a string path")

            try:
                mtime = os.path.getmtime(path)
            except OSError:
                # If file doesn't exist or other OS error, don't cache
                return func(path, *args, **kwargs)

            cache_key = (path, args, frozenset(kwargs.items()))

            if (
                cache_key in self.cache
                and cache_key in self.mtimes
                and self.mtimes[cache_key] == mtime
            ):
                return self.cache[cache_key]

            # Clear old cache entry if exists
            if cache_key in self.cache:
                del self.cache[cache_key]
                del self.mtimes[cache_key]

            # Calculate and cache new result
            result = func(path, *args, **kwargs)
            self.cache[cache_key] = result
            self.mtimes[cache_key] = mtime
            return result

        return wrapper
