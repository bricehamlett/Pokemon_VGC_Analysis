"""
Fill the 'pokemon' table with every pokemon from https://pokeapi.co/
Start with id = 1 and go until end of Pokedex
For each pokemon get Pokedex number, name, and base stats
Also get type and insert into pokemon_types table
Also use same api to fill 'moves' table for refernces
"""

import requests
import psycopg2
import json
import time

"""
Takes in raw Json from https://pokeapi.co/api/v2/pokemon/
Returns a disctionary of the form:
{'hp': 100, 'atk': 100 ... 'spd':100}
"""
def get_stats(pokemon_json: json) -> dict:
    stats = pokemon_json.get("stats")
    all_stats = {}
    for i in range(0, 6):
        stat_name = abbreviate_stat(stats[i].get("stat").get("name"))
        stat_number = stats[i].get("base_stat")
        all_stats.update({stat_name : stat_number})
    return all_stats
        
        
    
     
"""
Takes is the full stat name and returns the abbrivated as to fit into the database
Helper function for 'get_stats'
"""
def abbreviate_stat(stat_name: str) -> str:
    stat_name = stat_name.lower()

    match stat_name:
        case "hp":
            return "hp"
        case "attack":
            return "atk"
        case "defense":
            return "def"
        case "special-attack":
            return "spa"
        case "special-defense":
            return "spd"
        case "speed":
            return "spe"
        case _:
            raise ValueError(f"Unknown stat name: {stat_name}")
        
"""
Takes in full name of type and matches it to the type_lookup table inside of database
Returns corresponding type id so pokemon types can be put into pokemon_types table
"""
def get_type_id(p_type:  str) -> int:
    
    TYPE_LOOKUP = {
    "fire": 1,
    "water": 2,
    "grass": 3,
    "electric": 4,
    "ice": 5,
    "fighting": 6,
    "poison": 7,
    "ground": 8,
    "flying": 9,
    "psychic": 10,
    "bug": 11,
    "rock": 12,
    "ghost": 13,
    "dragon": 14,
    "dark": 15,
    "steel": 16,
    "fairy": 17,
    "normal": 18,
    "stellar": 19
}
    try:
        return TYPE_LOOKUP[p_type.lower()]
    except KeyError:
        raise ValueError(f"Unknown type: {p_type}")



"""
Get connection to local data base to store information
"""
def get_connection():
    return psycopg2.connect(
    host="127.0.0.1",
    port=5433,
    dbname="VGC",
    user="postgres",
    password="1232",
    connect_timeout=5
)
          
       
"""
Takes in connection to SQL DB and the URL for pokeapi
goes through pokedex from the API from 1-1025 pokemon
Gets their stats and type and commits them into table 'pokemon'
"""      
def commit_to_pokemon(cur, conn, URL):
    pokemon_query = """
            INSERT INTO pokemon 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (poke_dex) DO NOTHING;  
            """
    type_query = """
            INSERT INTO pokemon_types
            VALUES (%s, %s, %s)
            ON CONFLICT (poke_dex, type_id) DO NOTHING;
            """
    
    
    
    try:
        
        for pokemon_id in range(1, 1026):
            res = requests.get(URL + str(pokemon_id) + "/", timeout=10)
            res.raise_for_status()
            data = res.json()
            
  
            
            #Parameters for pokemon stable
            stats = get_stats(data)
            name = data.get("name")
            dex = data.get("id")
            print(name)
            #first type that will be inserted into pokemon_types table
            type1 = get_type_id(data.get("types")[0].get("type").get("name"))
            
            
            cur.execute(pokemon_query, (dex, name, stats.get("hp"), stats.get("atk"), stats.get("def"), stats.get("spa"), stats.get("spd"), stats.get("spe")))
            cur.execute(type_query, (dex, type1, 1))
            
            #Find if pokemon has second type, if so then add to pokemon_types table
            try:
                type2 = get_type_id(data.get("types")[1].get("type").get("name"))
                
                cur.execute(type_query, (dex, type2, 2))
            except IndexError:
                type2 = None
                
                
            #if pokemon_id % 50 == 0 or pokemon_id == 1025:
            conn.commit()
            time.sleep(0.2)
            
    #If error occurs rollback changes and exit program
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close() 
      
