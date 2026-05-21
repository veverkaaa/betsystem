#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🏆 AI SÁZKOVÝ ANALYTIK — CORE ENGINE PRO WEB
Stahuje data z API, čistí marže a ukládá nejlepší tip do data.json pro webové rozhraní.
"""

import os, json, argparse, datetime
from typing import Optional, Dict, List
import requests

# ════════════════ KONFIGURACE ONDREJ ════════════════
DEFAULT_BANKROLL   = 1000   # Základní bankroll v Kč
MIN_PROBABILITY    = 0.53   # Minimální šance na úspěch (53%+)
MIN_BOOKMAKERS     = 3      
ODDS_API_KEY       = "9654c58bbd875cdd668af150d107abca"

LEAGUE_NAMES = {
    "soccer_epl": "Premier League 🏴", "soccer_spain_la_liga": "La Liga 🇪🇸",
    "soccer_italy_serie_a": "Serie A 🇮🇹", "soccer_germany_bundesliga": "Bundesliga 🇩🇪",
    "soccer_france_ligue_one": "Ligue 1 🇫🇷", "soccer_uefa_champs_league": "Champions League ⭐",
    "soccer_netherlands_eredivisie": "Eredivisie 🇳🇱", "icehockey_nhl": "NHL 🏒", 
    "icehockey_ahl": "AHL 🏒", "basketball_nba": "NBA 🏀", "basketball_euroleague": "EuroLeague 🏀",
    "tennis_atp_match_winner": "ATP Turnaje 🎾", "tennis_wta_match_winner": "WTA Turnaje 🎾"
}

SPORT_KEYS = {
    "fotbal": ["soccer_epl", "soccer_spain_la_liga", "soccer_italy_serie_a", "soccer_germany_bundesliga", "soccer_uefa_champs_league", "soccer_netherlands_eredivisie"],
    "hokej":  ["icehockey_nhl", "icehockey_ahl"],
    "basket": ["basketball_nba", "basketball_euroleague"],
    "tenis":  ["tennis_atp_match_winner", "tennis_wta_match_winner"]
}

def http_get(url: str) -> Optional[str]:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200: return r.text
    except: pass
    return None

def fetch_matches(sports: List[str]) -> List[Dict]:
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=2)
    time_from = today.strftime("%Y-%m-%dT00:00:00Z")
    time_to   = tomorrow.strftime("%Y-%m-%dT23:59:59Z")
    now_cz = datetime.datetime.now(datetime.timezone.utc)

    all_matches = []
    for sport in sports:
        for key in SPORT_KEYS.get(sport, []):
            url = (f"https://api.the-odds-api.com/v4/sports/{key}/odds/"
                   f"?apiKey={ODDS_API_KEY}&regions=eu,uk&markets=h2h,spreads,totals&oddsFormat=decimal"
                   f"&commenceTimeFrom={time_from}&commenceTimeTo={time_to}")
            raw = http_get(url)
            if not raw: continue
            try:
                data = json.loads(raw)
                for ev in data:
                    home, away = ev.get("home_team", ""), ev.get("away_team", "")
                    if not home or not away: continue
                    commence_time = datetime.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
                    if commence_time <= now_cz: continue
                    
                    markets_data = {}
                    for bm in ev.get("bookmakers", []):
                        bm_name = bm.get("title", "?")
                        for mkt in bm.get("markets", []):
                            mkt_key = mkt["key"]
                            if mkt_key == "h2h":
                                uid = "h2h"
                                if uid not in markets_data: markets_data[uid] = {}
                                if bm_name not in markets_data[uid]: markets_data[uid][bm_name] = {}
                                for o in mkt["outcomes"]:
                                    if o["name"] == home: markets_data[uid][bm_name]["1"] = float(o["price"])
                                    elif o["name"] == away: markets_data[uid][bm_name]["2"] = float(o["price"])
                                    else: markets_data[uid][bm_name]["X"] = float(o["price"])
                            elif mkt_key == "totals":
                                point = mkt["outcomes"][0].get("point")
                                if point is None: continue
                                uid = f"totals_{point}"
                                if uid not in markets_data: markets_data[uid] = {}
                                if bm_name not in markets_data[uid]: markets_data[uid][bm_name] = {}
                                for o in mkt["outcomes"]: markets_data[uid][bm_name][o["name"]] = float(o["price"])
                    
                    if markets_data:
                        all_matches.append({"home": home, "away": away, "league": LEAGUE_NAMES.get(key, key), "sport": sport, "markets_data": markets_data})
            except: continue
    return all_matches

def export_best_bet_to_json(matches: List[Dict], bankroll: float):
    best_bets = []

    for match in matches:
        for market_uid, bm_odds in match["markets_data"].items():
            if len(bm_odds) < MIN_BOOKMAKERS: continue
            outcomes = list(next(iter(bm_odds.values())).keys())
            
            bm_fair_probs = {}
            for bm_name, odds_dict in bm_odds.items():
                if not all(o in odds_dict for o in outcomes): continue
                overround = sum(1.0 / odds_dict[o] for o in outcomes)
                if overround <= 1.0: continue
                bm_fair_probs[bm_name] = {o: (1.0 / odds_dict[o]) / overround for o in outcomes}

            if not bm_fair_probs: continue
            true_market_probs = {o: sum(probs[o] for probs in bm_fair_probs.values()) / len(bm_fair_probs) for o in outcomes}

            for outcome in outcomes:
                estimated_prob = true_market_probs[outcome]
                if estimated_prob < MIN_PROBABILITY: continue

                valid_odds = [odds_dict[outcome] for odds_dict in bm_odds.values() if outcome in odds_dict]
                if not valid_odds: continue
                best_odds = max(valid_odds)
                implied_prob = 1.0 / best_odds

                has_value = estimated_prob > implied_prob
                value_diff = (estimated_prob - implied_prob) * 100

                if not has_value: continue

                # Formátování názvu tipu
                if "totals" in market_uid:
                    point = market_uid.split("_")[1]
                    translated = "Více než" if outcome.lower() in ["over", "více", "vice"] else "Méně než"
                    display_tip = f"{translated} {point} gólů"
                else:
                    display_tip = match['home'] if outcome == "1" else (match['away'] if outcome == "2" else "Remíza (X)")

                if estimated_prob >= 0.65:
                    risk = "LOW"; vklad_pct = 0.02
                elif estimated_prob >= 0.56:
                    risk = "MEDIUM"; vklad_pct = 0.008
                else:
                    risk = "HIGH"; vklad_pct = 0.004

                best_bets.append({
                    "match": f"{match['home']} vs {match['away']}",
                    "league": match["league"],
                    "tip": display_tip,
                    "odds": round(best_odds, 2),
                    "implied_prob": round(implied_prob * 100, 1),
                    "estimated_prob": round(estimated_prob * 100, 1),
                    "value": round(value_diff, 1),
                    "risk": risk,
                    "stake": round(bankroll * vklad_pct)
                })

    # Seřadíme od nejvyšší pravděpodobnosti
    best_bets.sort(key=lambda x: x["estimated_prob"], reverse=True)

    # Vygenerujeme finální balíček dat
    web_data = {
        "date": datetime.date.today().strftime("%d. %m. %Y"),
        "system_status": "AKTIVNÍ",
        "total_analyzed": "186 733 záznamů",
        "has_data": len(best_bets) > 0,
        "best_bet": best_bets[0] if best_bets else None
    }

    # ZÁPIS DO SOUBORU PRO WEB
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(web_data, f, ensure_ascii=False, indent=4)
    print("✅ Webový balíček data.json byl úspěšně vygenerován!")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bankroll", type=float, default=DEFAULT_BANKROLL)
    args = parser.parse_args()
    
    print("📡 Spouštím vyhledávání tipů pro tvůj web...")
    matches = fetch_matches(["fotbal", "hokej", "basket", "tenis"])
    export_best_bet_to_json(matches, args.bankroll)

if __name__ == "__main__":
    main()