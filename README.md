# Pokémon VGC Tournament Analytics

A data analytics project designed to collect, normalize, and analyze competitive Pokemon VGC tournament data.
This project builds a fully normalized PostgreSQL database by scraping tournament results from LimitlessVGC and integrating official Pokédex data from PokeAPI. This is for a deeper undestanding of what causes meta-game changes as well as how good placements affect sequential placements.

---

## Overview

Competitive Pokémon VGC data is publicly available but not structured for analysis.

- Designing a normalized relational schema
- Building a web scraping pipeline
- Relating to offical Pokemon Data
- Enforcing relational integrity with foreign keys and constraints
- Enabling regulation-based meta analysis
- Preparing clean data for Power BI dashboards

---

## Tech Stack

**Languages & Tools**
- Python
- PostgreSQL
- Power BI (planned visualization layer)

**Python Libraries**
- `requests`
- `BeautifulSoup`
- `psycopg2`
- `json`
- `datetime`


**Data Sources**
- LimitlessVGC (tournament data)
- PokeAPI (official Pokédex data)

---

## Database Design

The schema follows strict normalization principles and analytical practices.

### Core Tables

- `Events`
- `Players`
- `Teams`
- `Team_Pokemon`
- `Team_Pokemon_Moves`
- `Pokemon`
- `Pokemon_types`
- `Moves`
- `Abilities`
- `Items`
- `Type_lookup`

### Design Decisions

- One Pokémon per row per team
- Separate lookup tables for moves, items, abilities and types
- Foreign key enforcement across all relational tables
- `ON CONFLICT` handling to prevent duplicates
- Name normalization to align Limitless formatting with PokeAPI naming

---

## Data Pipeline

### Step 1 — Pokédex Load

- Pull Pokémon data from PokeAPI
- Insert base stats and typing into:
  - `Pokemon`
  - `Pokemon_types`
  - `abilites`
  - `moves`
  - `items`

### Step 2 — Tournament Scraping

For each tournament:
- Extract event data
- Extract player names and placements
- Extract team compositions
- Extract Pokémon data:
  - Item
  - Ability
  - Tera type
  - Moves (1–4)

All names are normalized before database insertion.

### Step 3 — Database Insertion

- Insert event
- Insert player
- Insert team
- Insert each Pokémon
- Insert moves per Pokémon

---

## Example Analyses (Planned / In Progress)

- Pokémon usage rate by regulation
- Item frequency distribution
- Tera type trends
- Cross-regulation meta comparisons
- Team composition clustering
- Synergy analysis between Pokémon pairs