def commit_to_moves(cur):
    
    #Connect to PokeAPI to get all of the moves
    BASE_URL = "https://pokeapi.co/api/v2/move?limit=10000"
    response = requests.get(BASE_URL)
    response.raise_for_status()

    #Collect all moves into a list
    all_moves = response.json()["results"]

    print(f"Found {len(all_moves)} moves. Beginning insertion...\n")

    #Loop through all moves
    for move in all_moves:
        move_url = move["url"]


        try:
            move_data = requests.get(move_url).json()

            move_id = move_data["id"]
            move_name = move_data["name"]

            move_type = move_data["type"]["name"]
            type_id = get_type_id(move_type)

            accuracy = move_data["accuracy"]        # Can be None
            power = move_data["power"]              # Can be None
            priority = move_data["priority"]

            cur.execute("""
                INSERT INTO Moves (move_id, move_name, type_id, accuracy, power, priority)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (move_id) DO NOTHING;
            """, (move_id, move_name, type_id, accuracy, power, priority))

            #Verify if it inserted properly
            print(f"Inserted move {move_id} - {move_name}")

            time.sleep(0.05)  # Small delay to be polite to API

        except Exception as e:
            #If not print details for edge cases
            print(f"Error inserting move {move['name']}: {e}")

    


    
def commit_to_abilities(cur):
    
    BASE_URL = "https://pokeapi.co/api/v2/ability?limit=100000"
    resp = requests.get(BASE_URL, timeout=30)
    resp.raise_for_status()
    all_abilities = resp.json()["results"]

    print(f"Found {len(all_abilities)} abilities. Beginning insertion...\n")


    # LOOP THROUGH ABILITIES (single inserts)  
    for ability in all_abilities:
        ability_url = ability["url"]

        try:
            data = requests.get(ability_url, timeout=30).json()

            ability_id = data["id"]
            ability_name = data["name"]

            cur.execute("""
                INSERT INTO Abilities (ability_id, ability_name)
                VALUES (%s, %s)
                ON CONFLICT (ability_id) DO NOTHING;
            """, (ability_id, ability_name))

            print(f"Inserted ability {ability_id} - {ability_name}")

            time.sleep(0.05)  # small delay to be polite to the API

        except Exception as e:
            print(f"\n\nError inserting ability {ability['name']}: {e}\n\n")

def commit_to_items(cur):
    
    CATEGORY_URL = "https://pokeapi.co/api/v2/item-category/held-items/"
    resp = requests.get(CATEGORY_URL, timeout=30)
    resp.raise_for_status()
    all_items = resp.json()

    held_items = all_items["items"]
    print(f"Found {len(all_items)} items. Beginning insertion...\n")


    # LOOP THROUGH ITEMS (single inserts)
    for item in held_items:
        try:
            item_data = requests.get(item["url"], timeout=30).json()

            item_id = item_data["id"]
            item_name = item_data["name"]  # canonical format

            cur.execute("""
                INSERT INTO Items (item_id, item_name)
                VALUES (%s, %s)
                ON CONFLICT (item_id) DO NOTHING;
            """, (item_id, item_name))

            print(f"Inserted held item {item_id} - {item_name}")

            time.sleep(0.05)


        except Exception as e:
            print(f"Error inserting item {item.get('name')}: {e}")


    

def main ():
    URL = "https://pokeapi.co/api/v2/pokemon/"
    conn = get_connection()
    cur = conn.cursor()
    
    #commit_to_pokemon(cur, conn, URL)
    #commit_to_moves(cur) 
    #commit_to_abilities(cur)
    commit_to_items(cur)
    
    conn.commit()
    cur.close()
    conn.close()




if __name__ == "__main__":
    main()
