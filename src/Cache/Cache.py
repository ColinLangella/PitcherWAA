import json
import logging
import os
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _FullPath(file_name: str) -> str:
    return os.path.join(BASE_DIR, file_name)


def _FileExists(file_name: str) -> bool:
    return os.path.isfile(_FullPath(file_name))


def _ReadCached(path: str) -> dict | None:
    """Returns the parsed cache file, or None if it's missing/corrupt -- e.g. left
    truncated by a prior run that was killed or interrupted mid-write."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        logging.error(f"Cache file missing or corrupt, refetching: {path}")
        return None


def _WriteAtomic(path: str, data: dict) -> None:
    """Writes to a uniquely-named temp file, then atomically renames it into place, so a
    process killed mid-write can only ever leave behind an orphaned temp file -- never a
    truncated/corrupt file at `path` itself."""
    tmp_path = f"{path}.tmp-{uuid.uuid4().hex}"
    with open(tmp_path, "w") as f:
        json.dump(data, f)
    os.replace(tmp_path, path)


def GetOrFetch(file_name: str, fetch_fn, force_refresh: bool = False) -> dict:
    """Check/fetch-if-absent/read, keyed by file_name, backed by a caller-supplied fetch_fn.

    Caches raw API JSON verbatim; callers are responsible for parsing. `fetch_fn`
    takes no arguments and returns the dict to cache.
    """
    path = _FullPath(file_name)

    if _FileExists(file_name) and not force_refresh:
        cached = _ReadCached(path)
        if cached is not None:
            logging.debug(f"Cache hit: {file_name}")
            return cached

    logging.debug(f"Cache miss: {file_name} -- fetching")
    data = fetch_fn()
    _WriteAtomic(path, data)
    return data


if __name__ == "__main__":
    calls = {"count": 0}

    def _fetch() -> dict:
        calls["count"] += 1
        return {"hello": "world"}

    test_file = "_cache_selfcheck.json"
    try:
        first  = GetOrFetch(test_file, _fetch)
        second = GetOrFetch(test_file, _fetch)
        assert first == second == {"hello": "world"}
        assert calls["count"] == 1, "fetch_fn should only run once (second call should hit cache)"

        # A truncated/corrupt cache file should be treated as a miss and transparently refetched.
        with open(_FullPath(test_file), "w") as f:
            f.write("")
        third = GetOrFetch(test_file, _fetch)
        assert third == {"hello": "world"}
        assert calls["count"] == 2, "a corrupt cache file should trigger exactly one refetch"

        print("Cache self-checks passed.")
    finally:
        if _FileExists(test_file):
            os.remove(_FullPath(test_file))
