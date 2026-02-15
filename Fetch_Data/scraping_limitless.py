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
    regulation_text = soup.find(class_="infobox-line").findChild("a").text
    regulation = regulation_text.split("Regulation ")[1]
    
    event_details.update({
    "event_id": id,
    "event_name": event_name,
    "event_date": event_date,
    "event_size": player_count,
    "regulation": regulation
    })
    
    print("Checkpoint \n\n")
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
            pk_name = normalize_string(pokemon.find(class_="name").find("a").text.strip())
            pk_item = normalize_string(pokemon.find("div", class_="details").find(class_="item").text.strip())
            pk_ability = normalize_string(pokemon.find(class_="ability").text.split("Ability: ")[1])
            pk_tera_type = pokemon.find(class_="tera").text.split("Tera Type: ")[1].lower()
            pk_tera_type = pokemon_table.get_type_id(pk_tera_type)
            
            
            pk_all_moves = pokemon.find(class_="moves").find_all("li")
            pk_moves = [normalize_string(pk_all_moves[0].text), normalize_string(pk_all_moves[1].text), normalize_string(pk_all_moves[2].text), normalize_string(pk_all_moves[3].text)]
            
            #Add pokemon to the list
            complete_pokemon_desc = {"pokemon_name" : pk_name, "item" : pk_item, "ability" : pk_ability, "tera" : pk_tera_type,  "moves" : pk_moves}
            pokemon_list.append(complete_pokemon_desc)
        
        #Add that team 
        teams.append({"name" : name, "placement" : rank, "country" : country, "pokemon" : pokemon_list})
        
        time.sleep(0.2)
        
        
    event_details.update({"teams" : teams})
    
    return event_details
    
    
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
        SELECT 1 FROM Players WHERE player_name = %s
    """
    
    #Query to check is team already exists
    team_check = """
        SELECT team_id FROM Teams WHERE player_id = %s AND event_id = %s
    """
    
    player_insert = """
        INSERT INTO Players (player_name)
        VALUES(%s)
        ON CONFLICT DO NOTHING
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
    

    
    #Create Event if one does not exist alreadt
    cur.execute(event_query,
                (event_details.get("event_id"), event_details.get("event_name"), event_details.get("regulation"), event_details.get("event_date"), event_details.get("event_size")))
    
    
    for team in event_details.get("teams"):
        
        
        #Chech for player, if not then create new entry
        player_name = team.get("player_name")
        cur.execute(player_check, (player_name,))
        if not cur.fetchone():
            cur.execute(player_insert, (player_name,))
         
        #Get player_id   
        cur.execute("SELECT player_id FROM Players WHERE player_name = %s", (player_name,))
        player_id = cur.fetchone()[0]

            
        #Check for Team, if team exists go to next next iteration
        cur.execute(team_check, (player_id, event_details.get("event_id"),))
        if cur.fetchone():
            print("Team already found!")
        else:            
            cur.execute(team_insert, (event_details.get("event_id"), player_id, team.get("placement")))
        cur.execute(team_check, (player_id, event_details.get("event_id"),))
        team_id = cur.fetchone()[0]
            
        #Now that player and team has been created go into each pokemon 
        commit_team_pokemon(team.get("pokemon"), team_id, cur)
    conn.commit()
        
        
def commit_team_pokemon(pokemon_list: list, team_id: int, cur):
    team_pokemon_insert = """
    INSERT INTO Team_Pokemon (
        team_id,
        slot,
        poke_dex,
        nature_id,
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
        
        #Get poke_dex by first getting name and querying
        pokemon_name = pokemon.get("pokemon_name")
        pokemon_name = canonical_species_name(pokemon_name)
        cur.execute("SELECT poke_dex FROM pokemon WHERE pokemon_name = %s", (pokemon_name,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"name not found in DB: '{pokemon_name}'")
        poke_dex = row[0]
        
        #Add to insert list
        insert_list.append(poke_dex)
        
        #Natures not added yet potential expansion with greater data
        nature_id = None
        insert_list.append(nature_id)
        
        #Get item_id
        pokemon_item = pokemon.get("item")
        cur.execute("SELECT item_id FROM items WHERE item_name = %s", (pokemon_item,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Item not found in DB: '{pokemon_item}'")
        item_id = row[0]
        insert_list.append(item_id)
        
        #insert tera-type which is already in correct format
        insert_list.append(pokemon.get("tera"))
        
        #Get ability ID
        pokemon_ability = pokemon.get("ability")
        cur.execute("SELECT ability_id FROM abilities WHERE ability_name = %s", (pokemon_ability,))
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"ability not found in DB: '{pokemon_ability}'")
        ability_id = row[0]
        insert_list.append(ability_id)
        
        cur.execute(team_pokemon_insert, (insert_list[0], insert_list[1], insert_list[2], insert_list[3], insert_list[4], insert_list[5], insert_list[6],))
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
        
        cur.execute("SELECT move_id FROM Moves WHERE move_name = %s", (move,))
        row = cur.fetchone()

        if row is None:
            raise ValueError(f"Move not found in database: '{move}'")
        move_id = row[0]
        
        cur.execute(team_pokemon_move_insert, (team_pokemon_id, move_id, slot,))
        slot += 1
        
        
        
        
            
            
        
    
    
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
def canonical_species_name(scraped_name: str) -> str:
    # Normalize separators/case
    name = scraped_name.strip()

    # Common “form suffix” patterns from VGC sites
    # Add to this dict as you encounter new ones (keeps it contained)
    overrides = {
        "Urshifu-Rapid-Strike": "Urshifu",
        "Urshifu-Single-Strike": "Urshifu",
        "Landorus-Therian": "Landorus",
        "Thundurus-Therian": "Thundurus",
        "Tornadus-Therian": "Tornadus",
        "Indeedee-F": "Indeedee",
        "Indeedee-M": "Indeedee",
        # add more as needed
    }

    if name in overrides:
        return overrides[name]

    # Generic fallback: take base before first hyphen if your DB stores base species
    # (only do this if your DB naming convention matches this assumption)
    if "-" in name:
        return name.split("-", 1)[0]

    return name
   
    
def save_scraped_data():
    event_details = get_event_details(415)
    
    with open("event_415.json", "w", encoding="utf-8") as f:
        json.dump(event_details, f, indent=2)   

def load_scraped_data() -> dict:
    with open("event_415.json", "r", encoding="utf-8") as f:
        return json.load(f)
    

def main():
    #conn = pokemon_table.get_connection()
    #cur = conn.cursor()
    
    
    event_details = load_scraped_data()
    print(event_details)
        
    #commit_teams(event_415, cur, conn)
    
    #cur.close()
    #conn.close()
    




if __name__ == "__main__":
    main()


