import asyncio
import aiohttp
import aiofiles
import ipaddress
import os
import time
import requests
import concurrent.futures
from bs4 import BeautifulSoup

# ================= CONFIG =================

TIMEOUT = 10
MAX_WORKERS = 120
CONCURRENCY = 300  # Safe for GitHub Actions
CHECK_URL_HTTP = "http://httpbin.org/ip"
CHECK_URL_SOCKS = "http://httpbin.org/ip"

SOURCES = [
    # HTTP / HTTPS
    ("http", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=displayproxies&protocol=http&timeout=10000"),
    ("http", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=displayproxies&protocol=https&timeout=5000"),
    ("http", "https://proxyspace.pro/http.txt"),
    ("http", "https://proxyspace.pro/https.txt"),
    ("http", "https://vakhov.github.io/fresh-proxy-list/http.txt"),
    ("http", "https://vakhov.github.io/fresh-proxy-list/https.txt"),
    ("http", "https://raw.githubusercontent.com/zloi-user/hideip.me/master/http.txt"),
    ("http", "https://raw.githubusercontent.com/zloi-user/hideip.me/master/https.txt"),
    ("http", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"),
    ("http", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"),
    ("http", "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt"),
    ("http", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt"),
    ("http", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt"),
    ("http", "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt"),

    # SOCKS4
    ("socks4", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=displayproxies&protocol=socks4&timeout=10000"),
    ("socks4", "https://proxyspace.pro/socks4.txt"),
    ("socks4", "https://vakhov.github.io/fresh-proxy-list/socks4.txt"),
    ("socks4", "https://raw.githubusercontent.com/zloi-user/hideip.me/master/socks4.txt"),
    ("socks4", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt"),
    ("socks4", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt"),
    ("socks4", "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt"),
    ("socks4", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt"),
    ("socks4", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks4/data.txt"),
    ("socks4", "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/socks4_proxies.txt"),

    # SOCKS5
    ("socks5", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=displayproxies&protocol=socks5&timeout=10000"),
    ("socks5", "https://proxyspace.pro/socks5.txt"),
    ("socks5", "https://vakhov.github.io/fresh-proxy-list/socks5.txt"),
    ("socks5", "https://raw.githubusercontent.com/zloi-user/hideip.me/master/socks5.txt"),
    ("socks5", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt"),
    ("socks5", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt"),
    ("socks5", "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt"),
    ("socks5", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt"),
    ("socks5", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt"),
    ("socks5", "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/socks5_proxies.txt"),
]

# ================= SCRAPING =================

def fetch_source(p_type, url):
    found = set()
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return p_type, found

        text = r.text.replace("\ufeff", "")

        if "<" in text and ">" in text:
            text = BeautifulSoup(text, "lxml").get_text()

        for line in text.splitlines():
            line = line.strip()
            if line and ":" in line:
                found.add(line)

    except:
        pass

    return p_type, found


def scrape_proxies():
    proxies = {"http": set(), "socks4": set(), "socks5": set()}
    print(f"[+] Scraping {len(SOURCES)} sources...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(fetch_source, p_type, url) for p_type, url in SOURCES]

        for future in concurrent.futures.as_completed(futures):
            p_type, found = future.result()
            proxies[p_type].update(found)

    print(
        f"[✓] Scraped {len(proxies['http'])} HTTP | "
        f"{len(proxies['socks4'])} SOCKS4 | "
        f"{len(proxies['socks5'])} SOCKS5 proxies"
    )

    return proxies


# ================= PROXY CHECK =================

async def check_proxy(session, proxy, p_type):
    proxy_url = f"{p_type}://{proxy}"

    for attempt in range(2):  # 1 retry
        try:
            async with session.get(
                CHECK_URL_HTTP,
                proxy=proxy_url,
            ) as resp:

                if resp.status != 200:
                    continue

                text = await resp.text()

                try:
                    ipaddress.ip_address(text.strip())
                    return proxy
                except ValueError:
                    try:
                        data = await resp.json()
                        if "origin" in data:
                            return proxy
                    except:
                        pass

        except:
            if attempt == 1:
                return None

    return None


# ================= CHECK FILE =================

async def process_file(input_file, output_file, p_type):
    if not os.path.exists(input_file):
        print(f"[!] File {input_file} not found. Skipping {p_type}")
        return 0

    async with aiofiles.open(input_file, "r") as f:
        proxies = [line.strip() for line in await f.readlines() if line.strip()]

    print(f"[+] Checking {len(proxies)} {p_type} proxies...")

    valid = []
    start = time.time()
    semaphore = asyncio.Semaphore(CONCURRENCY)

    timeout = aiohttp.ClientTimeout(total=TIMEOUT)

    async with aiohttp.ClientSession(timeout=timeout) as session:

        async def bounded(proxy):
            async with semaphore:
                return await check_proxy(session, proxy, p_type)

        tasks = [bounded(p) for p in proxies]

        for i, future in enumerate(asyncio.as_completed(tasks), 1):
            result = await future
            if result:
                valid.append(result)

            if i % 50 == 0 or i == len(proxies):
                elapsed = time.time() - start
                print(
                    f"  Checked {i}/{len(proxies)} | "
                    f"Live: {len(valid)} | "
                    f"{elapsed:.1f}s",
                    end="\r",
                )

    os.makedirs("checked", exist_ok=True)

    async with aiofiles.open(output_file, "w") as f:
        for p in sorted(valid):
            await f.write(p + "\n")

    print(f"\n[✓] {len(valid)} live {p_type} proxies saved to {output_file}")
    return len(valid)


# ================= MAIN =================

async def main():
    proxies = scrape_proxies()

    # Save scraped proxies
    os.makedirs("scraped", exist_ok=True)
    for p_type in proxies:
        with open(f"scraped/{p_type}_proxies.txt", "w") as f:
            for proxy in proxies[p_type]:
                f.write(proxy + "\n")

    print("[✓] Scraped proxies saved.")

    live_http = await process_file("scraped/http_proxies.txt", "checked/http_live.txt", "http")
    live_socks4 = await process_file("scraped/socks4_proxies.txt", "checked/socks4_live.txt", "socks4")
    live_socks5 = await process_file("scraped/socks5_proxies.txt", "checked/socks5_live.txt", "socks5")

    print(f"\nSummary: HTTP={live_http}, SOCKS4={live_socks4}, SOCKS5={live_socks5}")


if __name__ == "__main__":
    asyncio.run(main())

