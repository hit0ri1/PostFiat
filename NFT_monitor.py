import time
import requests
from collections import deque
from telegram import Bot
import asyncio

# API URLs
OPENSEA_API_URL = "https://api.opensea.io/api/v2/collections/{collection_slug}/stats"
BLUR_API_URL = "https://api.blur.io/v1/collections/{collection_slug}"
MAGICEDEN_EVM_API_URL = "https://api-mainnet.magiceden.dev/v2/evm/collections/{collection_slug}/stats"

TELEGRAM_BOT_TOKEN = "HIDDEN_FOR_SECURITY_REASONS"
TELEGRAM_CHAT_ID = "HIDDEN_FOR_SECURITY_REASONS"

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
CHECK_INTERVAL = 10  # Check for new price interval, in seconds
SPIKE_TIME_WINDOW = 3600  # how long historical prices will be saved, in seconds

# History prices -> { collection_slug: { marketplace: deque([(timestamp, price), ...]) } }
historical_prices = {}

def get_floor_and_volume(slug, source):
    """Fetch the floor price from a specific marketplace."""
    try:
        collection_identifier = NFT_PROJECTS[slug][source]  # this must be here ✅

        if source == "opensea":
            headers = {"X-API-KEY": "HIDDEN_FOR_SECURITY_REASONS"}
            url = OPENSEA_API_URL.format(collection_slug=collection_identifier)
            #print(f"URL for OpenSea: {url}")
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                floor_price = float(data["total"]["floor_price"])
                one_day_volume = data["intervals"][0]["volume"]
                print(f"{slug} on OpenSea. Floor price: {floor_price}, 1D volume: {one_day_volume}")
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
                    print(f"{slug} on Magic Eden. Floor price: {floor_price}, 1D volume: {one_day_volume}")
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

    return None

async def send_telegram_alert(message):
    """Send a Telegram message."""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print("Telegram alert sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def monitor_floor_prices():
    """Main monitoring loop."""
    global historical_prices

    for slug, marketplaces in NFT_PROJECTS.items():
        for source in marketplaces:
            current_price, one_day_volume = get_floor_and_volume(slug, source)
            if current_price is None:
                continue

            # Initialize history
            if slug not in historical_prices:
                historical_prices[slug] = {}
            if source not in historical_prices[slug]:
                historical_prices[slug][source] = deque()

            # Add new price
            current_time = time.time()
            historical_prices[slug][source].append((current_time, current_price))

            # Remove old entries
            while historical_prices[slug][source] and historical_prices[slug][source][0][0] < current_time - SPIKE_TIME_WINDOW:
                historical_prices[slug][source].popleft()

            # Analyze price movement
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
                    message = (
                        f"🚨 {slug} floor price {direction} detected!\n"
                        f"Marketplace: {source.capitalize()}\n"
                        f"Timeframe: {SPIKE_TIME_WINDOW // 60} min\n"
                        f"Old: {oldest_price:.4f} ETH → New: {newest_price:.4f} ETH\n"
                        f"Change: {percent_change * 100:.2f}%\n"
                        f"1-Day Volume: {one_day_volume:.2f} ETH"
                    )
                    asyncio.run(send_telegram_alert(message))

if __name__ == "__main__":
    while True:
        monitor_floor_prices()
        time.sleep(CHECK_INTERVAL)