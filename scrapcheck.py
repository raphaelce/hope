import asyncio
import aiohttp
import aiofiles
import ipaddress
import concurrent.futures
import os
import time
import requests
from bs4 import BeautifulSoup

# ================= CONFIG =================

TIMEOUT = 5
MAX_WORKERS = 120
CONCURRENCY = 1000  # Maximum concurrent requests for async
CHECK_URL_HTTP = "http://icanhazip.com"  # HTTP proxy check endpoint
CHECK_URL_SOCKS = "http://httpbin.org/ip"  # SOCKS proxy check endpoint

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
    """Fetch a single proxy source and extract IP:PORTs."""
    found = set()
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return p_type, found

        text = r.text.replace("\ufeff", "")

        # If HTML, extract text
        if "<" in text and ">" in text:
            text = BeautifulSoup(text, "lxml").get_text()

        for line in text.splitlines():
            line = line.strip()
            if line:
                found.add(line)

    except Exception:
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

    proxies["http"] = list(proxies["http"])
    proxies["socks4"] = list(proxies["socks4"])
    proxies["socks5"] = list(proxies["socks5"])

    print(f"[✓] Scraped {len(proxies['http'])} HTTP | {len(proxies['socks4'])} SOCKS4 | {len(proxies['socks5'])} SOCKS5 proxies")
    return proxies


# ================= ASYNC PROXY CHECK =================

async def check_proxy(session, proxy, p_type):
    """Check if proxy is alive. Return proxy if alive else None."""
    if p_type == "http":
        proxies = {
            "http": f"http://{proxy}",
            "https": f"http://{proxy}",
        }
        target_url = CHECK_URL_HTTP
    else:
        proxies = {
            "http": f"{p_type}://{proxy}",
            "https": f"{p_type}://{proxy}",
        }
        target_url = CHECK_URL_SOCKS

    try:
        async with session.get(target_url, proxy=proxies.get("http"), timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return None

            text = await resp.text()
            # For icanhazip.com, it's just the IP
            try:
                ipaddress.ip_address(text.strip())
                return proxy
            except ValueError:
                # For httpbin.org/ip, check JSON
                try:
                    data = await resp.json()
                    if "origin" in data:
                        return proxy
                except:
                    return None
    except:
        return None

# ================= FILE PROCESSING =================

async def process_file(input_file, output_file, p_type):
    if not os.path.exists(input_file):
        print(f"[!] File {input_file} not found. Skipping {p_type}")
        return 0

    async with aiofiles.open(input_file, "r") as f:
        proxies = [line.strip() for line in await f.readlines() if line.strip()]

    print(f"[+] Checking {len(proxies)} {p_type} proxies...")

    valid_proxies = []
    start_time = time.time()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for proxy in proxies:
            tasks.append(check_proxy(session, proxy, p_type))

        results = await asyncio.gather(*tasks)

        for i, result in enumerate(results, 1):
            if result:
                valid_proxies.append(result)
            if i % 50 == 0 or i == len(proxies):
                elapsed = time.time() - start_time
                print(f"  Checked {i}/{len(proxies)} | Live: {len(valid_proxies)} | {elapsed:.1f}s", end="\r")

    # Save live proxies
    os.makedirs("checked", exist_ok=True)
    async with aiofiles.open(output_file, "w") as f:
        for p in sorted(valid_proxies):
            await f.write(f"{p}\n")

    print(f"\n[✓] {len(valid_proxies)} live {p_type} proxies saved to {output_file}")
    return len(valid_proxies)

# ================= MAIN =================

async def main():
    # Scrape proxies first
    proxies = scrape_proxies()

    os.makedirs("checked", exist_ok=True)

    # Now check the validity of proxies asynchronously and save results
    live_http = await process_file("scraped/http_proxies.txt", "checked/http_live.txt", "http")
    live_socks4 = await process_file("scraped/socks4_proxies.txt", "checked/socks4_live.txt", "socks4")
    live_socks5 = await process_file("scraped/socks5_proxies.txt", "checked/socks5_live.txt", "socks5")

    print(f"\nSummary: HTTP={live_http}, SOCKS4={live_socks4}, SOCKS5={live_socks5}")

if __name__ == "__main__":

    asyncio.run(main())
