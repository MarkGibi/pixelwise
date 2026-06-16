#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import error, request


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def make_image(seed: int) -> list[list[int]]:
    image = [[0 for _ in range(28)] for _ in range(28)]

    # Deterministic simple test pattern. The goal is API performance,
    # not model accuracy.
    for i in range(28):
        image[i][(i + seed) % 28] = 255
        image[(i * 3 + seed) % 28][14] = 255

    return image


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = (len(ordered) - 1) * (percent / 100)
    lower = math.floor(index)
    upper = math.ceil(index)

    if lower == upper:
        return ordered[int(index)]

    lower_value = ordered[lower]
    upper_value = ordered[upper]
    weight = index - lower

    return lower_value + (upper_value - lower_value) * weight


def post_json(url: str, payload: dict, api_key: str, expected_images: int, timeout: int) -> dict:
    body = json.dumps(payload).encode("utf-8")

    req = request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )

    start = time.perf_counter()

    try:
        with request.urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            latency = time.perf_counter() - start
            status = response.status

            if 200 <= status < 300:
                data = json.loads(response_body)
                images_done = data.get("count", expected_images)
                return {
                    "ok": True,
                    "status": status,
                    "latency": latency,
                    "images": images_done,
                    "error": "",
                }

            return {
                "ok": False,
                "status": status,
                "latency": latency,
                "images": 0,
                "error": response_body[:200],
            }

    except error.HTTPError as exc:
        latency = time.perf_counter() - start
        response_body = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": exc.code,
            "latency": latency,
            "images": 0,
            "error": response_body[:200],
        }

    except Exception as exc:
        latency = time.perf_counter() - start
        return {
            "ok": False,
            "status": "EXCEPTION",
            "latency": latency,
            "images": 0,
            "error": str(exc)[:200],
        }


def run_scenario(
    base_url: str,
    api_key: str,
    total_images: int,
    mode: str,
    batch_size: int,
    concurrency: int,
    timeout: int,
) -> dict:
    tasks = []

    if mode == "single":
        endpoint = f"{base_url}/classify"
        for i in range(total_images):
            tasks.append(
                {
                    "url": endpoint,
                    "payload": {"pixels": make_image(i)},
                    "expected_images": 1,
                }
            )
    else:
        endpoint = f"{base_url}/classify/batch"
        images = [make_image(i) for i in range(total_images)]

        for start in range(0, total_images, batch_size):
            chunk = images[start:start + batch_size]
            tasks.append(
                {
                    "url": endpoint,
                    "payload": {"images": chunk},
                    "expected_images": len(chunk),
                }
            )

    started = time.perf_counter()
    responses = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(
                post_json,
                task["url"],
                task["payload"],
                api_key,
                task["expected_images"],
                timeout,
            )
            for task in tasks
        ]

        for future in as_completed(futures):
            responses.append(future.result())

    total_time = time.perf_counter() - started

    latencies = [response["latency"] for response in responses]
    success_requests = sum(1 for response in responses if response["ok"])
    failed_requests = len(responses) - success_requests
    success_images = sum(response["images"] for response in responses if response["ok"])

    status_counts = {}
    for response in responses:
        status = str(response["status"])
        status_counts[status] = status_counts.get(status, 0) + 1

    return {
        "mode": mode,
        "total_images": total_images,
        "batch_size": batch_size,
        "concurrency": concurrency,
        "total_requests": len(tasks),
        "successful_requests": success_requests,
        "failed_requests": failed_requests,
        "successful_images": success_images,
        "total_time_s": round(total_time, 4),
        "requests_per_s": round(len(tasks) / total_time, 4) if total_time > 0 else 0,
        "images_per_s": round(success_images / total_time, 4) if total_time > 0 else 0,
        "avg_latency_ms": round((sum(latencies) / len(latencies)) * 1000, 2) if latencies else 0,
        "p50_latency_ms": round(percentile(latencies, 50) * 1000, 2),
        "p95_latency_ms": round(percentile(latencies, 95) * 1000, 2),
        "p99_latency_ms": round(percentile(latencies, 99) * 1000, 2),
        "max_latency_ms": round(max(latencies) * 1000, 2) if latencies else 0,
        "status_counts": json.dumps(status_counts, sort_keys=True),
    }


def main():
    parser = argparse.ArgumentParser(description="PixelWise API benchmark and stress test")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.getenv("SECRET_API_KEY", "dev-secret-key"))
    parser.add_argument("--total-images", type=int, default=100)
    parser.add_argument("--batch-sizes", default="5,10,25,50")
    parser.add_argument("--concurrency-levels", default="1,5,10")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--output", default="results/benchmark_results.csv")

    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    batch_sizes = parse_int_list(args.batch_sizes)
    concurrency_levels = parse_int_list(args.concurrency_levels)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    rows = []

    print(f"Benchmark target: {base_url}")
    print(f"Total images per scenario: {args.total_images}")
    print()

    for concurrency in concurrency_levels:
        row = run_scenario(
            base_url=base_url,
            api_key=args.api_key,
            total_images=args.total_images,
            mode="single",
            batch_size=1,
            concurrency=concurrency,
            timeout=args.timeout,
        )
        rows.append(row)
        print(row)

        for batch_size in batch_sizes:
            row = run_scenario(
                base_url=base_url,
                api_key=args.api_key,
                total_images=args.total_images,
                mode="batch",
                batch_size=batch_size,
                concurrency=concurrency,
                timeout=args.timeout,
            )
            rows.append(row)
            print(row)

    fieldnames = list(rows[0].keys())

    with open(args.output, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print()
    print(f"Wrote benchmark results to {args.output}")


if __name__ == "__main__":
    main()
