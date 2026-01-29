"""
Fill the 'pokemon' table with every pokemon from https://pokeapi.co/
Start with id = 1 and go until end of Pokedex
For each pokemon get Pokedex number, name, and base stats
Also get type and insert into pokemon_types table
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
    "normal": 18
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


def main ():
    URL = "https://pokeapi.co/api/v2/pokemon/"
    conn = get_connection()
    cur = conn.cursor()
    
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
            
       
        
        
        

    
    




if __name__ == "__main__":
    main()
