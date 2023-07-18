import numpy as np
from scipy.interpolate import interp1d
import matplotlib.colors as mcolors
from datetime import datetime
import json, sqlite3, re, time
import dateutil.parser


def compute_colour(x):
    domain = np.array([0.1, 1.25, 2, 2.5, 3.3, 4.2, 4.9, 5.8, 6.7, 7.7, 9])
    range_values = np.array(['#4290FB', '#4FC0FF', '#4FFFD5', '#7CFF4F', '#F6F05C', '#FF8068', '#FF4E6F', '#C645B8', '#6563DE', '#18158E', '#000000'])
    range_numeric = np.array([mcolors.to_rgb(color) for color in range_values])
    interp = interp1d(domain, range_numeric, axis=0, kind='linear')

    # Ensure that x is within the defined domain range
    x = np.clip(x, domain[0], domain[-1])

    interpolated_color = interp(x)
    interpolated_color_hex = mcolors.to_hex(interpolated_color)
    return interpolated_color_hex


def beatmap_row(row):
    # Convert the values to the appropriate types
    row[0] = int(row[0])
    row[3] = float(row[3])
    row[4:7] = map(int, row[4:7])
    row[7:12] = map(float, row[7:12])
    row[12:17] = map(int, row[12:17])
    row[17] = datetime.strptime(row[17], "%Y-%m-%d %H:%M:%S%z")
    row[18] = int(row[18])
    row[19] = int(row[19])
    row[24] = int(row[24])
    row[25] = float(row[25])
    row[26] = float(row[26])
    row[27] = datetime.strptime(row[27], "%Y-%m-%d %H:%M:%S%z")
    row[28] = int(row[28])
    return row


def get_mods(mod):
    mods = ["NF", "EZ", "TD", "HD", "HR", "SD", "DT", "RX", "HT", "NC", "FL", "AT", "SO", "AP", "PF"]
    combination = []
    for i in range(15):
        if mod & 1 == 1:
            combination += [mods[i]]
        mod >>= 1
    if "NC" in combination:
        combination.remove("DT")
    if "PF" in combination:
        combination.remove("SD")
    return combination


def users_row(row):
    row[15] = datetime.strptime(row[15], "%Y-%m-%d %H:%M:%S%z")
    row[16] = json.loads(row[16])
    row[19] = datetime.strptime(row[19], "%Y-%m-%d %H:%M:%S.%f")
    return row


def search_beatmaps(search_query, sort):
    print("Entered query:", search_query, sort)
    search_query, filters, sort, status = parse_input(search_query, sort)
    print("Processed query:", search_query, filters, sort)
    conn = sqlite3.connect("db/maps.db")
    cursor = conn.cursor()

    values = []
    # Prepare the SQL query
    query = "SELECT beatmapset_id, total_playcount, max_star_rating, min_star_rating, ranked_date, favourite_count FROM (SELECT * FROM ranked_maps UNION SELECT * FROM loved_maps) AS maps WHERE "
    if status is not None:
        query += f"""(status LIKE "%{status}%" COLLATE NOCASE) AND ("""
    else:
        query += "("

    text_conditions = []
    filter_conditions = []

    # Process the search query
    terms = re.findall(r'"([^"]+)"|(\S+)', search_query)
    if len(terms) == 0:
        terms = [("", "")]
    for i in range(len(terms)):
        text_conditions.append("(search_tags LIKE ? COLLATE NOCASE)")

    # add filter conditions
    for attribute, value, operator in filters:
        filter_conditions.append(f"({attribute} {operator} ?)")

    query += " OR ".join(text_conditions)
    if len(filter_conditions) > 0:
        query += ") AND "
        query += " AND ".join(filter_conditions)
    else:
        query += ")"

    query += f" GROUP BY beatmapset_id ORDER BY {sort}"
    query += " LIMIT 50"

    # Prepare the values for the search conditions
    for term in terms:
        if term[0]:
            values += [f"%{term[0]}%"]
        else:
            values += [f"%{term[1]}%"]

    # Add the values for the INTEGER/REAL filters
    values += [value for _, value, _ in filters]

    cursor.execute(query, tuple(values))

    results = cursor.fetchall()
    return [result[0] for result in results]


