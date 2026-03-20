"""
Test script for Antarctic Wallet token refresh mechanism.

Demonstrates the full cycle:
1. Load tokens from file
2. Fetch rates using access token
3. Refresh tokens (get new access + refresh pair)
4. Save new tokens to file
5. Verify new tokens work

Run: python scripts/test_antarctic_refresh.py

Token file format (antarctic_tokens.json):
{
    "access_token": "eyJ...",
    "refresh_token": "abc123..."
}
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi.requests import AsyncSession

API_BASE = "https://app.antarcticwallet.com/api/v2"
TOKENS_FILE = Path(__file__).parent.parent / "config" / "antarctic_tokens.json"


def load_tokens() -> dict:
    if not TOKENS_FILE.exists():
        print(f"[!] Token file not found: {TOKENS_FILE}")
        print(f"    Create it with: {{\"access_token\": \"...\", \"refresh_token\": \"...\"}}")
        raise SystemExit(1)
    with open(TOKENS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_tokens(access_token: str, refresh_token: str):
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump({"access_token": access_token, "refresh_token": refresh_token}, f, indent=2)
    print(f"[+] Tokens saved to {TOKENS_FILE}")


async def fetch_rates(session: AsyncSession, access_token: str) -> dict | None:
    r = await session.get(
        f"{API_BASE}/coins/rates",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=15,
    )
    if r.status_code == 401:
        print(f"[!] Rates request: 401 (token expired or invalid)")
        return None
    r.raise_for_status()
    return r.json()


async def refresh_tokens(session: AsyncSession, access_token: str, refresh_token: str) -> dict | None:
    r = await session.post(
        f"{API_BASE}/auth/refresh_tokens",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={"refresh_token": refresh_token},
        timeout=15,
    )
    if r.status_code != 200:
        print(f"[!] Refresh failed: {r.status_code} {r.text[:200]}")
        return None
    data = r.json()
    if data.get("status") != "ok":
        print(f"[!] Refresh status: {data.get('status')}")
        return None
    return data["data"]


async def main():
    tokens = load_tokens()
    access_token = tokens["access_token"]
    refresh_tok = tokens["refresh_token"]

    print("=" * 60)
    print(f"  Antarctic Wallet Token Refresh Test")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    print(f"\n  Access token:  ...{access_token[-20:]}")
    print(f"  Refresh token: {refresh_tok}")

    async with AsyncSession(impersonate="chrome110") as session:
        # Step 1: Try current tokens
        print(f"\n--- Step 1: Fetch rates with current access token ---")
        rates = await fetch_rates(session, access_token)
        if rates and rates.get("status") == "ok":
            for item in rates["data"]["items"]:
                if item["coin"] == "USDT":
                    print(f"  USDT sell: {float(item['sellRate']):.2f} RUB  (token works!)")
        else:
            print(f"  Could not fetch rates (token may be expired)")

        # Step 2: Refresh tokens
        print(f"\n--- Step 2: Refresh tokens ---")
        new_tokens = await refresh_tokens(session, access_token, refresh_tok)
        if not new_tokens:
            print(f"  [!] Refresh failed. Manual re-login required.")
            return

        new_access = new_tokens["accessToken"]
        new_refresh = new_tokens["refreshToken"]
        exp = new_tokens["expiredAt"]
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)

        print(f"  New access token:  ...{new_access[-20:]}")
        print(f"  New refresh token: {new_refresh}")
        print(f"  Expires at:        {exp_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        # Step 3: Save new tokens
        save_tokens(new_access, new_refresh)

        # Step 4: Verify new tokens work
        print(f"\n--- Step 3: Verify new access token ---")
        rates2 = await fetch_rates(session, new_access)
        if rates2 and rates2.get("status") == "ok":
            for item in rates2["data"]["items"]:
                if item["coin"] == "USDT":
                    print(f"  USDT sell: {float(item['sellRate']):.2f} RUB  (new token works!)")
        else:
            print(f"  [!] New token verification failed!")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
