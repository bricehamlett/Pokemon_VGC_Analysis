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
import pokemon_table
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


def get_event_details (id: int) -> dict:
    res = requests.get(URL + str(id) + "/")
    res.raise_for_status()
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
    
    
    #List of teams which each team is a disctionary
    teams = []
    
    #Get information on team as a whole, Standing, name, and country of player
    all_players = soup.find_all(lambda x: x.has_attr("data-rank"))
    
    for player in all_players:
            
        name = player["data-name"]
        rank = int(player["data-rank"])
        country = player["data-country"]
    
        
        #Find reference to team sheet
        team_href = player.find("a", href=lambda x: x and x.startswith("/teams/"))["href"]
       
        
        #Create another instance this time for the team sheet
        team_res = requests.get("https://limitlessvgc.com" + team_href)
        team_res.raise_for_status()
        html = team_res.text
        
        team_sheet = BeautifulSoup(html, "html.parser")
        
        #List containing each pokemon as a disctionary inside
        pokemon_list = []
        
        #Get a list with all the pokemon (1-6)
        all_pokemon = team_sheet.find_all(class_="pkmn")
        
        
        #get Individualized information for each pokemon, name, item, tera, ability and moves
        for pokemon in all_pokemon:
            pk_name = normalize_limitless_name_to_pokeapi(pokemon.find(class_="name").find("a").text.strip())
            pk_name = edge_case_names(pk_name)
            item_element = normalize_string(pokemon.find("div", class_="details").find(class_="item").text.strip())
            
            # In rare case where pokemon does not hold item
            details_element = pokemon.find("div", class_="details")

            if details_element is not None:
                item_element = details_element.find(class_="item")
            else:
                item_element = None

            if item_element is not None:
                item_text = item_element.get_text(" ", strip=True)

                item_text = re.sub(
                    r"^held\s*item\s*:\s*",
                    "",
                    item_text,
                    flags=re.IGNORECASE
                ).strip()

                if item_text:
                    pk_item = normalize_string(item_text)
                else:
                    pk_item = None
            else:
                pk_item = None
                
                
            
            pk_ability = normalize_string(pokemon.find(class_="ability").text.split("Ability: ")[1])
            
            pk_ability = edge_case_abilities(pk_name, pk_ability)
            
            tera_element = pokemon.find(class_="tera")

            if tera_element:
                pk_tera_type = tera_element.text.split("Tera Type: ")[1].lower()
                pk_tera_type = pokemon_table.get_type_id(pk_tera_type)
            else:
                pk_tera_type = None
           
            
            
            pk_all_moves = pokemon.find(class_="moves").find_all("li")
            pk_moves = [normalize_string(pk_all_moves[0].text), normalize_string(pk_all_moves[1].text), normalize_string(pk_all_moves[2].text), normalize_string(pk_all_moves[3].text)]
            
            #Add pokemon to the list
            complete_pokemon_desc = {"pokemon_name" : pk_name, "item" : pk_item, "ability" : pk_ability, "tera" : pk_tera_type,  "moves" : pk_moves}
            pokemon_list.append(complete_pokemon_desc)
        
        #Add that team 
        teams.append({"player_name" : name, "placement" : rank, "country" : country, "pokemon" : pokemon_list})
        
        time.sleep(0.2)
        
        
    event_details.update({"teams" : teams})
    
    return event_details
    

