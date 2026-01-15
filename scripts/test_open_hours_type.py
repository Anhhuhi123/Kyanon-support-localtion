import asyncio
import asyncpg
from config.config import Config

async def test():
    conn_str = Config.get_db_connection_string()
    print(f'Connection string: {conn_str}')
    pool = await asyncpg.create_pool(conn_str, min_size=1, max_size=2)
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, name, open_hours
            FROM public."PoiClean"
            WHERE open_hours IS NOT NULL
            LIMIT 1
        """)
        
        if row:
            print(f'\nID: {row["id"]}')
            print(f'Name: {row["name"]}')
            print(f'open_hours type: {type(row["open_hours"])}')
            print(f'open_hours value: {row["open_hours"]}')
            
            if isinstance(row['open_hours'], str):
                print('\n=> open_hours is STRING, needs JSON parsing')
                import json
                parsed = json.loads(row['open_hours'])
                print(f'   Parsed type: {type(parsed)}')
                print(f'   First item: {parsed[0] if parsed else "empty"}')
            elif isinstance(row['open_hours'], list):
                print('\n=> open_hours is LIST, already parsed by asyncpg')
                print(f'   First item: {row["open_hours"][0] if row["open_hours"] else "empty"}')
            else:
                print(f'\n=> open_hours is {type(row["open_hours"]).__name__}')
        else:
            print('No rows found')
    
    await pool.close()

if __name__ == '__main__':
    asyncio.run(test())
