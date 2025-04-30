import time
import requests
from collections import deque
#from telegram import Bot
import requests

# API URLs
OPENSEA_API_URL = "https://api.opensea.io/api/v2/collections/{collection_slug}/stats"
BLUR_API_URL = "https://api.blur.io/v1/collections/{collection_slug}"
MAGICEDEN_EVM_API_URL = "https://api-mainnet.magiceden.dev/v2/evm/collections/{collection_slug}/stats"

TELEGRAM_BOT_TOKEN = "7539585423:AAHaS4keQ73kTiMtzsc_-bcst2hgxyrrWTM"
TELEGRAM_CHAT_ID = "436804823"

# Assign marketplaces per collection
NFT_PROJECTS = {
    "gemesis": {
        "opensea": "gemesis",
        "magiceden": "gemesis"
    },
    "finalbosu": {
        "opensea": "finalbosu",
        # no Magic Eden yet
    },
    "memelandcaptainz": {
        "opensea": "memelandcaptainz",
        "magiceden": "memelandcaptainz"
    },
    "lilpudgys": {
        "opensea": "lilpudgys",
        "magiceden": "lilpudgys"
    },
    "pudgypenguins": {
        "opensea": "pudgypenguins",
        "magiceden": "pudgypenguins"
    },
    "pudgyrods": {
        "opensea": "pudgyrods",
        "magiceden": "pudgyrods"
    }
}


RISE_THRESHOLD = 0.0001  # 0.1% up
FALL_THRESHOLD = -0.0001  # 0.1% down
CHECK_INTERVAL = 300  # Check for new price interval, in seconds
SPIKE_TIME_WINDOW = 3600  # how long historical prices will be saved, in seconds

# History prices -> { collection_slug: { marketplace: deque([(timestamp, price), ...]) } }
historical_prices = {}

def get_floor_and_volume(slug, source):
    """Fetch the floor price and 1-day volume from a specific marketplace."""
    try:
        collection_identifier = NFT_PROJECTS[slug][source]  # this must be here ✅

        if source == "opensea":
            headers = {"X-API-KEY": "b40b29e1513c4137952736a1a072e8d8"}
            url = OPENSEA_API_URL.format(collection_slug=collection_identifier)
            print(f"Opensea URL {url}")
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                print(f"Raw response {data}")
                floor_price = float(data["total"]["floor_price"])
                one_day_volume = data["intervals"][0]["volume"]
                one_day_volume = round(one_day_volume, 2)
                return floor_price, one_day_volume
            else:
                print(f"[OpenSea] Error for {slug}: {response.status_code}")

        elif source == "magiceden":
            url = f"https://api-mainnet.magiceden.dev/v3/rtp/ethereum/collections/v7?slug={slug}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                collections = data.get("collections", [])
                if collections:
                    floor_price = collections[0].get("floorAsk", {}).get("price", {}).get("amount", {}).get("native", 0)
                    one_day_volume = collections[0].get("volume", {}).get("1day", {})
                    one_day_volume = round(one_day_volume, 2)
                    return floor_price, one_day_volume
                else:
                    print(f"[Magic Eden] No collections found for {slug}")
            else:
                print(f"[Magic Eden] Error for {slug}: {response.status_code}")

        #elif source == "blur":
        #    url = BLUR_API_URL.format(collection_slug=slug)
        #    response = requests.get(url)
        #    if response.status_code == 200:
        #        data = response.json()
        #        print(f"{slug} on Blur. Current floor price is {float(data['floorPrice']) / 1e18}")
        #        return float(data["floorPrice"]) / 1e18
        #    else:
        #        print(f"[Blur] Error for {slug}: {response.status_code}")

    except Exception as e:
        print(f"Exception while fetching {slug} from {source}: {e}")

    return None, None






"""Compare floor prices of a collection across marketplaces."""
def compare_floor_prices(slug, floor_prices):
    sources = list(floor_prices.keys())
    if len(sources) < 2:
        return False

    sorted_sources = sorted(floor_prices.items(), key=lambda x: x[1])
    cheapest_marketplace, cheapest_price = sorted_sources[0]
    most_expensive_marketplace, highest_price = sorted_sources[-1]
    difference = highest_price - cheapest_price

    if difference >= 0.001:
        print(f"[{slug}] Floor price comparison:")
        print(f"🔻 Lowest: {cheapest_marketplace.capitalize()} @ {cheapest_price:.4f} ETH")
        print(f"🔺 Highest: {most_expensive_marketplace.capitalize()} @ {highest_price:.4f} ETH")
        print(f"📉 Difference: {difference:.6f} ETH")
        return True
    else:
        print(f"[{slug}] No significant floor difference (Δ {difference:.6f} ETH)")
        return False