def get_event_ids(pages: int) -> list:
    URL = "https://limitlessvgc.com/tournaments?show=100&page=" 
    ids = []
    
    for page in range(1, pages + 1):

        res = requests.get(URL + str(page))
        res.raise_for_status()
        html = res.text
        soup = BeautifulSoup(html, "html.parser")
        
        links = soup.find_all("a", href=lambda x: x and x.startswith("/tournaments/"))
        
        hrefs = [a["href"] for a in links]
        
        for href in hrefs:
            ids.append(href.split('/')[2])
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
def commit_teams (event_details: dict, cur, conn):
   
   #Query to check if player is already in db 
    player_check = """
        SELECT player_id FROM Players WHERE player_name = %s
    """
    
    #Query to check is team already exists
    team_check = """
        SELECT team_id FROM Teams WHERE player_id = %s AND event_id = %s
    """
    
    #Query to check if event already exists
    event_check = """
        SELECT event_id from Events WHERE event_name = %s
    """
    
    player_insert = """
        INSERT INTO Players (player_name)
        VALUES(%s)
        ON CONFLICT (player_id) DO NOTHING
        RETURNING player_id
    """
    
    team_insert = """
        INSERT INTO Teams (event_id, player_id, placement)
        VALUES(%s, %s, %s)
    """
    
    event_query = """
        INSERT INTO Events (event_id, event_name, regulation, event_date, event_size)
        VALUES(%s, %s, %s, %s, %s)
        ON CONFLICT (event_id) DO NOTHING    
    """
    
    #See if event exists if so return(unless needs an update)
    cur.execute(event_check, (event_details.get("event_name"),))
    if cur.fetchone():
        print("Already in DB")
        return
    
    #Create Event if one does not exist alreadt
    cur.execute(event_query,
                (event_details.get("event_id"), event_details.get("event_name"), event_details.get("regulation"), parse_event_date(event_details.get("event_date")), event_details.get("event_size")))
    
    
    for team in event_details.get("teams"):
        
        
        #Check for player, if not then create new entry
        player_name = team.get("player_name")

        cur.execute(player_insert, (player_name,))
        row = cur.fetchone()

        if row is not None:
            player_id = row[0]
        else:
            cur.execute(player_check, (player_name,))
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Player '{player_name}' not found after insert attempt.")
            player_id = row[0]
         
        

            
        #Check for Team, if team exists go to next next iteration
        cur.execute(team_check, (player_id, event_details.get("event_id"),))
        if cur.fetchone():
            print("Team already found!")
        else:            
            cur.execute(team_insert, (event_details.get("event_id"), player_id, team.get("placement")))
        cur.execute(team_check, (player_id, event_details.get("event_id"),))
        team_id = cur.fetchone()[0]
            
        #Now that player and team has been created go into each pokemon 
        #print("Successful before team_pokemon")
        commit_team_pokemon(team.get("pokemon"), team_id, cur)
    conn.commit()
        
        
