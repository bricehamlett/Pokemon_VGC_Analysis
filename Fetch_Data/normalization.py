"""Single normalization boundary for Limitless HTML, Standings, and Play API.

IDs use Limitless's base-form conventions. Explicit forms are never collapsed.
Unidentified name-only forms and contradictory explicit identifiers are flagged.
Original fields are retained alongside canonical values for audit/reprocessing.
"""
import re

VERSION = 1


def slug(value):
    if value is None or not str(value).strip():
        return None
    value = str(value).strip().lower().replace('’', "'").replace("'", '').replace('.', '')
    value = value.replace('♀', '-female').replace('♂', '-male')
    return re.sub(r'[-\s]+', '-', re.sub(r'[()]', '', value)).strip('-') or None


ALIASES = {'aegislash': 'aegislash-shield',
 'alolan-diglett': 'diglett-alola',
 'alolan-dugtrio': 'dugtrio-alola',
 'alolan-exeggutor': 'exeggutor-alola',
 'alolan-geodude': 'geodude-alola',
 'alolan-golem': 'golem-alola',
 'alolan-graveler': 'graveler-alola',
 'alolan-grimer': 'grimer-alola',
 'alolan-marowak': 'marowak-alola',
 'alolan-meowth': 'meowth-alola',
 'alolan-muk': 'muk-alola',
 'alolan-ninetales': 'ninetales-alola',
 'alolan-persian': 'persian-alola',
 'alolan-raichu': 'raichu-alola',
 'alolan-raticate': 'raticate-alola',
 'alolan-rattata': 'rattata-alola',
 'alolan-sandshrew': 'sandshrew-alola',
 'alolan-sandslash': 'sandslash-alola',
 'alolan-vulpix': 'vulpix-alola',
 'basculegion': 'basculegion-male',
 'basculegion-f': 'basculegion-female',
 'bloodmoon-ursaluna': 'ursaluna-bloodmoon',
 'calyrex-ice-rider': 'calyrex-ice',
 'calyrex-shadow-rider': 'calyrex-shadow',
 'cornerstone-mask-ogerpon': 'ogerpon-cornerstone-mask',
 'dawn-wings-necrozma': 'necrozma-dawn',
 'dudunsparce': 'dudunsparce-two-segment',
 'dusk-mane-necrozma': 'necrozma-dusk',
 'enamorus': 'enamorus-incarnate',
 'eternal-flower-floette': 'floette-eternal',
 'family-of-four-maushold': 'maushold-family-of-four',
 'family-of-three-maushold': 'maushold-family-of-three',
 'fan-rotom': 'rotom-fan',
 'female-indeedee': 'indeedee-female',
 'female-meowstic': 'meowstic-female',
 'female-oinkologne': 'oinkologne-female',
 'frost-rotom': 'rotom-frost',
 'galarian-articuno': 'articuno-galar',
 'galarian-corsola': 'corsola-galar',
 'galarian-darmanitan': 'darmanitan-galar-standard',
 'galarian-darumaka': 'darumaka-galar',
 'galarian-farfetchd': 'farfetchd-galar',
 'galarian-linoone': 'linoone-galar',
 'galarian-meowth': 'meowth-galar',
 'galarian-moltres': 'moltres-galar',
 'galarian-mr-mime': 'mr-mime-galar',
 'galarian-ponyta': 'ponyta-galar',
 'galarian-rapidash': 'rapidash-galar',
 'galarian-slowbro': 'slowbro-galar',
 'galarian-slowking': 'slowking-galar',
 'galarian-slowpoke': 'slowpoke-galar',
 'galarian-stunfisk': 'stunfisk-galar',
 'galarian-weezing': 'weezing-galar',
 'galarian-yamask': 'yamask-galar',
 'galarian-zapdos': 'zapdos-galar',
 'galarian-zigzagoon': 'zigzagoon-galar',
 'hearthflame-mask-ogerpon': 'ogerpon-hearthflame-mask',
 'heat-rotom': 'rotom-heat',
 'hisuian-arcanine': 'arcanine-hisui',
 'hisuian-avalugg': 'avalugg-hisui',
 'hisuian-braviary': 'braviary-hisui',
 'hisuian-decidueye': 'decidueye-hisui',
 'hisuian-electrode': 'electrode-hisui',
 'hisuian-goodra': 'goodra-hisui',
 'hisuian-growlithe': 'growlithe-hisui',
 'hisuian-lilligant': 'lilligant-hisui',
 'hisuian-qwilfish': 'qwilfish-hisui',
 'hisuian-samurott': 'samurott-hisui',
 'hisuian-sliggoo': 'sliggoo-hisui',
 'hisuian-sneasel': 'sneasel-hisui',
 'hisuian-typhlosion': 'typhlosion-hisui',
 'hisuian-voltorb': 'voltorb-hisui',
 'hisuian-zoroark': 'zoroark-hisui',
 'hisuian-zorua': 'zorua-hisui',
 'ice-rider-calyrex': 'calyrex-ice',
 'incarnate-landorus': 'landorus-incarnate',
 'indeedee': 'indeedee-male',
 'indeedee-f': 'indeedee-female',
 'indeedee-m': 'indeedee-male',
 'landorus': 'landorus-incarnate',
 'lycanroc': 'lycanroc-midday',
 'male-indeedee': 'indeedee-male',
 'male-meowstic': 'meowstic-male',
 'male-oinkologne': 'oinkologne-male',
 'maushold': 'maushold-family-of-four',
 'meowstic': 'meowstic-male',
 'meowstic-f': 'meowstic-female',
 'mimikyu': 'mimikyu-disguised',
 'mow-rotom': 'rotom-mow',
 'necrozma-dawn-wings': 'necrozma-dawn',
 'necrozma-dusk-mane': 'necrozma-dusk',
 'ogerpon': 'ogerpon',
 'ogerpon-cornerstone': 'ogerpon-cornerstone-mask',
 'ogerpon-hearthflame': 'ogerpon-hearthflame-mask',
 'ogerpon-wellspring': 'ogerpon-wellspring-mask',
 'oinkologne': 'oinkologne-male',
 'oinkologne-f': 'oinkologne-female',
 'palafin': 'palafin-zero',
 'palafin-hero-form': 'palafin-hero',
 'palafin-zero-form': 'palafin-zero',
 'paldean-tauros-aqua-breed': 'tauros-paldea-aqua-breed',
 'paldean-tauros-blaze-breed': 'tauros-paldea-blaze-breed',
 'paldean-tauros-combat-breed': 'tauros-paldea-combat-breed',
 'paldean-wooper': 'wooper-paldea',
 'pyroar': 'pyroar-male',
 'rapid-strike-urshifu': 'urshifu-rapid-strike',
 'shadow-rider-calyrex': 'calyrex-shadow',
 'single-strike-urshifu': 'urshifu-single-strike',
 'squawkabilly': 'squawkabilly-green-plumage',
 'tatsugiri': 'tatsugiri-curly',
 'tatsugiri-droopy-form': 'tatsugiri-droopy',
 'tatsugiri-soggy-form': 'tatsugiri-soggy',
 'tatsugiri-stretchy-form': 'tatsugiri-stretchy',
 'tauros-paldea-aqua': 'tauros-paldea-aqua-breed',
 'tauros-paldea-blaze': 'tauros-paldea-blaze-breed',
 'tauros-paldea-combat': 'tauros-paldea-combat-breed',
 'therian-landorus': 'landorus-therian',
 'thundurus': 'thundurus-incarnate',
 'tornadus': 'tornadus-incarnate',
 'toxtricity': 'toxtricity-amped',
 'ultra-necrozma': 'necrozma-ultra',
 'urshifu': 'urshifu-single-strike',
 'wash-rotom': 'rotom-wash',
 'wellspring-mask-ogerpon': 'ogerpon-wellspring-mask'}

