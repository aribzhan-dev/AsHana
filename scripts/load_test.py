"""Read-only load check of the public menu and slots (no orders are created).

python3 -I scripts/load_test.py --url http://127.0.0.1:8080 --users 50 --requests 1000
"""

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import URLError
from urllib.request import urlopen


def timed(url: str) -> tuple[float, bool]:
    started = time.perf_counter()
    try:
        with urlopen(url, timeout=10) as response:
            response.read()
            ok = response.status == 200
    except (URLError, TimeoutError, OSError):
        ok = False
    return (time.perf_counter() - started) * 1000, ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--requests", type=int, default=1000)
    args = parser.parse_args()
    base = args.url.rstrip("/") + "/api/v1"
    with urlopen(f"{base}/catalog/menu?upcoming=true&limit=20", timeout=10) as response:
        entries = json.loads(response.read())["entries"]
    period = entries[0]["period_id"] if entries else None
    urls = [f"{base}/catalog/menu?upcoming=true&limit=20"]
    if period:
        urls.append(f"{base}/orders/slots?period_id={period}")
    plan = [urls[n % len(urls)] for n in range(args.requests)]
    started = time.perf_counter()
    with ThreadPoolExecutor(args.users) as pool:
        results = list(pool.map(timed, plan))
    total = time.perf_counter() - started
    times = sorted(ms for ms, _ in results)
    errors = sum(not ok for _, ok in results)
    p95 = times[int(len(times) * 0.95) - 1]
    print(f"Запросов: {len(results)}, одновременно: {args.users}, ошибок: {errors}")
    print(f"Пропускная способность: {len(results) / total:.0f} запросов/с")
    print(
        f"Время ответа, мс: медиана {statistics.median(times):.0f}, "
        f"95% {p95:.0f}, максимум {times[-1]:.0f}"
    )


if __name__ == "__main__":
    main()
