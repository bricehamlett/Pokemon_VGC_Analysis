"""
Enter a Pokedex ID number to see a trend line for the usage rates through tournaments in scarlet and violet
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import psycopg2
from Fetch_Data.pokemon_table import get_connection


def get_data(pokedex: int) -> pd.DataFrame:
    conn = get_connection()
    query = """
    WITH event_team_totals AS (
    SELECT event_id, COUNT(DISTINCT team_id) as teams_in_event
    FROM teams
    GROUP BY event_id
    )
    SELECT
    ROUND(COUNT(DISTINCT tp.team_id)::numeric / ett.teams_in_event * 100, 4) AS usage_rate,
    tp.poke_dex,
    t.event_id,
    e.event_name,
    e.event_date,
    p.pokemon_name
    FROM team_pokemon tp
    JOIN teams t   ON tp.team_id = t.team_id
    JOIN events e  ON t.event_id = e.event_id
    JOIN pokemon p ON p.poke_dex = tp.poke_dex
    JOIN event_team_totals ett ON ett.event_id = e.event_id
    WHERE p.poke_dex = %s
    GROUP BY t.event_id, tp.poke_dex, e.event_name, p.pokemon_name, p.poke_dex, e.event_size, ett.teams_in_event, e.event_date
    HAVING ett.teams_in_event >= 30
    ORDER BY e.event_date DESC;
    """

    return pd.read_sql_query(query, conn, params=[pokedex])



def main():
    print("Enter Pokedex Number:")
    choice = input()
    df = get_data(choice)
    
    # Convert to datetime
    df["event_date"] = pd.to_datetime(df["event_date"])

    # Sort by date
    df = df.sort_values("event_date")

    # Plot
    plt.figure(figsize=(10, 6))
    plt.plot(df["event_date"], df["usage_rate"], marker='o')

    plt.title(f"{df['pokemon_name'].iloc[0]} Usage Over Time")
    plt.xlabel("Event Date")
    plt.ylabel("Usage %")
    plt.xticks(rotation=45)

    plt.tight_layout()
    plt.show()
    
    



if __name__ == "__main__":
    main()