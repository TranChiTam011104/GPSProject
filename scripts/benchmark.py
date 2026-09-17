#!/usr/bin/env python3
"""Benchmark sync vs async serving."""
import time
import argparse
from pathlib import Path
import sys


# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def benchmark_sync(num_requests: int = 100):
    """Benchmark synchronous serving."""
    from src.serving.sync import create_sync_server
    from src.models.heuristic import create_heuristic_classifier
    
    classifier = create_heuristic_classifier()
    server = create_sync_server(classifier)
    
    # Generate test data
    test_data = [
        {
            "user_id": f"user_{i}",
            "stay_points": [
                {
                    "lat": 39.9847 + i * 0.001,
                    "lng": 116.3184 + i * 0.001,
                    "arrival_time": "2024-01-01T22:00:00",
                    "departure_time": "2024-01-02T06:00:00"
                }
            ]
        }
        for i in range(num_requests)
    ]
    
    print(f"\n=== Sync Serving Benchmark ({num_requests} requests) ===")
    
    start_time = time.time()
    results = server.serve_batch(test_data)
    total_time = time.time() - start_time
    
    successful = sum(1 for r in results if r.get("success"))
    latencies = [r.get("latency_ms", 0) for r in results]
    
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    throughput = num_requests / total_time
    
    print(f"Total time: {total_time:.2f}s")
    print(f"Throughput: {throughput:.1f} req/s")
    print(f"Avg latency: {avg_latency:.2f}ms")
    print(f"Successful: {successful}/{num_requests}")
    
    return {
        "total_time": total_time,
        "throughput": throughput,
        "avg_latency": avg_latency,
        "successful": successful
    }


def benchmark_async(num_jobs: int = 100):
    """Benchmark asynchronous serving."""
    from src.serving.async_serving import create_async_server
    from src.models.heuristic import create_heuristic_classifier
    
    classifier = create_heuristic_classifier()
    server = create_async_server(classifier)
    
    print(f"\n=== Async Serving Benchmark ({num_jobs} jobs) ===")
    
    # Submit jobs
    start_time = time.time()
    job_ids = []
    
    for i in range(num_jobs):
        job_id = server.submit_job(
            f"user_{i}",
            [
                {
                    "lat": 39.9847 + i * 0.001,
                    "lng": 116.3184 + i * 0.001,
                    "arrival_time": "2024-01-01T22:00:00",
                    "departure_time": "2024-01-02T06:00:00"
                }
            ]
        )
        job_ids.append(job_id)
    
    submit_time = time.time() - start_time
    
    # Process jobs
    process_start = time.time()
    for job_id in job_ids:
        server.process_job(job_id)
    process_time = time.time() - process_start
    
    print(f"Submit time: {submit_time:.2f}s")
    print(f"Process time: {process_time:.2f}s")
    print(f"Total jobs: {num_jobs}")
    
    return {
        "submit_time": submit_time,
        "process_time": process_time,
        "total_jobs": num_jobs
    }


def main():
    """Main benchmark function."""
    parser = argparse.ArgumentParser(description="Benchmark serving strategies")
    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Number of requests"
    )
    parser.add_argument(
        "--mode",
        choices=["sync", "async", "both"],
        default="both",
        help="Benchmark mode"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Serving Strategy Benchmark")
    print("=" * 60)
    
    if args.mode in ["sync", "both"]:
        sync_results = benchmark_sync(args.requests)
    
    if args.mode in ["async", "both"]:
        async_results = benchmark_async(args.requests)
    
    print("\n" + "=" * 60)
    print("Benchmark complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
