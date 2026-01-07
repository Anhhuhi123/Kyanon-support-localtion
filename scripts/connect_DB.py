import os
import sys
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

# Env keys (fallbacks)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "postgres")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))

def get_db_connection():
    """
    Trả về psycopg2 connection sử dụng biến môi trường từ .env.
    """
    conn_kwargs = {
        "host": DB_HOST,
        "port": DB_PORT,
        "dbname": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "connect_timeout": CONNECT_TIMEOUT,
    }
    return psycopg2.connect(cursor_factory=RealDictCursor, **conn_kwargs)

def test_connection(sql_query: str = "SELECT now() AS now"):
    """
    Thực thi 1 câu SQL test và in kết quả.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(sql_query)
            rows = cur.fetchall()
            print(f"✓ Query executed: {sql_query}")
            for row in rows:
                print(row)
    except Exception as e:
        print(f"DB error: {e}")
    finally:
        if conn:
            conn.close()

def list_tables():
    """Liệt kê các bảng hiện có (bỏ schema hệ thống)."""
    sql_query = """
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_type='BASE TABLE'
      AND table_schema NOT IN ('pg_catalog','information_schema')
    ORDER BY table_schema, table_name;
    """
    test_connection(sql_query)

def list_tables_in_schema(schema: str):
    sql_query = """
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_type='BASE TABLE'
      AND table_schema = %s
    ORDER BY table_name;
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(sql_query, (schema,))
            rows = cur.fetchall()
            print(f"Tables in schema '{schema}':")
            for r in rows:
                print(r)
    except Exception as e:
        print(f"DB error: {e}")
    finally:
        if conn:
            conn.close()

# ----------------- NEW: table info function -----------------
def show_table_info(table_name: str, schema: str = "public", do_count: bool = False):
    """
    In thông tin bảng:
      - columns + types
      - primary key
      - indexes
      - approx size on disk
      - optional exact row count (can be slow)
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Columns + types
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position;
                """,
                (schema, table_name),
            )
            cols = cur.fetchall()
            if not cols:
                print(f"Table '{schema}.{table_name}' not found or has no columns.")
                return
            print(f"\nColumns for {schema}.{table_name}:")
            for c in cols:
                print(f"  - {c['column_name']}: {c['data_type']} nullable={c['is_nullable']} max_len={c['character_maximum_length']}")

            # Primary key
            cur.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = %s
                  AND tc.table_name = %s
                  AND tc.constraint_type = 'PRIMARY KEY'
                ORDER BY kcu.ordinal_position;
                """,
                (schema, table_name),
            )
            pk = [r["column_name"] for r in cur.fetchall()]
            print(f"\nPrimary key: {pk or 'NONE'}")

            # Indexes (pg_indexes)
            cur.execute(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = %s AND tablename = %s
                ORDER BY indexname;
                """,
                (schema, table_name),
            )
            idxs = cur.fetchall()
            print(f"\nIndexes ({len(idxs)}):")
            for i in idxs:
                print(f"  - {i['indexname']}: {i['indexdef']}")

            # Size on disk (human)
            cur.execute(
                """
                SELECT
                  pg_size_pretty(pg_total_relation_size(quote_ident(%s) || '.' || quote_ident(%s))) AS total_size,
                  pg_size_pretty(pg_relation_size(quote_ident(%s) || '.' || quote_ident(%s))) AS table_size
                """,
                (schema, table_name, schema, table_name),
            )
            size_info = cur.fetchone()
            print(f"\nSize: total={size_info['total_size']} table={size_info['table_size']}")

            # Approx row estimate from pg_class
            cur.execute(
                """
                SELECT reltuples::BIGINT AS estimate_rows
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relname = %s;
                """,
                (schema, table_name),
            )
            est = cur.fetchone()
            print(f"Estimated rows (pg_class.reltuples): {est['estimate_rows'] if est else 'N/A'}")

            # Optional exact count (use sql module to safely format identifiers)
            if do_count:
                print("\nComputing exact COUNT(*) (may be slow)...")
                q = sql.SQL("SELECT count(*) AS exact_count FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(table_name)
                )
                cur.execute(q)
                cnt = cur.fetchone()
                print(f"Exact rows: {cnt['exact_count']}")
    except Exception as e:
        print(f"DB error: {e}")
    finally:
        if conn:
            conn.close()
# ----------------- END NEW -----------------

def fetch_one_row(table_name: str, schema: str = "public", where_clause: str = None):
    """
    Lấy 1 hàng từ bảng để inspect.
    - table_name: tên bảng
    - schema: schema, default public
    - where_clause: optional raw SQL condition (e.g. "id = 123" or "name ILIKE '%coffee%'")
    NOTE: where_clause is used raw into query; don't pass untrusted input.
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            if where_clause:
                q = sql.SQL("SELECT * FROM {}.{} WHERE {} LIMIT 1").format(
                    sql.Identifier(schema), sql.Identifier(table_name), sql.SQL(where_clause)
                )
                cur.execute(q)
            else:
                q = sql.SQL("SELECT * FROM {}.{} LIMIT 1").format(
                    sql.Identifier(schema), sql.Identifier(table_name)
                )
                cur.execute(q)
            row = cur.fetchone()
            if not row:
                print(f"No rows found for {schema}.{table_name} with condition: {where_clause}")
                return
            print(f"Sample row from {schema}.{table_name}:")
            # row is RealDictRow; print key/value lines
            for k, v in row.items():
                print(f"  {k}: {v}")
    except Exception as e:
        print(f"DB error: {e}")
    finally:
        if conn:
            conn.close()
# ----------------- END NEW -----------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="DB helper (reads DB config from .env)")
    parser.add_argument("--list", action="store_true", help="List all tables (excluding system schemas)")
    parser.add_argument("--schema", type=str, help="List tables in specific schema")
    parser.add_argument("--info", type=str, help="Show detailed info for a table (name only)")
    parser.add_argument("--info-schema", type=str, default="public", help="Schema for --info (default: public)")
    parser.add_argument("--count", action="store_true", help="When used with --info, compute exact COUNT(*)")
    parser.add_argument("--sample", type=str, help="Show one sample row from table (table name)")
    parser.add_argument("--sample-schema", type=str, default="public", help="Schema for --sample (default: public)")
    parser.add_argument("--where", type=str, help="Optional WHERE clause for --sample (raw SQL condition)")
    parser.add_argument("sql", nargs="?", help="SQL to run (optional). If omitted, runs SELECT now()")
    args = parser.parse_args()

    if args.list:
        list_tables()
    elif args.schema:
        list_tables_in_schema(args.schema)
    elif args.info:
        show_table_info(args.info, schema=args.info_schema, do_count=args.count)
    elif args.sample:
        fetch_one_row(args.sample, schema=args.sample_schema, where_clause=args.where)
    else:
        sql_arg = args.sql if args.sql else "SELECT now() AS now"
        test_connection(sql_arg)