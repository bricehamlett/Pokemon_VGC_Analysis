"""
Scraping Data from limitlessvgc
URL = https://limitlessvgc.com/tournaments
From each tournament Gather:
    - Event Name
    - Event Regulation
    - Event Date 
    - Event Data
        - Each Player Name
        - Each Team placement 
            - Each Pokemon:
                - Ability
                - Item
                - Moves (1-4)
                - Tera-type
"""



import requests
from bs4 import BeautifulSoup
import psycopg2
try:
    from . import pokemon_table, ingestion, official_standings, terminal_output
except ImportError:
    import pokemon_table
    import ingestion
    import official_standings
    import terminal_output
import time
import json
from datetime import datetime
import re
import os
import traceback




"""
Takes in tounrament ID data 
ex) https://limitlessvgc.com/tournaments/(Tournament_ID)
returns a disctionary including event details and then a list of dictionary for each team
format:
{tournament_id : 415, event_name : "name", regulation: "f" ... 
    teams : [ 
    {player_name : "john smith", placement : 1, pokemon : [{name : "charmander", item : "choice scarf", ... moves : ["scratch", ...]], }
    ]
                                        }
                       
                       }
             }
}

"""
URL = "https://limitlessvgc.com/tournaments/"


def get_event_details(id: int, refresh=False) -> dict:
    res = requests.get(URL + str(id) + "/", timeout=45)
    res.raise_for_status()
    res.encoding = "utf-8"
    html = res.text
    soup = BeautifulSoup(html, "html.parser")
    
    event_details = {}
    
    event_details.update({"event_id" : id})
    
    event_name = soup.find(class_="infobox-heading").get_text(strip=True)  
    
      
    #Strips text to form: "24th January 2026 • 688 Players"
    unsplit_text = soup.find(class_="infobox-line").get_text(" ", strip=True)
    
    
    event_date, player_count = unsplit_text.split("•", 1)
    event_date = event_date.strip()
    
    #Get ride of  the space and 'Players' and convert into int for Postgres
    player_count = player_count.strip().split(" ")[0]
    player_count = int(player_count)
    
    
    #Get regulation
    regulation_text = soup.find(class_="infobox-line").find("a").get_text(strip=True)
    regulation = normalize_regulation(regulation_text)
    
        
    event_details.update({
    "event_id": id,
    "event_name": event_name,
    "event_date": event_date,
    "event_size": player_count,
    "regulation": regulation
    })
    
    
    standings_link = soup.find('a', href=lambda href: href and
                               href.startswith('https://standings.limitlessvgc.com/') and
                               href.rstrip('/').endswith('/standings'))
    if standings_link:
        return official_standings.collect(
            event_details, soup, standings_link['href'].rstrip('/'),
            official_standings.PageClient(refresh=refresh))
    event_details['metadata'] = {
        'official_adapter_version': official_standings.VERSION,
        'coverage_scope': 'results_page',
    }

    #List of teams which each team is a disctionary
    teams = []
    
    #Get information on team as a whole, Standing, name, and country of player
    all_players = soup.find_all(lambda x: x.has_attr("data-rank"))
    
    for player in all_players:
            
        name = player["data-name"]
        rank = int(player["data-rank"])
        country = player["data-country"]
    
        
        #Find reference to team sheet
        #Some have no team sheets, skip beacuse they are not usefel
        team_link = player.find(
            "a",
            href=lambda x: x and x.startswith("/teams/")
        )

        if team_link is None:
            teams.append({"player_name": name, "placement": rank, "country": country, "pokemon": []})
            continue

        team_href = team_link["href"]       
        
        #Create another instance this time for the team sheet
        team_res = requests.get("https://limitlessvgc.com" + team_href, timeout=45)
        team_res.raise_for_status()
        team_res.encoding = "utf-8"
        html = team_res.text
        
        team_sheet = BeautifulSoup(html, "html.parser")
        
        #List containing each pokemon as a disctionary inside
        pokemon_list = []
        
        #Get a list with all the pokemon (1-6)
        all_pokemon = team_sheet.find_all(class_="pkmn")
        
        
        for pokemon in all_pokemon:
            link = pokemon.select_one('.name a')
            def field(selector, prefix):
                element = pokemon.select_one(selector)
                return re.sub(prefix, '', element.get_text(' ', strip=True), flags=re.I).strip() if element else None
            source_fields = {
                'id': link.get('href', '').rstrip('/').split('/')[-1] if link else None,
                'name': link.get_text(' ', strip=True) if link else None,
                'item': field('.item', r'^Held\s*Item:\s*'),
                'ability': field('.ability', r'^Ability:\s*'),
                'tera': field('.tera', r'^Tera\s*Type:\s*'),
                'moves': [m.get_text(strip=True) for m in pokemon.select('.moves li')],
            }
            pokemon_list.append(ingestion.normalization.pokemon(source_fields))

        #Add that team 
        teams.append({"player_name" : name, "placement" : rank, "country" : country, "pokemon" : pokemon_list})
        
        time.sleep(0.2)
        
        
    event_details.update({"teams" : teams})
    
    return event_details
    

def get_event_ids(pages: int) -> list:
    URL = "https://limitlessvgc.com/tournaments?show=100&page=" 
    ids = []
    
    for page in range(1, pages + 1):

        res = requests.get(URL + str(page), timeout=45)
        res.raise_for_status()
        html = res.text
        soup = BeautifulSoup(html, "html.parser")
        
        links = soup.find_all("a", href=lambda x: x and x.startswith("/tournaments/"))
        
        hrefs = [a["href"] for a in links]
        
        for href in hrefs:
            candidate = href.split('/')[2]
            if candidate.isdigit():
                ids.append(candidate)
    return ids
    
    
    
