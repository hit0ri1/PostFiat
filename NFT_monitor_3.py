import time
import requests
from collections import deque

# API URLs
MAGICEDEN_EVM_API_URL = "https://api-mainnet.magiceden.dev/v3/rtp/ethereum/users/{wallet_address}/tokens/v7?normalizeRoyalties=false&sortBy=acquiredAt&sortDirection=desc&limit=100&includeTopBid=false&includeAttributes=false&includeLastSale=false&includeRawData=true&filterSpamTokens=true&useNonFlaggedFloorAsk=false"

# Telegram Config
TELEGRAM_BOT_TOKEN = "7539585423:AAHaS4keQ73kTiMtzsc_-bcst2hgxyrrWTM"
TELEGRAM_CHAT_ID = "436804823"
WALLET_ADDRESS = "0x7075f3b9C1c9fB099D000Ebb7676B1A972c2348E"
API_KEY = "YOUR_API_KEY"  # Replace with your Magic Eden API key

# Keywords to scan in metadata
KEYWORDS = ["orbiter", "jumper", "relay", "stargate"]

# Monitoring Parameters
METADATA_CHECK_INTERVAL = 43200  # Metadata check every 12 hours

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload)
        print(f"[Telegram] Sent. Status: {response.status_code}")
    except Exception as e:
        print(f"[Telegram] Error: {e}")

def extract_contract_address(contract_field):
    if isinstance(contract_field, dict):
        return contract_field.get("address")
    return contract_field

# Define API URLs for different chains
MAGICEDEN_EVM_API_URLS = {
    "ethereum": "https://api-mainnet.magiceden.dev/v3/rtp/ethereum/users/{wallet_address}/tokens/v7?normalizeRoyalties=false&sortBy=acquiredAt&sortDirection=desc&limit=10&includeTopBid=false&includeAttributes=false&includeLastSale=false&includeRawData=true&filterSpamTokens=true&useNonFlaggedFloorAsk=false",
    "polygon": "https://api-mainnet.magiceden.dev/v3/rtp/polygon/users/{wallet_address}/tokens/v7?normalizeRoyalties=false&sortBy=acquiredAt&sortDirection=desc&limit=10&includeTopBid=false&includeAttributes=false&includeLastSale=false&includeRawData=true&filterSpamTokens=true&useNonFlaggedFloorAsk=false",
    "abstract": "https://api-mainnet.magiceden.dev/v3/rtp/abstract/users/{wallet_address}/tokens/v7?normalizeRoyalties=false&sortBy=acquiredAt&sortDirection=desc&limit=10&includeTopBid=false&includeAttributes=false&includeLastSale=false&includeRawData=true&filterSpamTokens=true&useNonFlaggedFloorAsk=false",
}

# List of chains to search in order
CHAIN_ORDER = ["ethereum", "polygon", "abstract"]  # Modify this order as needed

# Function to check metadata for keywords across multiple chains
def check_metadata_for_keywords():
    print(f"🔎 Checking NFTs in wallet {WALLET_ADDRESS} for keywords...")

    # Track whether we've found NFTs on any chain
    for chain in CHAIN_ORDER:
        print(f"🔄 Searching on {chain.capitalize()}...")

        # Fetch the appropriate URL for the current chain
        MAGICEDEN_EVM_API_URL = MAGICEDEN_EVM_API_URLS.get(chain)

        try:
            url = MAGICEDEN_EVM_API_URL.format(wallet_address=WALLET_ADDRESS)

            headers = {
                "accept": "*/*",
                "Authorization": f"Bearer {API_KEY}"
            }

            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                print(f"[{chain.capitalize()}] Error fetching NFTs: {response.status_code} - {response.text}")
                continue  # Move to the next chain if there's an error

            try:
                data = response.json()
            except Exception as json_error:
                print(f"❌ Error parsing response JSON: {json_error}")
                continue

            # Ensure we have the 'tokens' field in the response
            nfts = data.get("tokens", [])
            if not nfts:
                print(f"❌ No NFTs found in {chain.capitalize()} chain response.")
                continue

            # Process the NFTs from this chain
            seen_ids = set()
            total_checked = 0
            max_nfts = 200

            for nft in nfts:
                try:
                    # Get contract address and token id from the nested 'token' field
                    token = nft.get("token", {})
                    contract_address = token.get("contract")  # Inside 'token'
                    identifier = token.get("tokenId")         # Inside 'token'

                    # Check if contract_address or token_id is missing
                    if not contract_address or not identifier:
                        print(f"❌ Missing contract or tokenId for NFT: {token.get('name')}")
                        continue

                    # Skip spam tokens
                    is_spam = token.get('collection', {}).get('isSpam', False)
                    if is_spam:
                        continue

                    unique_id = f"{contract_address}_{identifier}"
                    if unique_id in seen_ids:
                        continue

                    seen_ids.add(unique_id)
                    total_checked += 1
                    if total_checked >= max_nfts:
                        break

                    # Now we correctly fetch name and description from 'token' field
                    # Fetch name and description from 'token' field
                    name = token.get("name", "Unnamed NFT")
                    description = token.get("description", "No description available")
                    
                    # Check for None and strip safely
                    name = name if name else "Unnamed NFT"
                    description = description if description else "No description available"
                    
                    # Now it's safe to apply .strip() because name and description are guaranteed to be non-None
                    name = name.strip()
                    description = description.strip()
                    
                    # Build the Magic Eden item URL
                    item_url = f"https://magiceden.io/item-details/{chain}/{contract_address}/{identifier}"
                    print(f"🔍 Searching keywords in: {name} ")

                    name_lower = name.lower()
                    description_lower = description.lower()

                    # Check if any keyword is in the name or description
                    for word in KEYWORDS:
                        if word in name_lower:
                            message = (
                                f"🔔 Keyword alert in wallet NFT!\n"
                                f"Chain: {chain.capitalize()}\n"
                                f"Name: {name}\n"
                                f"Description: {description}\n"
                                f"Match: {word} (in Name)\n"
                                f"Link: {item_url}"
                            )
                            send_telegram_alert(message)
                            break  # Stop after sending the alert for the matched keyword in name
                        elif word in description_lower:
                            message = (
                                f"🔔 Keyword alert in wallet NFT!\n"
                                f"Chain: {chain.capitalize()}\n"
                                f"Name: {name}\n"
                                f"Description: {description}\n"
                                f"Match: {word} (in Description)\n"
                                f"Link: {item_url}"
                            )
                            send_telegram_alert(message)
                            break  # Stop after sending the alert for the matched keyword in description


                except Exception as nft_error:
                    print(f"❌ Error processing NFT: {nft_error}")
                    continue

            print(f"✅ Metadata check completed on {chain.capitalize()}.")

        except Exception as e:
            print(f"[{chain.capitalize()}] Metadata check failed: {e}")

    print("✅ Finished checking all chains for keywords.")

if __name__ == "__main__":
    last_metadata_check = 0

    while True:
        current_time = time.time()

        # Check for metadata every 12 hours
        if current_time - last_metadata_check >= METADATA_CHECK_INTERVAL:
            check_metadata_for_keywords()
            last_metadata_check = current_time

        # Sleep for a while before checking again
        time.sleep(METADATA_CHECK_INTERVAL)

