DROP TABLE IF EXISTS Team_Pokemon_EV CASCADE;
DROP TABLE IF EXISTS Team_Pokemon CASCADE;
DROP TABLE IF EXISTS Pokemon_types CASCADE;
DROP TABLE IF EXISTS Team_Pokemon_Moves CASCADE;

	
DROP TABLE IF EXISTS Teams CASCADE;
DROP TABLE IF EXISTS Events CASCADE;
DROP TABLE IF EXISTS Players CASCADE;

DROP TABLE IF EXISTS Moves CASCADE;
DROP TABLE IF EXISTS Items CASCADE;
DROP TABLE IF EXISTS Abilities CASCADE;
DROP TABLE IF EXISTS Natures CASCADE;
DROP TABLE IF EXISTS Pokemon CASCADE;
DROP TABLE IF EXISTS Type_lookup CASCADE;


CREATE TABLE Events (
	event_id 				SERIAL PRIMARY KEY,
	event_name 				Varchar(50) UNIQUE, 
	regulation 				CHAR(1)
);

CREATE TABLE Players (
	player_id 				SERIAL PRIMARY KEY,
	player_name 			VARCHAR(50)
);

CREATE TABLE Teams (
	team_id 				SERIAL PRIMARY KEY,
	event_id				INTEGER NOT NULL,
	player_id				INTEGER NOT NULL,
	
	FOREIGN KEY (event_id)	REFERENCES Events(event_id),
	FOREIGN KEY(player_id) 	REFERENCES Players(player_id),
	CONSTRAINT uq_teams_event_player UNIQUE(player_id, event_id) 
);

CREATE TABLE Type_lookup (
	type_id 				SERIAL PRIMARY KEY,
	type_name 				VARCHAR(20) UNIQUE
);

CREATE TABLE Natures (
	nature_id 				SERIAL PRIMARY KEY,
	nature_name 			VARCHAR(12)
);

CREATE TABLE Abilities (
	ability_id 				SERIAL PRIMARY KEY,
	ability_name 			VARCHAR(50)
);

CREATE TABLE Items (
	item_id 				SERIAL PRIMARY KEY,
	item_name 				VARCHAR(50)
);

CREATE TABLE Moves (
    move_id     SERIAL PRIMARY KEY,
    move_name   VARCHAR(100),
    type_id     INT,
    accuracy    INT,
    power       INT,
    priority    INT,

	FOREIGN KEY(type_id) REFERENCES Type_lookup(type_id)
);

CREATE TABLE Pokemon (
	poke_dex 				INT PRIMARY KEY,
	pokemon_name 			VARCHAR(100)
);

CREATE TABLE Pokemon_types (
	poke_dex 					INTEGER NOT NULL,
	type_id						INTEGER NOT NULL,
	
	FOREIGN KEY (poke_dex) 		REFERENCES Pokemon(poke_dex),
	FOREIGN KEY (type_id) 		REFERENCES Type_lookup(type_id),
	PRIMARY KEY(poke_dex, type_id)
);


CREATE TABLE Team_Pokemon (
	team_pokemon_id 		SERIAL PRIMARY KEY,
	team_id 				INTEGER NOT NULL,
	slot 					INT NOT NULL CHECK(slot >= 1 and slot <= 6),
	poke_dex 				INTEGER NOT NULL,
	nature_id				INTEGER,
	item_id					INTEGER,
	tera_type				INTEGER,
	ability_id				INTEGER,
	
	

	FOREIGN KEY (team_id) 	REFERENCES Teams(team_id),
	FOREIGN KEY(poke_dex) 	REFERENCES Pokemon(poke_dex),
	FOREIGN KEY(nature_id) 	REFERENCES Natures(nature_id),
	FOREIGN KEY(item_id) 	REFERENCES Items(item_id),
	FOREIGN KEY(tera_type) 	REFERENCES Type_lookup(type_id),
	FOREIGN KEY(ability_id)	REFERENCES Abilities(ability_id),
	
	UNIQUE(team_id, slot)
);

CREATE TABLE Team_Pokemon_EV (
	team_pokemon_id 		INTEGER NOT NULL PRIMARY KEY,
	FOREIGN KEY(team_pokemon_id) REFERENCES Team_Pokemon(team_pokemon_id)
	ON DELETE CASCADE,

	hp  					SMALLINT NOT NULL CHECK (hp  BETWEEN 0 AND 252),
    atk						SMALLINT NOT NULL CHECK (atk BETWEEN 0 AND 252),
    def 					SMALLINT NOT NULL CHECK (def BETWEEN 0 AND 252),
    spa 					SMALLINT NOT NULL CHECK (spa BETWEEN 0 AND 252),
    spd 					SMALLINT NOT NULL CHECK (spd BETWEEN 0 AND 252),
    spe 					SMALLINT NOT NULL CHECK (spe BETWEEN 0 AND 252),

    CHECK (hp + atk + def + spa + spd + spe <= 510)
	
);

CREATE TABLE Team_Pokemon_Moves (
    team_pokemon_id INT,
    move_id         INT,
    move_slot       INT CHECK (move_slot BETWEEN 1 AND 4),
    PRIMARY KEY (team_pokemon_id, move_slot),
	
    CONSTRAINT uq_team_pokemon_move UNIQUE (team_pokemon_id, move_id),
    CONSTRAINT fk_tpm_team_pokemon
   	FOREIGN KEY (team_pokemon_id)		REFERENCES Team_Pokemon(team_pokemon_id),
    CONSTRAINT fk_tpm_move
    FOREIGN KEY (move_id)				REFERENCES Moves(move_id)
);

