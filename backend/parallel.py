"""Queue-workers parallelism for the sweep loop.

This is the queue-workers pattern you described: an internal task queue with N
persistent workers, each pulling the next job the moment it finishes one. The
important nuance discovered by profiling: it must run on PROCESSES, not threads.
vtracer's Rust binding and cairo/skimage all hold the GIL during their calls, so
a thread pool gave ~1.0x (no speedup) while a process pool gives ~4x. Each
process has its own GIL and interpreter, so the work runs truly in parallel.

Both maps are provided; `process_map` is what the sweeps use. Defaults to
(cores - 2) workers, leaving headroom for the OS and main process.
"""
from __future__ import annotations

import os
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional


def limit_native_threads():
    """Pin numeric libraries to a single thread each.

    OpenCV / numpy (BLAS) auto-parallelize a single call across all cores. Under
    a worker pool that causes catastrophic oversubscription (N workers x N
    internal threads), which is *slower* than serial. Making each job
    single-threaded lets the pool own the parallelism. Env vars must be set
    before numpy is imported, so call this at the very top of an entry script;
    the cv2 call can happen any time after import.
    """
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(var, "1")
    try:
        import cv2
        cv2.setNumThreads(1)
    except Exception:
        pass


def default_workers() -> int:
    return max(1, (os.cpu_count() or 4) - 2)


def thread_map(fn: Callable, jobs: List, workers: Optional[int] = None,
               on_progress: Optional[Callable[[int, int], None]] = None) -> List:
    """Run fn over jobs across a worker pool; return results in job order.

    Exceptions in a job are captured and returned as {"__error__": str} rather
    than aborting the whole run. `on_progress(done, total)` fires as each job
    completes (from worker threads, so it must be cheap/thread-safe).
    """
    workers = workers or default_workers()
    total = len(jobs)
    results: List = [None] * total
    lock = threading.Lock()
    done = 0

    def _wrapped(job):
        try:
            return fn(job)
        except Exception as e:  # keep the pool alive on a single bad job
            return {"__error__": str(e)}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_wrapped, job): i for i, job in enumerate(jobs)}
        for fut in as_completed(futs):
            i = futs[fut]
            results[i] = fut.result()
            if on_progress is not None:
                with lock:
                    done += 1
                    on_progress(done, total)
    return results


def process_map(fn: Callable, jobs: List, workers: Optional[int] = None,
                on_progress: Optional[Callable[[int, int], None]] = None,
                initializer: Optional[Callable] = None) -> List:
    """Like thread_map but with a process pool (real parallelism, own GIL each).

    `fn` and every job must be picklable — use a module-level worker fn and pass
    data as primitives/paths, not closures or large arrays. Results are returned
    in job order; a job that raises becomes {"__error__": str}.
    """
    workers = workers or default_workers()
    total = len(jobs)
    results: List = [None] * total
    done = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=initializer) as ex:
        futs = {ex.submit(fn, job): i for i, job in enumerate(jobs)}
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception as e:
                results[i] = {"__error__": str(e)}
            if on_progress is not None:
                done += 1
                on_progress(done, total)
    return results
