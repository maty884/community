import asyncio
import socket
import aiohttp
from aiohttp.resolver import DefaultResolver
async def main():
    ip = socket.gethostbyname("api.telegram.org")
    print("DNS:", ip)

    connector = aiohttp.TCPConnector(
        resolver=aiohttp.AsyncResolver() if False else None,
        use_dns_cache=True
    )

    original_getaddrinfo = connector._resolve_host

    async def resolve_host(host, port, traces=None):
        if host == "api.telegram.org":
            return [{
                "hostname": host,
                "host": ip,
                "port": port,
                "family": socket.AF_INET,
                "proto": 0,
                "flags": 0
            }]
        return await original_getaddrinfo(host, port, traces)

    connector._resolve_host = resolve_host

    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(
                "https://api.telegram.org",
                timeout=aiohttp.ClientTimeout(total=20)
            ) as response:
                print("HTTP status:", response.status)
    except Exception as e:
        print(type(e).__name__, e)

if __name__ == "__main__":
    asyncio.run(main())