"""Fetch the max offer price (top bid) for a collection on a specific marketplace."""
def get_max_offer_price(slug, source):
    try:
        collection_identifier = NFT_PROJECTS[slug][source]

        if source == "opensea":
            url = f"https://api.opensea.io/api/v2/collections/{collection_identifier}/stats"
            headers = {"X-API-KEY": "b40b29e1513c4137952736a1a072e8d8"}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                # OpenSea doesn't expose top bid easily — this is a placeholder.
                # Will be replaced once bid API access is confirmed.
                top_bid = float(data["total"].get("top_bid", 0)) or 0.0
                print(f"[{slug}] Max offer on OpenSea: {top_bid:.6f} ETH")
                return top_bid
            else:
                print(f"[OpenSea] Offer fetch failed for {slug}: {response.status_code}")

        elif source == "magiceden":
            url = f"https://api-mainnet.magiceden.dev/v3/rtp/ethereum/collections/v7?slug={slug}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                collections = data.get("collections", [])
                if collections:
                    top_bid = collections[0].get("topBid", {}).get("price", {}).get("amount", {}).get("native", 0)
                    print(f"[{slug}] Max offer on Magic Eden: {top_bid:.6f} ETH")
                    return float(top_bid)
            else:
                print(f"[Magic Eden] Offer fetch failed for {slug}: {response.status_code}")

    except Exception as e:
        print(f"[{slug}] Error getting offer from {source}: {e}")

    return 0.0  # fallback



def send_telegram_alert(message):
    """Send a Telegram message using the raw Telegram Bot API (no async, full logging)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        response = requests.post(url, data=payload)
        print(f"Telegram alert sent. Status code: {response.status_code}")
        print(f"Telegram API response: {response.text}")
    except Exception as e:
        print(f"Error sending Telegram alert: {e}")

def monitor_floor_prices():
    """Main monitoring loop."""
    global historical_prices

    for slug, marketplaces in NFT_PROJECTS.items():
        if len(marketplaces) < 2:
            print(f"[{slug}] Only one marketplace available, skipping arbitrage check.")
            continue

        current_time = time.time()
        floor_prices = {}
        one_day_volumes = {}

        # Fetch floor price and volume once per source
        for source in marketplaces:
            current_price, one_day_volume = get_floor_and_volume(slug, source)
            if current_price is None:
                continue

            floor_prices[source] = current_price
            one_day_volumes[source] = one_day_volume

            # Print floor and volume info
            print(f"{slug} on {source.capitalize()}. Floor price: {current_price:.6f}, 1D volume: {one_day_volume:.2f}")

            # Initialize history if needed
            if slug not in historical_prices:
                historical_prices[slug] = {}
            if source not in historical_prices[slug]:
                historical_prices[slug][source] = deque()

            # Update price history
            historical_prices[slug][source].append((current_time, current_price))
            while historical_prices[slug][source] and historical_prices[slug][source][0][0] < current_time - SPIKE_TIME_WINDOW:
                historical_prices[slug][source].popleft()

        # Skip further analysis if not enough marketplaces
        if len(floor_prices) < 2:
            continue

        # Compare floor prices
        has_difference = compare_floor_prices(slug, floor_prices)
        if not has_difference:
            continue

        # Log top offers only if arbitrage potential exists
        for source in marketplaces:
            get_max_offer_price(slug, source)

        # Analyze price movement
        for source in marketplaces:
            if slug not in historical_prices or source not in historical_prices[slug]:
                continue
            if len(historical_prices[slug][source]) > 1:
                oldest_time, oldest_price = historical_prices[slug][source][0]
                newest_time, newest_price = historical_prices[slug][source][-1]

                percent_change = (newest_price - oldest_price) / oldest_price

                if percent_change >= RISE_THRESHOLD:
                    direction = "rise"
                elif percent_change <= FALL_THRESHOLD:
                    direction = "fall"
                else:
                    direction = None

                if direction:
                    volume = one_day_volumes.get(source, 0.0)
                    message = (
                        f"🚨 {slug} floor price {direction} detected!\n"
                        f"Marketplace: {source.capitalize()}\n"
                        f"Timeframe: {SPIKE_TIME_WINDOW // 60} min\n"
                        f"Old: {oldest_price:.4f} ETH → New: {newest_price:.4f} ETH\n"
                        f"Change: {percent_change * 100:.2f}%\n"
                        f"1-Day Volume: {volume:.2f} ETH"
                    )
                    send_telegram_alert(message)

if __name__ == "__main__":
    while True:
        monitor_floor_prices()
        time.sleep(CHECK_INTERVAL)