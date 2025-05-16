import time
import requests
import json
from collections import deque
from moralis import evm_api
#from telegram import Bot

# API URLs
OPENSEA_API_URL = "https://api.opensea.io/api/v2/collections/{collection_slug}/stats"
BLUR_API_URL = "https://api.blur.io/v1/collections/{collection_slug}"
MAGICEDEN_EVM_API_URL = "https://api-mainnet.magiceden.dev/v2/evm/collections/{collection_slug}/stats"

TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
MORALIS_API_KEY = ""


# Assign marketplaces per collection
NFT_PROJECTS = {
    "gemesis": {
        "opensea": "gemesis",
        "magiceden": "gemesis",
        "blur": "0xbe9371326f91345777b04394448c23e2bfeaa826"
    },
    "finalbosu": {
        "opensea": "finalbosu",
        # no Magic Eden yet
        "blur": "0xb792864e4659d0b8076f9c6912c228f914ec66d4"
    },
    "memelandcaptainz": {
        "opensea": "memelandcaptainz",
        "magiceden": "memelandcaptainz",
        "blur": "0x769272677fab02575e84945f03eca517acc544cc"
    },
    "lilpudgys": {
        "opensea": "lilpudgys",
        "magiceden": "lilpudgys",
        "blur": "0x524cab2ec69124574082676e6f654a18df49a048"
    },
    "pudgypenguins": {
        "opensea": "pudgypenguins",
        "magiceden": "pudgypenguins",
        "blur": "0xbd3531da5cf5857e7cfaa92426877b022e612cf8"
    },
    "pudgyrods": {
        "opensea": "pudgyrods",
        "magiceden": "pudgyrods",
        "blur": "0x062e691c2054de82f28008a8ccc6d7a1c8ce060d"
    }
}


RISE_THRESHOLD = 0.0001  # 0.1% up
FALL_THRESHOLD = -0.0001  # 0.1% down
CHECK_INTERVAL = 300  # Check for new price interval, in seconds
SPIKE_TIME_WINDOW = 3600  # how long historical prices will be saved, in seconds
ARBITRAGE_THRESHOLD = 0.001 # difference in floor prices between marketplaces lower than that value will be ignored

# History prices -> { collection_slug: { marketplace: deque([(timestamp, price), ...]) } }
historical_prices = {}

def get_floor_and_volume(slug, source):
    """Fetch the floor price and 1-day volume from a specific marketplace."""
    try:
        collection_identifier = NFT_PROJECTS[slug][source]  # this must be here ✅

        if source == "opensea":
            headers = {"X-API-KEY": "b40b29e1513c4137952736a1a072e8d8"}
            url = OPENSEA_API_URL.format(collection_slug=collection_identifier)
            #print(f"Opensea URL {url}")
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                #print(f"Raw response {data}")
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

        elif source == "blur":
            # You must store contract address in NFT_PROJECTS for 'blur'
            contract_address = collection_identifier
            url = f"https://deep-index.moralis.io/api/v2.2/nft/{contract_address}/metadata"
            headers = {"X-API-Key": MORALIS_API_KEY}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                floor_price = float(data.get("floor_price", 0))  # This key may not be returned, fallback to 0
                one_day_volume = float(data.get("volume_24h", 0))  # Same here
                #print(f"[Blur] Fetched floor: {floor_price} ETH | Volume: {one_day_volume} ETH")
                return floor_price, one_day_volume
            else:
                print(f"[Blur/Moralis] Error for {slug}: {response.status_code}, {response.text}")


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

    if difference >= ARBITRAGE_THRESHOLD:
        print(f"[{slug}] Floor price comparison:")
        print(f"🔻 Lowest: {cheapest_marketplace.capitalize()} @ {cheapest_price:.4f} ETH")
        print(f"🔺 Highest: {most_expensive_marketplace.capitalize()} @ {highest_price:.4f} ETH")
        print(f"📉 Difference: {difference:.4f} ETH")
        return True
    else:
        print(f"Arbitrage check for [{slug}]: floor difference below {ARBITRAGE_THRESHOLD:.4f} ETH")
        print()  # Blank line to separate collections
        return False


