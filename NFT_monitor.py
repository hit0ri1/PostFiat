import time
import requests
from collections import deque
from telegram import Bot
import asyncio

# Configuration
OPENSEA_API_URL = "https://api.opensea.io/api/v2/collections/{collection_slug}/stats"

NFT_PROJECTS = ["gemesis", "finalbosu", "memelandcaptainz", "lilpudgys", "pudgypenguins", "pudgyrods"]  # Replace with your project slugs
RISE_THRESHOLD = 0.0001  # 1% increase
FALL_THRESHOLD = -0.0001  # 1% decrease
CHECK_INTERVAL = 10  # Check for new price interval, in seconds
SPIKE_TIME_WINDOW = 3600  # how long historical prices will be saved, in seconds

# Store historical floor prices for each project
historical_prices = {}

def get_opensea_floor_price(collection_slug):
    """Fetch the floor price of a collection from OpenSea's V2 REST API."""
    urlOpensea = OPENSEA_API_URL.format(collection_slug=collection_slug)

    headers = {
        "X-API-KEY": "b40b29e1513c4137952736a1a072e8d8",  # Replace with your actual OpenSea API key
    }
    try:
        response = requests.get(urlOpensea, headers=headers)
        if response.status_code == 200:
            data = response.json()
            # print(f"API response for {collection_slug}: {data}")
            if "total" in data and "floor_price" in data["total"]:
    	        print(f"{collection_slug} Current floor price is {float(data['total']['floor_price'])}")
    	        return float(data["total"]["floor_price"])

            else:
                print(f"No 'floor_price' found for {collection_slug}.")
        else:
            print(f"Error fetching floor price for {collection_slug}: {response.text}")
    except Exception as e:
        print(f"Exception occurred while fetching floor price for {collection_slug}: {e}")
    return None

async def send_telegram_alert(message):
    """Send a message to Telegram with error handling."""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print("Telegram alert sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")

def monitor_floor_prices():
    """Monitor floor prices and send alerts for significant changes."""
    global historical_prices
    for project in NFT_PROJECTS:
        current_price = get_opensea_floor_price(project)
        if current_price is None:
            print(f"Skipping {project} due to missing floor price.")
            continue

        # Initialize historical prices for the project if not already present
        if project not in historical_prices:
            historical_prices[project] = deque()

        # Add the current price with a timestamp
        current_time = time.time()
        historical_prices[project].append((current_time, current_price))

        # Remove outdated prices (older than SPIKE_TIME_WINDOW)
        while historical_prices[project] and historical_prices[project][0][0] < current_time - SPIKE_TIME_WINDOW:
            historical_prices[project].popleft()

        # Calculate percentage change if there are enough data points
        if len(historical_prices[project]) > 1:
            oldest_time, oldest_price = historical_prices[project][0]
            newest_time, newest_price = historical_prices[project][-1]

            # Calculate percentage change
            percent_change = (newest_price - oldest_price) / oldest_price

            # Check for spike rise or fall
            if percent_change >= RISE_THRESHOLD:
                direction = "rise"
                message = (
                    f"🚨 ALERT: Floor price {direction} detected for {project}!\n"
                    f"Timeframe: {SPIKE_TIME_WINDOW // 60} minutes\n"
                    f"Oldest Price: {oldest_price:.3f} ETH\n"
                    f"Newest Price: {newest_price:.3f} ETH\n"
                    f"Percentage Change: {percent_change * 100:.2f}%"
                )
                asyncio.run(send_telegram_alert(message))
            elif percent_change <= FALL_THRESHOLD:
                direction = "fall"
                message = (
                    f"🚨 ALERT: Floor price {direction} detected for {project}!\n"
                    f"Timeframe: {SPIKE_TIME_WINDOW // 60} minutes\n"
                    f"Oldest Price: {oldest_price:.3f} ETH\n"
                    f"Newest Price: {newest_price:.3f} ETH\n"
                    f"Percentage Change: {percent_change * 100:.2f}%"
                )
                asyncio.run(send_telegram_alert(message))

if __name__ == "__main__":
    while True:
        monitor_floor_prices()
        time.sleep(CHECK_INTERVAL)