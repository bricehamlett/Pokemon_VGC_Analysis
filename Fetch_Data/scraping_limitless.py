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


def get_event_details (id) -> dict:
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
    player_1_team = soup.find("tr", attrs={"data-rank" : "1"})
    name = player_1_team["data-name"]
    rank = int(player_1_team["data-rank"])
    country = player_1_team["data-country"]
   
    
    #Find reference to team sheet
    team_href = player_1_team.find("a", href=lambda x: x and x.startswith("/teams/"))["href"]
    print(team_href)
    
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
        pk_name = pokemon.find(class_="name").find("a").text.strip()
        pk_item = pokemon.find("div", class_="details").find(class_="item").text.strip()
        pk_ability = pokemon.find(class_="ability").text.split("Ability: ")[1]
        pk_tera_type = pokemon.find(class_="tera").text.split("Tera Type: ")[1].lower()
        pk_tera_type = pokemon_table.get_type_id(pk_tera_type)
        print(pk_ability, pk_tera_type, pk_item)
        
        pk_all_moves = pokemon.find(class_="moves").find_all("li")
        pk_moves = [pk_all_moves[0].text, pk_all_moves[1].text, pk_all_moves[2].text, pk_all_moves[3].text]
        
        #Add pokemon to the list
        complete_pokemon_desc = {"pokemon_name" : pk_name, "item" : pk_item, "ability" : pk_ability, "tera" : pk_tera_type,  "moves" : pk_moves}
        pokemon_list.append(complete_pokemon_desc)
    
    #Add that team 
    teams.append({"name" : name, "placement" : rank, "country" : country, "pokemon" : pokemon_list})
    event_details.update({"teams" : teams})
    
    return event_details
    
    
    
    
    
    
    
    


def main():
    #conn = pokemon_table.get_connection()
    print(get_event_details(415))
    




if __name__ == "__main__":
    main()


