# sitechecker.py | Python 3.8+ | Telethon bot
# pip install telethon aiohttp aiofiles

import asyncio, aiohttp, json, os, re, time
from telethon import TelegramClient, events

# ---------- CONFIG ----------
API_ID       = 0           # your telegram api id
API_HASH     = ''          # your telegram api hash
BOT_TOKEN    = ''          # your bot token
ADMIN_IDS    = []          # [123456789]

SITES_FILE   = 'sites_1_5.txt'
API_CFG_FILE = 'api_cfg.json'
OUT_FILE     = 'chksites_result.txt'
TEST_CC      = '4111111111111111|01|2026|123'

DEFAULT_API  = 'https://bhikari-production-bf277.up.railway.app/shopify'

DEAD_KEYWORDS = [
    'no valid products', 'no session token', 'amount_too_large',
    'validation_custom', 'no valid payment', 'pick up is unavailable',
    'no products', 'invalid site', 'site error', 'could not find',
    'connection error', 'timeout'
]

# ---------- HELPERS ----------
def load_api() -> str:
    if os.path.exists(API_CFG_FILE):
        try:
            return json.load(open(API_CFG_FILE))['endpoint']
        except Exception:
            pass
    return DEFAULT_API

def save_api(endpoint: str):
    json.dump({'endpoint': endpoint}, open(API_CFG_FILE, 'w'))

def load_sites() -> list[str]:
    if not os.path.exists(SITES_FILE):
        return []
    return [s.strip() for s in open(SITES_FILE).read().splitlines() if s.strip()]

def save_sites(sites: list[str]):
    open(SITES_FILE, 'w').write('\n'.join(sites))

def is_dead_response(response: str) -> bool:
    r = response.lower()
    return any(kw in r for kw in DEAD_KEYWORDS)

async def check_site(session: aiohttp.ClientSession, site: str, api: str) -> dict:
    url = f"{api}?site={site}&cc={TEST_CC}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            data = await r.json(content_type=None)
            price    = float(data.get('Price', 0))
            currency = data.get('Currency', 'USD')
            response = data.get('Response', '')
            dead     = is_dead_response(response) or price == 0.0 or price > 5
            return {
                'site': site, 'price': price, 'currency': currency,
                'response': response, 'dead': dead
            }
    except Exception as e:
        return {
            'site': site, 'price': 0.0, 'currency': '???',
            'response': str(e), 'dead': True
        }

# ---------- BOT ----------
bot = TelegramClient('sitechecker', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

def admin_only(func):
    async def wrapper(event):
        if event.sender_id not in ADMIN_IDS:
            await event.reply('⛔ Admins only.')
            return
        await func(event)
    return wrapper

# /addapi <endpoint>
@bot.on(events.NewMessage(pattern=r'^/addapi (.+)'))
@admin_only
async def addapi_cmd(event):
    endpoint = event.pattern_match.group(1).strip()
    save_api(endpoint)
    await event.reply(f'✅ API saved:\n`{endpoint}`', parse_mode='md')

# /testapi
@bot.on(events.NewMessage(pattern=r'^/testapi$'))
@admin_only
async def testapi_cmd(event):
    api = load_api()
    msg = await event.reply(f'🔄 Testing API...\n`{api}`', parse_mode='md')
    async with aiohttp.ClientSession() as session:
        url = f"{api}?site=https://www.chocosphere.com&cc={TEST_CC}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                data = await r.json(content_type=None)
                text = f'✅ API Working\n\n<code>{json.dumps(data, indent=2)}</code>'
        except Exception as e:
            text = f'❌ API Error: <code>{e}</code>'
    await msg.edit(text, parse_mode='html')

# /chksites
@bot.on(events.NewMessage(pattern=r'^/chksites$'))
@admin_only
async def chksites_cmd(event):
    sites = load_sites()
    if not sites:
        await event.reply('❌ sites_1_5.txt empty.')
        return
    api = load_api()
    msg = await event.reply(f'🔄 Checking {len(sites)} sites...')
    keep, removed = [], []
    lines = []
    async with aiohttp.ClientSession() as session:
        for i, site in enumerate(sites, 1):
            res = await check_site(session, site, api)
            status = '❌ REMOVED' if res['dead'] else '✅ KEEP'
            line = f"{status} | {site} | ${res['price']} {res['currency']} | {res['response']}"
            lines.append(line)
            if res['dead']:
                removed.append(site)
            else:
                keep.append(site)
            if i % 10 == 0:
                await msg.edit(f'🔄 Checked {i}/{len(sites)}...')
            await asyncio.sleep(0.5)
    # save cleaned sites
    save_sites(keep)
    # save result txt
    result_text = '\n'.join(lines)
    open(OUT_FILE, 'w').write(result_text)
    summary = (
        f'✅ Done\n'
        f'Kept: {len(keep)} | Removed: {len(removed)}\n\n'
        f'Result saved to <code>{OUT_FILE}</code>'
    )
    await msg.edit(summary, parse_mode='html')
    # send result file
    await bot.send_file(event.chat_id, OUT_FILE, caption='📄 Full site check results')

# /clean
@bot.on(events.NewMessage(pattern=r'^/clean$'))
@admin_only
async def clean_cmd(event):
    sites = load_sites()
    cleaned = []
    for s in sites:
        # strip everything except the URL
        url = re.sub(r'[^\S\n]*[\|✅❌$A-Z].*', '', s).strip()
        url = re.match(r'https?://\S+', url)
        if url:
            cleaned.append(url.group(0))
    cleaned = list(dict.fromkeys(cleaned))  # deduplicate
    save_sites(cleaned)
    await event.reply(f'✅ Cleaned — {len(cleaned)} URLs remain in sites_1_5.txt')

print('SiteChecker bot running...')
bot.run_until_disconnected()
