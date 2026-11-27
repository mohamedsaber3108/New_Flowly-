"""Measure how much memory N parallel Argon2 hashes need (FL-20). Not part of CI.

    DJANGO_SETTINGS_MODULE=config.settings.test python scripts/argon2_memory_check.py [N]

Hashes N passwords at the same moment in N threads with Django's Argon2PasswordHasher and prints the process's
peak resident memory before and after. gunicorn here runs 3 workers x 2 threads, so at most 6 hashes run at once
on the server; the default N is 10 to leave margin.
"""

import os
import resource
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the backend/ folder, so `config` imports
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from django.contrib.auth.hashers import Argon2PasswordHasher  # noqa: E402


def peak_mib():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux reports KiB


def main(count):
    hasher = Argon2PasswordHasher()
    print(
        f"Django Argon2: time_cost={hasher.time_cost} memory_cost={hasher.memory_cost} KiB "
        f"parallelism={hasher.parallelism}"
    )
    hasher.encode("warm-up", hasher.salt())  # load the library once so it is not counted as hash memory
    before = peak_mib()
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=count) as pool:
        hashes = list(pool.map(lambda i: hasher.encode(f"password-{i}", hasher.salt()), range(count)))
    elapsed = time.perf_counter() - start
    after = peak_mib()
    assert len(hashes) == count and all(h.startswith("argon2$") for h in hashes)
    print(
        f"{count} hashes in parallel: {elapsed:.2f} s, "
        f"peak RSS {before:.0f} MiB -> {after:.0f} MiB (+{after - before:.0f} MiB)"
    )


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
