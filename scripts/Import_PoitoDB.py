# ...existing code...
import os
import sys
import argparse
import tempfile
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql

load_dotenv()

# Source DB config read from .env (DB_*)
SRC_DB = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", ""),
    "password": os.getenv("DB_PASSWORD", ""),
    "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
}

def connect(conf):
    return psycopg2.connect(cursor_factory=RealDictCursor, **conf)

def dump_table_to_file(src_conf, schema, table, out_path):
    q = sql.SQL("COPY (SELECT * FROM {}.{}) TO STDOUT WITH CSV HEADER").format(
        sql.Identifier(schema), sql.Identifier(table)
    )
    with connect(src_conf) as conn, conn.cursor() as cur, open(out_path, "w", encoding="utf-8") as f:
        cur.copy_expert(q.as_string(conn), f)

# ...existing code...
def create_table_on_target(src_conf, tgt_conf, schema, table, drop_if_exists=False):
    """
    Create table on target using source column definitions from pg_catalog (format_type)
    This handles user-defined types correctly by converting them to standard types.
    """
    cols_query = """
    SELECT
      a.attnum,
      a.attname AS column_name,
      format_type(a.atttypid, a.atttypmod) AS column_type,
      t.typname AS base_type,
      (NOT a.attnotnull) AS is_nullable,
      pg_get_expr(ad.adbin, ad.adrelid) AS column_default
    FROM pg_attribute a
    JOIN pg_class c ON a.attrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    JOIN pg_type t ON a.atttypid = t.oid
    LEFT JOIN pg_attrdef ad ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
    WHERE n.nspname = %s
      AND c.relname = %s
      AND a.attnum > 0
      AND NOT a.attisdropped
    ORDER BY a.attnum;
    """

    pk_query = """
    SELECT
      a.attname
    FROM
      pg_index i
      JOIN pg_class c ON c.oid = i.indrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
    WHERE n.nspname = %s
      AND c.relname = %s
      AND i.indisprimary = true
    ORDER BY a.attnum;
    """

    with connect(src_conf) as sconn, sconn.cursor() as scur:
        scur.execute(cols_query, (schema, table))
        cols = scur.fetchall()
        if not cols:
            raise RuntimeError(f"Source table not found: {schema}.{table}")

        scur.execute(pk_query, (schema, table))
        pk_result = scur.fetchall()
        pk_cols = [r[0] if isinstance(r, (list, tuple)) else r.get('attname') for r in pk_result]

    # Build CREATE TABLE SQL
    col_lines = []
    has_uuid_default = False
    has_postgis = False
    
    for c in cols:
        name = c[1] if isinstance(c, (list, tuple)) else c.get('column_name')
        col_type = c[2] if isinstance(c, (list, tuple)) else c.get('column_type')
        base_type = c[3] if isinstance(c, (list, tuple)) else c.get('base_type')
        is_nullable = c[4] if isinstance(c, (list, tuple)) else c.get('is_nullable')
        default = c[5] if isinstance(c, (list, tuple)) else c.get('column_default')
        
        # Detect PostGIS types - keep original type instead of converting to text
        if base_type in ('geometry', 'geography', 'point'):
            has_postgis = True
            # Keep the original PostGIS type instead of converting
            # col_type already has correct format from format_type()
        
        # Build column definition
        col_def = f'"{name}" {col_type}'
        
        # Handle defaults carefully
        if default:
            default_str = str(default).lower()
            if 'nextval' in default_str:
                # Skip sequence defaults
                pass
            elif 'uuid_generate' in default_str:
                # Mark that we need uuid-ossp extension
                has_uuid_default = True
                col_def += f" DEFAULT {default}"
            elif base_type not in ('geometry', 'geography', 'point'):
                # Add other defaults (skip PostGIS defaults)
                col_def += f" DEFAULT {default}"
        
        if not is_nullable:
            col_def += " NOT NULL"
        col_lines.append(col_def)

    # Build CREATE TABLE statement
    create_statements = []
    
    # Enable required extensions
    if has_postgis:
        create_statements.append('CREATE EXTENSION IF NOT EXISTS postgis')
    if has_uuid_default:
        create_statements.append('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    if drop_if_exists:
        create_statements.append(f'DROP TABLE IF EXISTS "{schema}"."{table}" CASCADE')
    
    create_statements.append(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    
    pk_clause = ""
    if pk_cols:
        pk_cols_quoted = ', '.join([f'"{c}"' for c in pk_cols])
        pk_clause = f", CONSTRAINT \"{table}_pkey\" PRIMARY KEY ({pk_cols_quoted})"
    
    create_table_sql = f'CREATE TABLE "{schema}"."{table}" (\n  ' + ',\n  '.join(col_lines) + pk_clause + '\n)'
    create_statements.append(create_table_sql)

    # Execute on target
    print("Executing CREATE TABLE statements...")
    with psycopg2.connect(**tgt_conf) as tconn:
        tconn.autocommit = False
        with tconn.cursor() as tcur:
            for stmt in create_statements:
                print(f"  {stmt[:80]}...")
                tcur.execute(stmt)
        tconn.commit()
        print("✓ Table created successfully")
# ...existing code...

def import_file_to_target(tgt_conf, schema, table, in_path):
    q = sql.SQL("COPY {}.{} FROM STDIN WITH CSV HEADER").format(sql.Identifier(schema), sql.Identifier(table))
    with connect(tgt_conf) as conn, conn.cursor() as cur, open(in_path, "r", encoding="utf-8") as f:
        cur.copy_expert(q.as_string(conn), f)
        conn.commit()

def fix_sequences(tgt_conf, schema, table):
    # find serial-like defaults and set sequence value to max(col)
    seq_q = """
    SELECT column_name,
           regexp_replace(column_default, '^nextval\\(''?(.*?)''?::regclass\\)','$1') AS seqname
    FROM information_schema.columns
    WHERE table_schema=%s AND table_name=%s AND column_default LIKE 'nextval(%';
    """
    with connect(tgt_conf) as conn, conn.cursor() as cur:
        cur.execute(seq_q, (schema, table))
        rows = cur.fetchall()
        if not rows:
            print("  No sequences to fix")
            return
        for r in rows:
            col = r["column_name"] if isinstance(r, dict) else r[0]
            seq = r["seqname"] if isinstance(r, dict) else r[1]
            print(f"  Fixing sequence for column '{col}': {seq}")
            cur.execute(sql.SQL("SELECT COALESCE(MAX({col}),0) FROM {schema}.{table}").format(
                col=sql.Identifier(col),
                schema=sql.Identifier(schema),
                table=sql.Identifier(table)
            ))
            result = cur.fetchone()
            m = (result["coalesce"] if isinstance(result, dict) else result[0]) or 0
            cur.execute(sql.SQL("SELECT setval(%s, %s, true)"), (seq, int(m)))
        conn.commit()
        print(f"✓ Fixed {len(rows)} sequence(s)")

def main():
    p = argparse.ArgumentParser(description="Copy a table from source DB (.env) to target DB (args). Uses CSV streaming.")
    p.add_argument("--schema", default="public")
    p.add_argument("--table", required=True)
    p.add_argument("--target-host", help="Target DB host (or TARGET_HOST env)")
    p.add_argument("--target-port", type=int, help="Target DB port (or TARGET_PORT env)")
    p.add_argument("--target-db", help="Target DB name (or TARGET_DB env)")
    p.add_argument("--target-user", help="Target DB user (or TARGET_USER env)")
    p.add_argument("--target-password", help="Target DB password (or TARGET_PASSWORD env)")
    p.add_argument("--create-table", action="store_true", help="Create table on target using source schema")
    p.add_argument("--drop-if-exists", action="store_true", help="Drop target table first if --create-table")
    p.add_argument("--no-seq-fix", action="store_true", help="Don't try to fix sequences after import")
    args = p.parse_args()

    tgt_conf = {
        "host": args.target_host or os.getenv("TARGET_HOST"),
        "port": args.target_port or int(os.getenv("TARGET_PORT", "5432")),
        "dbname": args.target_db or os.getenv("TARGET_DB"),
        "user": args.target_user or os.getenv("TARGET_USER"),
        "password": args.target_password or os.getenv("TARGET_PASSWORD"),
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
    }
    for k in ("host","dbname","user","password"):
        if not tgt_conf.get(k):
            print(f"Target DB missing {k}. Provide via args or TARGET_{k.upper()} env.")
            sys.exit(2)

    schema = args.schema
    table = args.table

    tmp = tempfile.NamedTemporaryFile(prefix=f"{schema}_{table}_", suffix=".csv", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        print("Dumping source table to CSV:", tmp_path)
        dump_table_to_file(SRC_DB, schema, table, tmp_path)
        if args.create_table:
            print("Creating table on target...")
            create_table_on_target(SRC_DB, tgt_conf, schema, table, drop_if_exists=args.drop_if_exists)
        print("Importing CSV into target...")
        import_file_to_target(tgt_conf, schema, table, tmp_path)
        if not args.no_seq_fix:
            print("Fixing sequences on target (if any)...")
            fix_sequences(tgt_conf, schema, table)
        print("Done.")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

if __name__ == "__main__":
    main()
# ...existing code...