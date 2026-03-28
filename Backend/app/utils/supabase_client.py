from supabase import create_client
import os

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Supabase credentials missing")

supabase = create_client(url, key)
bucket = os.getenv("SUPABASE_BUCKET", "bills")