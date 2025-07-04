# /// script
# dependencies = [
#   "requests",
#   "dotenv",
#   "psycopg2",
#   "datetime",
#   "numpy"
# ]
# ///



import os, time, datetime as dt
from datetime import timezone
import requests
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from iaq_formula import iaq_score        # your IAQ function

# ── parameters ────────────────────────────────────────────
INTERVAL_SEC = int(os.getenv("POLL_SEC", 22))
DEVICE_ID    = os.getenv("DEVICE_ID")
API_HOST     = os.getenv("API_HOST")
TABLE        = os.getenv("TABLE_NAME", "iaq_measurements")

load_dotenv()
DB = dict(
    host = os.getenv("PG_HOST", "localhost"),
    port = int(os.getenv("PG_PORT", 5432)),
    dbname = os.getenv("POSTGRES_DB"),
    user = os.getenv("POSTGRES_USER", "postgres"),
    password = os.getenv("POSTGRES_PASSWORD", "password"),
)

# ── API data fetching ───────────────────────────────────
def tb_login() -> str:
    """Login to the API and get authentication token"""
    body = {"username": os.getenv("VIZHUB_LOGIN"),
            "password": os.getenv("VIZHUB_PW")}
    r = requests.post(f"{API_HOST}/api/auth/login", json=body, timeout=10)
    r.raise_for_status()
    return r.json()["token"]

def fetch_reading(token: str) -> dict:
    """Fetch the latest sensor reading from the API"""
    url = f"{API_HOST}/api/plugins/telemetry/DEVICE/{DEVICE_ID}/values/timeseries"
    params  = {"keys": "CO2,Temperature,Humidity,TVOC", "limit": 1}
    headers = {"X-Authorization": f"Bearer {token}"}
    
    r = requests.get(url, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    j = r.json()
    ts_ms = next(iter(j.values()))[0]["ts"]

    co2  = float(j["CO2"][0]["value"])
    temp = float(j["Temperature"][0]["value"])
    rh   = float(j["Humidity"][0]["value"])
    tvoc = float(j["TVOC"][0]["value"])
    iaq  = iaq_score(temp, rh, co2, tvoc)[0]

    return {
        "time"  : dt.datetime.fromtimestamp(ts_ms / 1000, timezone.utc),
        "device": DEVICE_ID,
        "co2"   : round(co2, 1),
        "temp"  : round(temp, 1),
        "rh"    : round(rh, 1),
        "tvoc"  : round(tvoc, 1),
        "iaq"   : iaq,
    }

# ── insert helper ─────────────────────────────────────────
SQL = f"""
INSERT INTO {TABLE}
       (time, device_id,
        co2_ppm,   temp_c, rh_pct, tvoc_ppb,
        iaq_score)
VALUES %s
ON CONFLICT DO NOTHING
"""

def insert(conn, rows):
    vals = [
        (r["time"], r["device"],
         r["co2"], r["temp"], r["rh"], r["tvoc"],
         r["iaq"])
        for r in rows
    ]
    with conn.cursor() as cur:
        execute_values(cur, SQL, vals)
    conn.commit()

# ── main loop ─────────────────────────────────────────────
def main():
    conn = None
    token = None
    token_time = 0
    
    print("▶ API data feed → DB every", INTERVAL_SEC, "s (Ctrl-C to stop)")
    
    try:
        while True:
            try:
                # Establish or reconnect to database if needed
                if conn is None or conn.closed:
                    conn = psycopg2.connect(**DB)
                    print("Connected to database")
                
                # Get or refresh token if needed
                if token is None or time.time() - token_time > 3600:
                    token = tb_login()
                    token_time = time.time()
                    print("Authenticated with API")
                
                # Fetch data and insert into database
                row = fetch_reading(token)
                insert(conn, [row])
                
                print(f"[{row['time']:%Y-%m-%d %H:%M:%S}] "
                      f"IAQ={row['iaq']:3d} | CO₂={row['co2']:6.1f} ppm | "
                      f"T={row['temp']:4.1f} °C | RH={row['rh']:5.1f} % | "
                      f"TVOC={row['tvoc']:5.1f} ppb")
                
            except psycopg2.Error as e:
                print(f"⚠️ Database error: {e}")
                if conn and not conn.closed:
                    conn.close()
                conn = None
                time.sleep(10)
                continue
            except requests.RequestException as e:
                print(f"⚠️ API error: {e}")
                time.sleep(10)
                continue
            except Exception as e:
                print(f"⚠️ Unexpected error: {e}")
                time.sleep(10)
                continue
                
            time.sleep(INTERVAL_SEC)

    except KeyboardInterrupt:
        print("\n⏹  stopped")
    finally:
        if conn and not conn.closed:
            conn.close()

if __name__ == "__main__":
    main()