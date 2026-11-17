# sitechecker.py | Python 3.8+ | pip install telethon aiohttp

import asyncio, aiohttp, json, os, re
from telethon import TelegramClient, events

# ---------- CONFIG ----------
API_ID       = 0
API_HASH     = ''
BOT_TOKEN    = ''
ADMIN_IDS    = []

SITES_FILE   = 'sites_1_5.txt'
API_CFG_FILE = 'api_cfg.json'
OUT_FILE     = 'chksites_result.txt'
TEST_CC      = '4111111111111111|01|2026|123'
DEFAULT_API  = 'https://bhikari-production-bf277.up.railway.app/shopify'

DEAD_KEYWORDS = [
    'no valid products', 'no session token', 'amount_too_large',
    'validation_custom', 'no valid payment', 'pick up is unavailable',
    'no products', 'invalid site', 'site error', 'could not find',
    'connection error', 'timeout', 'required_artifacts'
]

stop_event = asyncio.Event()

# ---------- HELPERS ----------
def load_api():
    if os.path.exists(API_CFG_FILE):
        try:
            return json.load(open(API_CFG_FILE))['endpoint']
        except Exception:
            pass
    return DEFAULT_API

def save_api(endpoint):
    json.dump({'endpoint': endpoint}, open(API_CFG_FILE, 'w'))

def load_sites():
    if not os.path.exists(SITES_FILE):
        return []
    return [s.strip() for s in open(SITES_FILE).read().splitlines() if s.strip() and s.strip().startswith('http')]

def save_sites(sites):
    open(SITES_FILE, 'w').write('\n'.join(sites))

def is_dead(response, price):
    r = response.lower()
    if any(kw in r for kw in DEAD_KEYWORDS):
        return True
    if price == 0.0 or price > 5:
        return True
    return False

async def check_site(session, site, api):
    url = f"{api}?site={site}&cc={TEST_CC}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
            data = await r.json(content_type=None)
            price    = float(data.get('Price', 0))
            currency = data.get('Currency', 'USD')
            response = data.get('Response', '')
            dead     = is_dead(response, price)
            return {'site': site, 'price': price, 'currency': currency,
                    'response': response, 'dead': dead}
    except Exception as e:
        return {'site': site, 'price': 0.0, 'currency': '???',
                'response': str(e), 'dead': True}

# ---------- BOT ----------
bot = TelegramClient('sitechecker', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

def admin_only(func):
    async def wrapper(event):
        if event.sender_id not in ADMIN_IDS:
            await event.reply('⛔ Admins only.')
            return
        await func(event)
    return wrapper

@bot.on(events.NewMessage(pattern=r'^/start$'))
async def start_cmd(event):
    await event.reply(
        '<b>SiteChecker Bot</b>\n\n'
        '/addapi &lt;url&gt; - Set API\n'
        '/testapi - Test API\n'
        '/chksites - Check all sites\n'
        '/stopchk - Stop checking\n'
        '/clean - Clean sites file',
        parse_mode='html'
    )

@bot.on(events.NewMessage(pattern=r'^/addapi (.+)'))
@admin_only
async def addapi_cmd(event):
    endpoint = event.pattern_match.group(1).strip()
    save_api(endpoint)
    await event.reply(f'✅ API saved:\n<code>{endpoint}</code>', parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/testapi$'))
@admin_only
async def testapi_cmd(event):
    api = load_api()
    msg = await event.reply(f'🔄 Testing...')
    async with aiohttp.ClientSession() as session:
        url = f"{api}?site=https://www.chocosphere.com&cc={TEST_CC}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                data = await r.json(content_type=None)
                text = f'✅ API OK\n<code>{json.dumps(data, indent=2)}</code>'
        except Exception as e:
            text = f'❌ Error: <code>{e}</code>'
    await msg.edit(text, parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/stopchk$'))
@admin_only
async def stopchk_cmd(event):
    stop_event.set()
    await event.reply('⛔ Stop signal sent — will stop after current site.')

@bot.on(events.NewMessage(pattern=r'^/chksites$'))
@admin_only
async def chksites_cmd(event):
    stop_event.clear()
    sites = load_sites()
    if not sites:
        await event.reply('❌ No sites found.')
        return
    api = load_api()
    msg = await event.reply(f'🔄 Checking {len(sites)} sites... /stopchk to stop.')
    keep, removed, lines = [], [], []
    async with aiohttp.ClientSession() as session:
        for i, site in enumerate(sites, 1):
            if stop_event.is_set():
                break
            res = await check_site(session, site, api)
            status = '❌ REMOVED' if res['dead'] else '✅ KEEP'
            lines.append(f"{status} | {site} | ${res['price']} {res['currency']} | {res['response']}")
            (removed if res['dead'] else keep).append(site)
            if i % 10 == 0:
                try:
                    await msg.edit(f'🔄 Checked {i}/{len(sites)}... /stopchk to stop.')
                except Exception:
                    pass
            await asyncio.sleep(0.3)
    save_sites(keep)
    open(OUT_FILE, 'w').write('\n'.join(lines))
    stopped = ' (Stopped early)' if stop_event.is_set() else ''
    summary = f'✅ Done{stopped}\nChecked: {len(lines)} | Kept: {len(keep)} | Removed: {len(removed)}'
    await msg.edit(summary)
    await bot.send_file(event.chat_id, OUT_FILE, caption='📄 Results')

@bot.on(events.NewMessage(pattern=r'^/clean$'))
@admin_only
async def clean_cmd(event):
    sites = load_sites()
    cleaned = list(dict.fromkeys(sites))
    save_sites(cleaned)
    await event.reply(f'✅ Cleaned — {len(cleaned)} URLs remain.')

@bot.on(events.NewMessage(func=lambda e: e.file and e.file.name and e.file.name.endswith('.txt')))
async def file_handler(event):
    if event.sender_id not in ADMIN_IDS:
        return
    msg = await event.reply('📥 Downloading file...')
    path = await event.download_media('received_sites.txt')
    sites = [s.strip() for s in open(path).read().splitlines() if s.strip() and s.startswith('http')]
    if not sites:
        await msg.edit('❌ No valid URLs found.')
        return
    global SITES_FILE
    SITES_FILE = path
    save_sites(sites)
    await msg.edit(f'✅ {len(sites)} sites loaded — run /chksites.')

print('SiteChecker bot running...')
bot.run_until_disconnected()