def validate_filter(attribute, comp, value):
    if attribute in ["beatmap_id", "star_rating", "max_combo", "total_length", "hit_length", "bpm", "cs", "ar", "od", "hp",
                     "circles", "sliders", "spinners", "passcount", "playcount", "user_id", "beatmapset_id", "favourite_count"]:
        try:
            value = float(value)
        except Exception as e:
            return False, value
    elif attribute in ["last_updated"]:
        try:
            value = dateutil.parser.isoparse(value)
        except Exception as e:
            return False, value
    return True, value


def parse_input(search_string, sort):
    if search_string is None:
        search_string = ""
    search_string = search_string.lower()
    terms = re.findall(r'"([^"]+)"|(\S+)', search_string)
    items = []
    for term in terms:
        if len(term[0]) > 0:
            items += [f'"{term[0]}"']
        else:
            items += [term[1]]
    comparators = ["<=", "!=", ">=", "<", "=", ">"]
    attribute_map = {
        "beatmap_id": "beatmap_id", "id": "beatmap_id",
        "star_rating": "star_rating", "sr": "star_rating", "difficulty": "star_rating", "difficulty_rating": "star_rating", "stars": "star_rating", "star": "star_rating",
        "max_combo": "max_combo", "combo": "max_combo", "mc": "max_combo",
        "total_length": "total_length", "length": "total_length", "time": "total_length",
        "hit_length": "hit_length", "drain_time": "hit_length",
        "bpm": "bpm", "beats": "bpm", "beats_per_minute": "bpm",
        "cs": "cs", "circle_size": "cs",
        "ar": "ar", "approach_rate": "ar",
        "od": "od", "accuracy": "od", "overall_difficulty": "od",
        "hp": "hp", "drain": "hp", "health": "hp", "drain_rate": "hp",
        "circles": "circles", "count_circles": "circles", "circle_count": "circles",
        "sliders": "sliders", "count_sliders": "sliders", "slider_count": "sliders",
        "spinners": "spinners", "count_spinners": "spinners", "spinner_count": "spinners",
        "passcount": "passcount", "passes": "passcount",
        "playcount": "playcount", "plays": "playcount",
        "favouritecount": "favourite_count", "favourites": "favourite_count",
        "last_updated": "last_updated", "ranked": "last_updated", "updated": "last_updated",
        "user_id": "user_id", "mapper_id": "user_id",
        "beatmapset_id": "beatmapset_id", "bid": "beatmapset_id",
    }
    rankstatus = {
        "approved": "approved",
        "a": "approved",
        "ranked": "ranked",
        "r": "ranked",
        "loved": "loved",
        "l": "loved"
    }
    sort_map = {"title": "title", "artist": "artist", "difficulty": "star_rating", "ranked": "ranked_date", "playcount": "total_playcount", "favourites": "favourite_count"}
    main_query = []
    filters = []
    status = None
    for item in items:
        comp = None
        for c in comparators:
            if c in item:
                comp = c
                break
        if comp is not None:
            fields = item.split(comp)
            if len(fields) != 2:
                continue
            attribute, value = fields
            if attribute == "status" and value.lower() in rankstatus and comp == "=":
                status = rankstatus[value.lower()]
            elif attribute not in attribute_map:
                continue
            else:
                attribute = attribute_map[attribute]
                response, value = validate_filter(attribute, comp, value)
                if not response:
                    continue
                filters.append((attribute, value, comp))
        else:
            main_query.append(item)
    sort = sort.split()
    if len(sort) > 2:
        sort = "total_playcount DESC"
    else:
        sortmode, order = sort
        sortmode = sortmode.lower()
        if sortmode in sort_map:
            sortmode = sort_map[sortmode]
        else:
            sortmode = "total_playcount"
        order = order.upper()
        if order not in ["ASC", "DESC"]:
            order = "DESC"
        sort = f"{sortmode} {order}"
    if sort == "star_rating DESC":
        sort = "max_star_rating DESC"
    elif sort == "star_rating ASC":
        sort = "min_star_rating ASC"
    return ' '.join(list(set(main_query))), filters, sort, status


if __name__ == '__main__':
    print("util_functions.py")
