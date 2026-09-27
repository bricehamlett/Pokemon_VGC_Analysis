# VGC Team Builder — Project Overview

## Goal

Build a regulation-aware VGC team builder that accepts one or more Pokémon and recommends a complete, legal team with compatible builds.

---

## System Overview

```text
User selects:
- Regulation
- One or more Pokémon
- Optional locked items, abilities, Tera types, or moves
                    ↓
Partner Recommendation Model
Suggests compatible Pokémon
                    ↓
Team Generator
Creates several legal six-Pokémon teams
                    ↓
Team Evaluation Model
Scores and ranks the completed teams
                    ↓
Team Builder Output
Returns the strongest supported recommendations