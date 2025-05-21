import nextcord as discord
from nextcord import Client, Intents
import gspread
import asyncio
import re
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import logging

DISCORD_BOT_TOKEN = 'HIDDEN_FOR_SECURITY_REASONS'
DISCORD_CHANNEL_ID = 1340653770974957652
GOOGLE_SHEET_FILE_NAME = 'Bridge spreadsheet'
GOOGLE_SHEET_NAME = 'PFT_tasks_compilation_2'
JSON_KEY_PATH = 'HIDDEN_FOR_SECURITY_REASONS'

# Google Sheets setup
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_PATH, scope)
gs_client = gspread.authorize(creds)
try:
    sheet = gs_client.open(GOOGLE_SHEET_FILE_NAME).worksheet(GOOGLE_SHEET_NAME)
except gspread.exceptions.WorksheetNotFound:
    print(f"Sheet tab '{GOOGLE_SHEET_NAME}' not found.")
    exit()

# Discord client
intents = Intents.default()
intents.message_content = True
client = Client(intents=intents)

seen_message_ids = set()


@client.event
async def on_ready():
    print('✅ Bot started and connected to Discord.')
    print(f'Logged in as: {client.user} (ID: {client.user.id})')
    print(f'Connected to {len(client.guilds)} server(s).')
    client.loop.create_task(scan_channel_periodically())


async def scan_channel_periodically():
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            channel = client.get_channel(DISCORD_CHANNEL_ID)
            if not channel:
                print(f"❌ Channel with ID {DISCORD_CHANNEL_ID} not found.")
                return

            messages = [msg async for msg in channel.history(limit=50)]

            for message in reversed(messages):
                if message.id in seen_message_ids:
                    continue

                content = message.content
                match = re.search(
                    r"User:\s*(\w+).*?"                      # User
                    r"Date:\s*(\d{4}-\d{2}-\d{2}).*?"        # Date
                    r"Task ID:\s*[\d\-_:]+__([A-Z0-9]+).*?"  # Task ID (e.g. LY50 from 2025-05-20_22:23__LY50)
                    r"Memo:\s*(.*?)\s*Currency:",            # Memo (non-greedy until Currency:)
                    content,
                    re.DOTALL
                )

                amount_match = re.search(r"Amount:\s*(-?\d+(?:\.\d+)?)", content)

                if match and amount_match:
                    user = match.group(1)
                    date = match.group(2)
                    task_id = match.group(3)

                    full_memo = match.group(4).strip().replace('\n', ' ')

                    # Split memo into type and text
                    if '___' in full_memo:
                        memo_type, memo_text = [part.strip() for part in full_memo.split('___', 1)]
                    else:
                        memo_type, memo_text = full_memo, ""
                    
                    # Normalize memo type
                    memo_type = memo_type.upper()

                    # Detect bridge costs in memo_text
                    bridge_costs_match = re.search(r"total costs[:\s]*([0-9]*\.?[0-9]+)", memo_text, re.IGNORECASE)

                    if bridge_costs_match:
                        bridge_costs = bridge_costs_match.group(1)
                    else:
                        bridge_costs = "Not a bridging task, no bridging costs"
                    
                    amount = float(amount_match.group(1))

                    # Determine sign
                    negative_types = {
                        "REQUEST_POST_FIAT",
                        "ACCEPTANCE REASON",
                        "COMPLETION JUSTIFICATION",
                        "VERIFICATION RESPONSE"
                    }
                    if memo_type in negative_types:
                        amount *= -1

                    amount_str = f"{amount:+.1f}"  # Force sign

                    # Save to Google Sheet
                    sheet.append_row([user, date, task_id, memo_type, memo_text, amount_str, bridge_costs, str(datetime.utcnow())])
                    print(f"✅ Task {task_id} by {user} recorded: {memo_type}, {amount_str} PFT.")
                    seen_message_ids.add(message.id)


        except Exception as e:
            print(f"❗ Error during task check: {e}")

        await asyncio.sleep(600)  # 10 minutes


try:
    print("🔄 Running client...")
    client.run(DISCORD_BOT_TOKEN)
except Exception as e:
    print(f"❗ Exception while starting bot: {e}")