ALIASES.update({'white-kyurem': 'kyurem-white', 'black-kyurem': 'kyurem-black',
                'low-key-toxtricity': 'toxtricity-low-key', 'amped-toxtricity': 'toxtricity-amped',
                'paldean-tauros': 'tauros-paldea'})

# Labels that do not independently establish a form without a source ID.
AMBIGUOUS = {'indeedee', 'maushold', 'landorus', 'palafin', 'lycanroc', 'basculegion',
             'meowstic', 'oinkologne', 'giratina', 'basculin', 'minior', 'squawkabilly'}


def canonical_species(value):
    value = slug(value)
    if value is None:
        return None
    # Display-name ordering differs from source IDs; retain the actual form.
    if value.startswith('mega-'):
        base = value[5:]
        if base.endswith(('-x', '-y')):
            value = base[:-2] + '-mega' + base[-2:]
        else:
            value = base + '-mega'
    elif value.startswith('gigantamax-'):
        value = value[11:] + '-gmax'
    elif value.startswith('origin-forme-'):
        value = value[13:] + '-origin'
    return ALIASES.get(value, value)


def species(p):
    identifier = slug(p.get('id'))
    display = slug(p.get('name') or p.get('pokemon_name'))
    issues = []
    # Canonical database rows have already specified their exact form.
    if not identifier:
        result = canonical_species(display)
        if display in AMBIGUOUS:
            issues.append('error:ambiguous_form:' + display)
    else:
        result = canonical_species(identifier)
        named = canonical_species(display)
        if display and named != result:
            # A generic species ID can coexist with an explicit display form.
            if display not in AMBIGUOUS and named and named.startswith(identifier + '-'):
                result = named
            elif display not in AMBIGUOUS and identifier != display and not identifier.startswith(display + '-'):
                issues.append('error:contradictory_form')
    item = slug(p.get('item'))
    if result == 'zacian' and item == 'rusted-sword':
        result = 'zacian-crowned'
    if result == 'zamazenta' and item == 'rusted-shield':
        result = 'zamazenta-crowned'
    return result, issues


def ability(value, pokemon_name):
    value = slug(value)
    if value == 'as-one':
        return {'calyrex-ice': 'as-one-glastrier', 'calyrex-shadow': 'as-one-spectrier'}.get(pokemon_name, value)
    if value == 'mind' and pokemon_name == 'ursaluna-bloodmoon':
        return 'minds-eye'
    return value


def pokemon(p):
    name, issues = species(p)
    item = p.get('item')
    if isinstance(item, str):
        item = re.sub(r'^held\s*item\s*:\s*', '', item.strip(), flags=re.I)
    tera = p.get('tera')
    moves = p.get('moves', p.get('attacks', [])) or []
    return {'pokemon_name': name, 'item': slug(item),
            'ability': ability(p.get('ability'), name),
            'tera': tera if isinstance(tera, int) else slug(tera),
            'moves': [slug(m) for m in moves if slug(m) not in (None, '-')],
            'normalization_issues': issues, 'normalization_version': VERSION,
            'source_fields': dict(p)}
