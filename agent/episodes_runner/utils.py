import time


def live_timer(seconds: int | float):
    start_time = time.perf_counter()
    try:
        while True:
            elapsed = time.perf_counter() - start_time
            if elapsed >= seconds:
                break
            print(f"\rElapsed time: {elapsed:.0f} seconds", end="", flush=True)

            time.sleep(0.5)  # Update frequently for a smooth look
    except KeyboardInterrupt:
        print("\nTimer stopped.")