def commit_team_pokemon(pokemon_list: list, team_id: int, cur):
    team_pokemon_insert = """
    INSERT INTO Team_Pokemon (
        team_id,
        slot,
        pk_id,
        poke_dex,
        item_id,
        tera_type,
        ability_id
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (team_id, slot) DO NOTHING
    RETURNING team_pokemon_id
    """

    cur_slot = 1
    for pokemon in pokemon_list:
        
        #Start List that will be used with query, insert constants team_id and slot #
        insert_list = [team_id, cur_slot]
        cur_slot += 1
        
        #Get poke_dex and pk_id by first getting name and querying
        pokemon_name = pokemon.get("pokemon_name")
        cur.execute("SELECT pk_id, poke_dex FROM pokemon WHERE pokemon_name = %s", (pokemon_name,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"name not found in DB: '{pokemon_name}'")
        pk_id, poke_dex = row
        
        #Add to insert list
        insert_list.extend([pk_id, poke_dex])
        
        
        #Get item_id
        pokemon_item = pokemon.get("item")
        
        # Cover for when pokemon does not hold an item (item is None)
        if pokemon_item is None:
            item_id = None
        else:
            cur.execute(
                "SELECT item_id FROM items WHERE item_name = %s",
                (pokemon_item,)
            )
            row = cur.fetchone()

            if row is None:
                raise ValueError(f"Item not found in DB: '{pokemon_item}'")
    
        if row is None:
            raise ValueError(f"Item not found in DB: '{pokemon_item}'")
        item_id = row[0]
        insert_list.append(item_id)
        
        #insert tera-type which is already in correct format
        insert_list.append(pokemon.get("tera"))
        
        #Get ability ID
        pokemon_ability = pokemon.get("ability")
        pokemon_ability = edge_case_abilities(pokemon_name, pokemon_ability)
        cur.execute("SELECT ability_id FROM abilities WHERE ability_name = %s", (pokemon_ability,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"ability not found in DB: '{pokemon_ability}'")
        ability_id = row[0]
        insert_list.append(ability_id)
        
        cur.execute(team_pokemon_insert, insert_list)
        team_pokemon_id = cur.fetchone()[0]
        
        #Then after team_pokemon_id is made make moves
        commit_to_team_pokemon_moves(team_pokemon_id, pokemon.get("moves"), cur)       
        
    
def commit_to_team_pokemon_moves(team_pokemon_id: int, move_list: list, cur):
    team_pokemon_move_insert = """
    INSERT INTO Team_Pokemon_Moves (
        team_pokemon_id,
        move_id,
        move_slot
    )
    VALUES (%s, %s, %s)
    """
    
    slot = 1
    for move in move_list:
        
        if move == '-':
            break
        
        cur.execute("SELECT move_id FROM Moves WHERE move_name = %s", (move,))
        row = cur.fetchone()

        if row is None:
            raise ValueError(f"Move not found in database: '{move}'")
        move_id = row[0]
    
        
        cur.execute(team_pokemon_move_insert, (team_pokemon_id, move_id, slot,))
        slot += 1
        
        
#Make name from limitless match the pokeapi and db name: exluding regional variant and other edge cases        
def normalize_limitless_name_to_pokeapi(name: str) -> str:
    if not name:
        raise ValueError("Pokemon name is empty or None")

    name = name.strip().lower()

    # Remove punctuation PokeAPI doesn't use
    name = name.replace(".", "")
    name = name.replace("'", "")

    # Convert spaces to hyphens
    name = name.replace(" ", "-")

    return name       
            
            
        
    
    
#normalize the names of moves and abilites to match pokeAPI standard because it is more functional    
def normalize_string(name: str) -> str:
    return (
        name.strip()
            .lower()
            .replace("’", "")
            .replace("'", "")
            .replace("(", "")
            .replace(")", "")
            .replace(" ", "-")
    )

#Handle forms that are not taken into consideration in this analysis
def edge_case_names(scraped_name: str) -> str:
    # Normalize separators/case
    name = scraped_name.strip()
    
    # Common “form suffix” patterns from VGC sites
    # Add to this dict as you encounter new ones (keeps it contained)
    overrides = {
        "rapid-strike-urshifu": "urshifu-rapid-strike",
        "single-strike-urshifu": "urshifu-single-strike",
        "shadow-rider-calyrex" : "calyrex-shadow",
        "ice-rider-calyrex" : "calyrex-ice",
        "mimikyu": "mimikyu-disguised",
        "dudunsparce": "dudunsparce-two-segment",
        "bloodmoon-ursaluna": "ursaluna-bloodmoon",
        "female-indeedee": "indeedee-female",
        "male-indeedee": "indeedee-male",
        "eternal-flower-floette": "floette-eternal",
        "basculegion": "basculegion-male",
        "hearthflame-mask-ogerpon" : "ogerpon-hearthflame-mask",
        "cornerstone-mask-ogerpon" : "ogerpon-cornerstone-mask",
        "wellspring-mask-ogerpon" : "ogerpon-wellspring-mask",
        "maushold" : "maushold-family-of-three",
        "wash-rotom" : "rotom-wash",
        "heat-rotom" : "rotom-heat",
        "frost-rotom" : "rotom-frost",
        "fan-rotom" : "rotom-fan",
        "mow-rotom" : "rotom-mow",
        "landorus" : "landorus-therian",
        "tornadus" : "tornadus-incarnate",
        "thundurus" : "thundurus-incarnate",
        "enamorus" : "enamorus-incarnate",
        "aegislash" : "aegislash-shield",
        "palafin" : "palafin-hero",
        "tatsugiri" : "tatsugiri-curly",
        "tatsugiri-droopy-form" : "tatsugiri-droopy",
        "tatsugiri-stretchy-form" : "tatsugiri-stretchy",
        "tatsugiri-soggy-form" : "tatsugiri-soggy",
        "indeedee" : "indeedee-female",
        
        "hisuian-growlithe": "growlithe-hisui",
        "hisuian-arcanine": "arcanine-hisui",
        "hisuian-voltorb": "voltorb-hisui",
        "hisuian-electrode": "electrode-hisui",
        "hisuian-typhlosion": "typhlosion-hisui",
        "hisuian-qwilfish": "qwilfish-hisui",
        "hisuian-sneasel": "sneasel-hisui",
        "hisuian-samurott": "samurott-hisui",
        "hisuian-lilligant": "lilligant-hisui",
        "hisuian-zorua": "zorua-hisui",
        "hisuian-zoroark": "zoroark-hisui",
        "hisuian-braviary": "braviary-hisui",
        "hisuian-sliggoo": "sliggoo-hisui",
        "hisuian-goodra": "goodra-hisui",
        "hisuian-avalugg": "avalugg-hisui",
        "hisuian-decidueye": "decidueye-hisui",
        
        
        "alolan-rattata": "rattata-alola",
        "alolan-raticate": "raticate-alola",
        "alolan-raichu": "raichu-alola",
        "alolan-sandshrew": "sandshrew-alola",
        "alolan-sandslash": "sandslash-alola",
        "alolan-vulpix": "vulpix-alola",
        "alolan-ninetales": "ninetales-alola",
        "alolan-diglett": "diglett-alola",
        "alolan-dugtrio": "dugtrio-alola",
        "alolan-meowth": "meowth-alola",
        "alolan-persian": "persian-alola",
        "alolan-geodude": "geodude-alola",
        "alolan-graveler": "graveler-alola",
        "alolan-golem": "golem-alola",
        "alolan-grimer": "grimer-alola",
        "alolan-muk": "muk-alola",
        "alolan-exeggutor": "exeggutor-alola",
        "alolan-marowak": "marowak-alola",
        "dawn-wings-necrozma" : "necrozma-dawn",
        "dusk-mane-necrozma" : "necrozma-dusk",
        "ultra-necrozma" : "necrozma-ultra",
        
        
        "galarian-meowth": "meowth-galar",
        "galarian-ponyta": "ponyta-galar",
        "galarian-rapidash": "rapidash-galar",
        "galarian-slowpoke": "slowpoke-galar",
        "galarian-slowbro": "slowbro-galar",
        "galarian-farfetchd": "farfetchd-galar",
        "galarian-weezing": "weezing-galar",
        "galarian-mr-mime": "mr-mime-galar",
        "galarian-articuno": "articuno-galar",
        "galarian-zapdos": "zapdos-galar",
        "galarian-moltres": "moltres-galar",
        "galarian-slowking": "slowking-galar",
        "galarian-corsola": "corsola-galar",
        "galarian-zigzagoon": "zigzagoon-galar",
        "galarian-linoone": "linoone-galar",
        "galarian-darumaka": "darumaka-galar",
        "galarian-darmanitan": "darmanitan-galar-standard",
        "galarian-yamask": "yamask-galar",
        "galarian-stunfisk": "stunfisk-galar",
        "toxtricity" : "toxtricity-amped",
        
        "paldean-wooper": "wooper-paldea",
        "paldean-tauros-combat-breed": "tauros-paldea-combat-breed",
        "paldean-tauros-blaze-breed": "tauros-paldea-blaze-breed",
        "paldean-tauros-aqua-breed": "tauros-paldea-aqua-breed",
        "female-oinkologne" : "oinkologne-female",
        "male-oinkologne" : "oinkologne-male",
        
        
        
        # add more as needed
    }

    if name in overrides:
        return overrides[name]
    
    return name
   

    
    



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
    

def edge_case_abilities(pokemon_name: str, ability_name: str) -> str:
    if ability_name == "as-one":
        if pokemon_name == "calyrex-shadow" or pokemon_name == "shadow-rider-calyrex":
            return "as-one-spectrier"

        if pokemon_name == "calyrex-ice" or pokemon_name == "ice-rider-calyrex":
            return "as-one-glastrier"
        
        if pokemon_name == "ursaluna-bloodmoon" and ability_name == "mind":
            return "minds-eye"

    return ability_name

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
    conn = pokemon_table.get_connection()
    cur = conn.cursor()

    all_ids = get_event_ids(2)
    all_ids.pop(0)
    
    #Query to check if event already exists
    event_check = """
        SELECT event_id from Events WHERE event_id = %s
    """

    failed_events = [] 
    for event_id in all_ids:
        try:
            file_name = f"event_{event_id}.json"

            print("Trying event_id:", str(event_id))
            # 1️⃣ If file exists → load from disk
            if os.path.exists(file_name):
                print(f"Loading {event_id} from local file...")
                event_details = load_scraped_data(event_id)

            # 2️⃣ If file does NOT exist → scrape (do NOT save)
            else:
                cur.execute(event_check, (int(event_id),))
                if cur.fetchone():
                    print("Already in DB")
                    continue
                print(f"Scraping {event_id} from website...")
                event_details = get_event_details(event_id)

            # 3️⃣ Insert into DB
            commit_teams(event_details, cur, conn)
            conn.commit()

        except Exception as e:
            conn.rollback()
            failed_events.append(event_id)

            print(f"\nFailed event {event_id}: {e}")
            traceback.print_exc()

    print("Failed events: ", failed_events)
    cur.close()
    conn.close()
    

    """
    Failed Events:
    414, 408, 407, 404, 403, 400, 
    """


if __name__ == "__main__":
    main()