"""
Takes in dictionary generated from get_event_details
Then commits each pokemon to the postgres DB
First creating the Event with event ID given from limitless
Then creates a player ID in players table
Then creates a team using player ID and Event ID in teams table
And then look into the first team and gathers information before looking at the specific pokemon,
for Each pokemon check its ID from pokemon table, see if item/ability already exist in their respecitive tables if not insert,
then use 
"""
def commit_teams(event_details: dict, cur, conn):
    """Compatibility entry point; both sources now use the same loader."""
    ingestion.migrate(conn)
    return ingestion.load_event(conn, ingestion.normalize_scraped(event_details))


#Make name from limitless match the pokeapi and db name: exluding regional variant and other edge cases        
def normalize_limitless_name_to_pokeapi(name):
    return ingestion.normalization.slug(name)


def normalize_string(name):
    return ingestion.normalization.slug(name)


def edge_case_names(name):
    return ingestion.normalization.canonical_species(name)


def parse_event_date(date_str: str):
    """
    Convert strings like:
        '24th January 2026'
    into:
        datetime.date(2026, 1, 24)

    Returns a datetime.date object suitable for psycopg2 DATE insertion.
    """

    if not date_str:
        raise ValueError("Event date string is empty or None.")

    # Remove ordinal suffixes: st, nd, rd, th
    cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str.strip())

    try:
        parsed = datetime.strptime(cleaned, "%d %B %Y")
    except ValueError as e:
        raise ValueError(f"Could not parse date string: '{date_str}'") from e

    return parsed.date()
    
def save_scraped_data(event_id):
    event_details = get_event_details(event_id)

    with open(f"event_{event_id}.json", "w", encoding="utf-8") as f:
        json.dump(event_details, f, indent=2)

def load_scraped_data(id) -> dict:
    with open(f"event_{id}.json", "r", encoding="utf-8") as f:
        return json.load(f)
    

def edge_case_abilities(pokemon_name, ability_name):
    return ingestion.normalization.ability(ability_name, pokemon_name)

def normalize_regulation(regulation_text: str) -> str:
    regulation_text = regulation_text.strip()

    # Scarlet/Violet
    match = re.search(r"Regulation(?: Set)?\s+([A-Z](?:-[A-Z])?)", regulation_text)
    if match:
        return match.group(1)

    # Sword/Shield
    match = re.search(r"Series\s+(\d+)", regulation_text)
    if match:
        return f"S{match.group(1)}"

    # Unknown future format
    return regulation_text


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scrape official Limitless VGC results")
    parser.add_argument('--pages', type=int, default=2)
    parser.add_argument('--event-id', action='append', help='Import specific official events (repeatable)')
    parser.add_argument('--refresh', action='store_true', help='Refetch existing events and detect changed sheets')
    parser.add_argument('--verbose-errors', action='store_true',
                        help='Print full tracebacks in addition to compact error messages')
    args = parser.parse_args()
    if args.pages < 1:
        parser.error('--pages must be positive')
    conn = pokemon_table.get_connection()
    cur = conn.cursor()

    ingestion.migrate(conn)
    all_ids = list(dict.fromkeys(args.event_id or get_event_ids(args.pages)))
    if not args.event_id:
        cur.execute("""SELECT DISTINCT e.external_id FROM events e JOIN pending_identity_reviews r USING(event_id)
            WHERE e.source='limitless_vgc' AND r.resolved_at IS NULL""")
        all_ids = list(dict.fromkeys(all_ids + [row[0] for row in cur.fetchall()]))
    
    #Query to check if event already exists
    event_check = """
        SELECT event_id FROM events WHERE source = 'limitless_vgc' AND external_id = %s
        AND source_metadata->>'official_adapter_version' = '1'
        AND event_date < CURRENT_DATE - 14
        AND NOT EXISTS (SELECT 1 FROM pending_identity_reviews r
                        WHERE r.event_id=events.event_id AND r.resolved_at IS NULL)
    """

    failed_events = [] 
    for event_id in all_ids:
        try:
            print(f"\n[OFFICIAL] Event {event_id}", flush=True)
            cur.execute(event_check, (str(event_id),))
            if cur.fetchone() and not args.refresh and not args.event_id:
                print("[SKIP] Already imported with current full-standings adapter.")
                continue
            # Older files predate full standings. Do not let them bypass upgrades.
            event_details = get_event_details(event_id, refresh=args.refresh)

            # 3️⃣ Insert into DB
            print(terminal_output.event_summary(commit_teams(event_details, cur, conn)))
            conn.commit()

        except Exception as e:
            conn.rollback()
            failed_events.append(event_id)

            print(terminal_output.error_summary({'event_id': event_id, 'error': str(e)}))
            if args.verbose_errors:
                traceback.print_exc()

    if failed_events:
        print("\n[SUMMARY] Failed official events: " + ", ".join(map(str, failed_events)))
    else:
        print("\n[SUMMARY] Official-event ingestion completed without failures.")
    cur.close()
    conn.close()
    return 1 if failed_events else 0
    

    """
    Failed Events:
    414, 408, 407, 404, 403, 400, 
    """


if __name__ == "__main__":
    raise SystemExit(main())