"""Fetch the max offer price (top bid) for a collection on a specific marketplace."""
def get_max_offer_price(slug, source):
    try:
        collection_identifier = NFT_PROJECTS[slug][source]

        if source == "opensea":
            # Get top bid (offer) from OpenSea offers API
            url = f"https://api.opensea.io/api/v2/offers/collection/{collection_identifier}?limit=1&order_by=price&order_direction=desc"
            headers = {"X-API-KEY": "b40b29e1513c4137952736a1a072e8d8"}
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()

                #print(json.dumps(data, indent=2)) # logging raw answer for debugging

                offers = data.get("offers", [])
                if offers:
                    raw_value = offers[0]["price"]["value"]
                    decimals = offers[0]["price"]["decimals"]
                    top_bid = int(raw_value) / (10 ** decimals)
                    print(f"Arbitrage check for [{slug}]: max offer on OpenSea: {top_bid:.4f} ETH")
                    return top_bid
                else:
                    print(f"[OpenSea] No offers found for {slug}")
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
                    print(f"Arbitrage check for [{slug}]: max offer on Magic Eden: {top_bid:.4f} ETH")
                    print()  # Blank line to separate collections
                    return float(top_bid)
            else:
                print(f"[Magic Eden] Offer fetch failed for {slug}: {response.status_code}")
                print()  # Blank line to separate collections

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

def check_arbitrage(slug, floor_prices, offer_prices):
    """Check for arbitrage between max offer and lowest floor price."""
    if offer_prices and floor_prices:
        max_offer_source, max_offer_price = max(offer_prices.items(), key=lambda x: x[1])
        min_floor_source, min_floor_price = min(floor_prices.items(), key=lambda x: x[1])

        diff = max_offer_price - min_floor_price

        print(f"Arbitrage check for [{slug}]: offer: {max_offer_price:.4f} ETH ({max_offer_source}), floor: {min_floor_price:.4f} ETH ({min_floor_source})")
        #diff = 10 # this line for testing telegram notofocations only
        if diff >= ARBITRAGE_THRESHOLD:
            print(f"💰 Arbitrage opportunity on [{slug}]!")
            print(f"📈 Top offer on {max_offer_source.capitalize()}: {max_offer_price:.4f} ETH")
            print(f"📉 Lowest floor on {min_floor_source.capitalize()}: {min_floor_price:.4f} ETH")
            print(f"📊 Profit margin: {diff:.4f} ETH")

            message = (
                f"💰 *Arbitrage Opportunity Detected!*\n\n"
                f"🔹 Collection: {slug}\n"
                f"📈 Offer on *{max_offer_source.capitalize()}*: {max_offer_price:.4f} ETH\n"
                f"📉 Floor on *{min_floor_source.capitalize()}*: {min_floor_price:.4f} ETH\n"
                f"📊 Potential Spread: *{diff:.4f} ETH*"
            )
            send_telegram_alert(message)
        else:
            print(f"No arbitrage opportunity on [{slug}] (Δ {diff:.4f} ETH)")
            print()  # Blank line


def analyze_price_movement(slug, marketplaces, one_day_volumes):
    """Analyze short-term floor price movements for each marketplace."""
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


def monitor_floor_prices():
    """Main monitoring loop."""
    global historical_prices

    for slug, marketplaces in NFT_PROJECTS.items():
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

            print(f"{slug} on {source.capitalize()}. Floor price: {current_price:.6f}, 1D volume: {one_day_volume:.2f}")

            if slug not in historical_prices:
                historical_prices[slug] = {}
            if source not in historical_prices[slug]:
                historical_prices[slug][source] = deque()

            historical_prices[slug][source].append((current_time, current_price))
            while historical_prices[slug][source] and historical_prices[slug][source][0][0] < current_time - SPIKE_TIME_WINDOW:
                historical_prices[slug][source].popleft()

        if len(floor_prices) < 2:
            print(f"Arbitrage check for [{slug}]: only one marketplace available, skipping arbitrage check.\n")
            continue

        has_difference = compare_floor_prices(slug, floor_prices)
        if not has_difference:
            continue

        offer_prices = {}
        for source in marketplaces:
            offer_price = get_max_offer_price(slug, source)
            if offer_price > 0:
                offer_prices[source] = offer_price

        # Check for arbitrage opportunities
        check_arbitrage(slug, floor_prices, offer_prices)

        # Check for floor price movements
        #analyze_price_movement(slug, marketplaces, one_day_volumes)

if __name__ == "__main__":
    while True:
        monitor_floor_prices()
        time.sleep(CHECK_INTERVAL)
