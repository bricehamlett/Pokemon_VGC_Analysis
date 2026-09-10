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
	event_id 				INTEGER PRIMARY KEY,
	event_name 				Varchar(50) UNIQUE, 
	regulation 				VARCHAR(3),
	event_date 				DATE,
	event_size				INTEGER NOT NULL
);

CREATE TABLE Players (
	player_id 				SERIAL PRIMARY KEY,
	player_name 			VARCHAR(50)
);

CREATE TABLE Teams (
	team_id 				SERIAL PRIMARY KEY,
	event_id				INTEGER NOT NULL,
	player_id				INTEGER NOT NULL,
	placement				INTEGER,
	
	FOREIGN KEY (event_id)	REFERENCES Events(event_id),
	FOREIGN KEY(player_id) 	REFERENCES Players(player_id),
	CONSTRAINT uq_teams_event_player UNIQUE(player_id, event_id) 
);

CREATE TABLE Type_lookup (
	type_id 				INT PRIMARY KEY,
	type_name 				VARCHAR(20) UNIQUE
);

CREATE TABLE Abilities (
	ability_id 				INT PRIMARY KEY,
	ability_name 			VARCHAR(50)
);

CREATE TABLE Items (
	item_id 				SERIAL PRIMARY KEY,
	item_name 				VARCHAR(50)
);

CREATE TABLE Moves (
    move_id     INT PRIMARY KEY,
    move_name   VARCHAR(100),
    type_id     INT,
    accuracy    INT,
    power       INT,
    priority    INT,

	FOREIGN KEY(type_id) REFERENCES Type_lookup(type_id)
);

CREATE TABLE Pokemon (
	pk_id 					SERIAL PRIMARY KEY,
	poke_dex 				INT NOT NULL,
	pokemon_name 			VARCHAR(100) UNIQUE NOT NULL,
	generation 				INT NOT NULL,
	hp  					SMALLINT NOT NULL,
  	atk   					SMALLINT NOT NULL,
  	def   					SMALLINT NOT NULL,
  	spa   					SMALLINT NOT NULL,
  	spd  					SMALLINT NOT NULL,
  	spe   					SMALLINT NOT NULL
);

CREATE TABLE Pokemon_types (
	pk_id						INTEGER NOT NULL,
	type_id						INTEGER NOT NULL,
	slot						INTEGER CHECK(slot BETWEEN 1 and 2),
	
	FOREIGN KEY (pk_id) 		REFERENCES Pokemon(pk_id),
	FOREIGN KEY (type_id) 		REFERENCES Type_lookup(type_id),
	PRIMARY KEY(pk_id, type_id)
);


CREATE TABLE Team_Pokemon (
	team_pokemon_id 		SERIAL PRIMARY KEY,
	team_id 				INTEGER NOT NULL,
	slot 					INT NOT NULL CHECK(slot >= 1 and slot <= 6),
	pk_id 					INTEGER NOT NULL,
	poke_dex 				INTEGER NOT NULL,
	item_id					INTEGER,
	tera_type				INTEGER,
	ability_id				INTEGER,
	
	

	FOREIGN KEY (team_id) 	REFERENCES Teams(team_id),
	FOREIGN KEY(item_id) 	REFERENCES Items(item_id),
	FOREIGN KEY(tera_type) 	REFERENCES Type_lookup(type_id),
	FOREIGN KEY(ability_id)	REFERENCES Abilities(ability_id),
	FOREIGN KEY(pk_id) 		REFERENCES Pokemon(pk_id),
	UNIQUE(team_id, slot)
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

