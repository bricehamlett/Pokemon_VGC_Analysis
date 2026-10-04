"""
Fill the 'pokemon' table with every pokemon from https://pokeapi.co/
Start with id = 1 and go until end of Pokedex
For each pokemon get Pokedex number, name, and base stats
Also get type and insert into pokemon_types table
Also use same api to fill 'moves' table for refernces
"""

import os
import psycopg2
import json

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
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "5433")),
        dbname=os.getenv("POSTGRES_DB", "VGC"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "1232"),
        connect_timeout=5
    )

          
       
"""
Takes in connection to SQL DB and the URL for pokeapi
goes through pokedex from the API from 1-1025 pokemon
Gets their stats and type and commits them into table 'pokemon'
"""      
def _seed_reference_stage(conn, stage):
    try:
        from .seed_database import seed_stage
    except ImportError:
        from seed_database import seed_stage
    return seed_stage(conn, stage)


def commit_to_pokemon(cur, conn, URL=None):
    """Compatibility wrapper; progress is committed per complete resource."""
    return _seed_reference_stage(conn, 'pokemon')


def commit_to_moves(cur):
    return _seed_reference_stage(cur.connection, 'moves')


def commit_to_abilities(cur):
    return _seed_reference_stage(cur.connection, 'abilities')


def commit_to_items(cur):
    return _seed_reference_stage(cur.connection, 'items')


# Get the generation based on the National Dex number
def get_generation(national_dex: int) -> int:
    if national_dex <= 151:
        return 1
    elif national_dex <= 251:
        return 2
    elif national_dex <= 386:
        return 3
    elif national_dex <= 493:
        return 4
    elif national_dex <= 649:
        return 5
    elif national_dex <= 721:
        return 6
    elif national_dex <= 809:
        return 7
    elif national_dex <= 905:
        return 8
    elif national_dex <= 1025:
        return 9
    else:
        raise ValueError(f"Unknown generation for National Dex #{national_dex}")

    

def main():
    try:
        from .seed_database import main as seed_main
    except ImportError:
        from seed_database import main as seed_main
    return seed_main()


if __name__ == '__main__':
    raise SystemExit(main())
