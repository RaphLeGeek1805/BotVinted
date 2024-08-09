import discord
import requests
from pyVinted import Vinted
from dotenv import load_dotenv
import os
from datetime import datetime
import pytz
import time
import asyncio
import json

# Charger les variables d'environnement
load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
USER_IDS = [int(id) for id in os.getenv("USER_IDS").split(',')]
VINTED_URL = os.getenv("VINTED_URL")
SENT_ITEMS_FILE = "sent_items.json"
is_monitoring = False  # Variable pour contrôler la surveillance

vinted = Vinted()
paris_tz = pytz.timezone('Europe/Paris')

def convert_to_paris_time(utc_time):
    paris_time = utc_time.astimezone(paris_tz)
    return paris_time.strftime("%Y-%m-%d %H:%M:%S")

def fetch_vinted_items():
    print("[DEBUG] Récupération des articles depuis Vinted...")
    items = vinted.items.search(VINTED_URL, 10, 1)
    print(f"[DEBUG] Nombre d'articles récupérés: {len(items)}")
    return items

def load_sent_items():
    if os.path.exists(SENT_ITEMS_FILE):
        with open(SENT_ITEMS_FILE, "r") as file:
            return set(json.load(file))
    return set()

def save_sent_items(sent_items):
    with open(SENT_ITEMS_FILE, "w") as file:
        json.dump(list(sent_items), file)

async def send_to_discord(embed):
    # Convertir l'embed en dictionnaire pour l'envoyer via webhook
    data = {"embeds": [embed.to_dict()]}
    headers = {"Content-Type": "application/json"}
    response = requests.post(DISCORD_WEBHOOK_URL, json=data, headers=headers)
    
    if response.status_code == 204:
        print('[+] Embed envoyé avec succès à Discord.')
    elif response.status_code == 429:
        retry_after = response.json().get('retry_after', 1)
        print(f'[-] Rate limited. Réessayer après {retry_after} secondes...')
        time.sleep(retry_after)
        await send_to_discord(embed)
    else:
        print(f'[-] Échec de l\'envoi du message à Discord: {response.status_code}, {response.text}')

class DiscordClient(discord.Client):
    async def on_ready(self):
        print(f'{self.user} s\'est connecté à Discord!')
        await self.check_vinted_items()

    async def on_message(self, message):
        global is_monitoring
        print(f"Message reçu : {message.content}")
        if message.author == self.user:
            return

        if message.content.lower() == '!ping':
            await message.channel.send("Pong!")

        if message.content.lower() == '!start':
            is_monitoring = True
            await message.channel.send("Surveillance des annonces Vinted activée.")
            await self.check_vinted_items()

        elif message.content.lower() == '!stop':
            is_monitoring = False
            await message.channel.send("Surveillance des annonces Vinted désactivée.")

    async def check_vinted_items(self):
        sent_items = load_sent_items()

        while is_monitoring:
            print("[INFO] Vérification des articles Vinted...")
            items = fetch_vinted_items()

            if items:
                print(f"[INFO] {len(items)} articles récupérés.")
                for item in items:
                    item_id = item.id
                    if item_id not in sent_items:
                        sent_items.add(item_id)
                        item_title = item.title
                        item_url = item.url
                        item_description = getattr(item, 'description', "Description non disponible")
                        item_price = f"{item.price} {item.currency}"

                        item_created_utc = getattr(item, 'created_at_ts', None)
                        if item_created_utc:
                            item_created = convert_to_paris_time(item_created_utc)
                        else:
                            item_created = "Date non disponible"

                        # Création de l'embed
                        embed = discord.Embed(
                            title=item_title,
                            description=item_description,
                            url=item_url,
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="💶 Prix", value=item_price, inline=True)
                        embed.add_field(name="⌛ Publication", value=item_created, inline=True)
                        embed.set_image(url=item.photo)  # Utilisation directe de l'URL de l'image

                        print(f"[INFO] Envoi de l'article à Discord: {item_title}")
                        await send_to_discord(embed)
                        time.sleep(1)  # Attente pour éviter de dépasser les limites de Discord

                save_sent_items(sent_items)
            else:
                print("[WARNING] Aucun article récupéré.")

            await asyncio.sleep(60)  # Vérification des articles toutes les 60 secondes

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True  # Très important pour accéder au contenu des messages

client = DiscordClient(intents=intents)
client.run(DISCORD_TOKEN)
