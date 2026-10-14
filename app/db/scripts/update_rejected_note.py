import asyncio
from app.core.config import get_settings
from app.services import build_services

async def main():
    s = build_services(get_settings())
    async with s.db.connect() as conn:
        new_note_bn = "ভুল ট্রানজ্যাকশন আইডি (টাকা পাওয়া যায়নি)। অনুগ্রহ করে সঠিক TrxID দিয়ে পুনরায় চেষ্টা করুন।"
        new_note_en = "Invalid Transaction ID (Payment not found). Please verify and submit the correct TrxID."
        
        await conn.execute("UPDATE deposits SET admin_note = $1 WHERE id = 19", new_note_bn)
        await conn.execute("UPDATE deposits SET admin_note = $1 WHERE id = 16", new_note_en)
        print("Updated deposits #19 and #16 with beautiful rejection notes.")
        
        rows = await conn.fetch("SELECT id, status, method_name, admin_note FROM deposits WHERE status = 'rejected' ORDER BY id DESC")
        for r in rows:
            print(f"ID {r['id']} ({r['status']}): {r['admin_note']}")
    await s.close()

if __name__ == "__main__":
    asyncio.run(main())
