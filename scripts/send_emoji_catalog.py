import asyncio
from app.core.config import Settings
from app.api.admin.emojis import SYSTEM_EMOJIS
from aiogram import Bot
from aiogram.enums import ParseMode

async def main():
    cfg = Settings()
    bot = Bot(token=cfg.bot_token)
    admin_id = 6775546602

    categories = {}
    for item in SYSTEM_EMOJIS:
        cat = item.get('category', 'Other')
        categories.setdefault(cat, []).append(item)

    # Message 1: Payment & Services (Newly requested)
    msg1_lines = [
        '<b>🎨 Emoji Library · Verified Emojis (Part 1/2)</b>',
        '<i>এখানে নতুন পেমেন্ট মেথড এবং সার্ভিসগুলোর কাস্টম ইমোজি রয়েছে:</i>\n',
    ]

    if 'Payment' in categories:
        msg1_lines.append('<b>💳 Payment Methods:</b>')
        for item in categories['Payment']:
            eid = item['emoji_id']
            name = item['name']
            msg1_lines.append(f'<tg-emoji emoji-id="{eid}">💳</tg-emoji> <b>{name}</b> — <code>{eid}</code>')
        msg1_lines.append('')

    if 'Services' in categories:
        msg1_lines.append('<b>🌟 Services & Subscriptions:</b>')
        for item in categories['Services']:
            eid = item['emoji_id']
            name = item['name']
            msg1_lines.append(f'<tg-emoji emoji-id="{eid}">✨</tg-emoji> <b>{name}</b> — <code>{eid}</code>')

    await bot.send_message(chat_id=admin_id, text='\n'.join(msg1_lines), parse_mode=ParseMode.HTML)
    print('Part 1 sent successfully!')

    # Message 2: VPN Services & Bot UI
    msg2_lines = [
        '<b>🎨 Emoji Library · System & VPN Presets (Part 2/2)</b>',
        '<i>এখানে ভিপিএন এবং সিস্টেম ইউজার ইন্টারফেসের প্রিসেটগুলো রয়েছে:</i>\n',
    ]

    if 'VPN' in categories:
        msg2_lines.append('<b>🛡 VPN Services:</b>')
        for item in categories['VPN']:
            eid = item['emoji_id']
            name = item['name']
            msg2_lines.append(f'<tg-emoji emoji-id="{eid}">🛡</tg-emoji> <b>{name}</b> — <code>{eid}</code>')
        msg2_lines.append('')

    if 'System' in categories:
        msg2_lines.append('<b>⚙️ System UI Icons:</b>')
        for item in categories['System']:
            eid = item['emoji_id']
            name = item['name']
            msg2_lines.append(f'<tg-emoji emoji-id="{eid}">🔹</tg-emoji> <b>{name}</b> — <code>{eid}</code>')

    await bot.send_message(chat_id=admin_id, text='\n'.join(msg2_lines), parse_mode=ParseMode.HTML)
    print('Part 2 sent successfully!')

    await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())
