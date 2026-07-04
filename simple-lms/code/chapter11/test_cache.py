import time

try:
    from chapter11.weather_api import build_cache_key, get_redis_client, get_weather
except ModuleNotFoundError:
    from weather_api import build_cache_key, get_redis_client, get_weather


def main():
    city = "Jakarta"
    redis_client = get_redis_client()
    cache_key = build_cache_key(city)

    # Reset key agar panggilan pertama pasti miss
    redis_client.delete(cache_key)

    start = time.time()
    result1 = get_weather(city)
    time1 = time.time() - start
    print(f"First call: {time1:.2f}s")
    print(f"First result cache status: {result1['cache_status']}")

    start = time.time()
    result2 = get_weather(city)
    time2 = time.time() - start
    print(f"Second call (cached): {time2:.2f}s")
    print(f"Second result cache status: {result2['cache_status']}")

    current_ttl = redis_client.ttl(cache_key)
    print(f"Current TTL: {current_ttl}s")
    print(
        "Third call after cache expired (300 detik) akan kembali lambat karena "
        "Redis sudah menghapus key dan fungsi harus memanggil API lagi."
    )


if __name__ == "__main__":
    main()
