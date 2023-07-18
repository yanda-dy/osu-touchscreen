from flask import Flask, render_template, request, flash, redirect, url_for, session
from flask_bootstrap import Bootstrap
import sqlite3, time, threading, json, secrets, hashlib
from datetime import datetime, timedelta, timezone
from babel.dates import format_timedelta
from ossapi import Ossapi, OssapiV1, Mod, GameMode
from rosu_pp_py import Beatmap, Calculator
import schedule

from database_update import insert_score, check_beatmap, insert_beatmap, update_ranked, check_user, insert_user_scores, \
    insert_user, insert_user_recent, insert_map, insert_beatmap_user
from util_functions import compute_colour, beatmap_row, get_mods, users_row, search_beatmaps
from database_reprocess import reprocess_maps


with open('config.json', 'r') as config_file:
    config = json.load(config_file)
admin_path = "/admin_" + secrets.token_urlsafe(32)
config["admin_path"] = admin_path
config["admin"] = secrets.token_hex(32)
with open('config.json', 'w') as config_file:
    json.dump(config, config_file, indent=2)
ranks = {"XH": "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/badges/score-ranks-v2019/GradeSmall-SS-Silver.svg",
         "X": "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/badges/score-ranks-v2019/GradeSmall-SS.svg",
         "SH": "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/badges/score-ranks-v2019/GradeSmall-S-Silver.svg",
         "S": "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/badges/score-ranks-v2019/GradeSmall-S.svg",
         "A": "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/badges/score-ranks-v2019/GradeSmall-A.svg",
         "B": "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/badges/score-ranks-v2019/GradeSmall-B.svg",
         "C": "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/badges/score-ranks-v2019/GradeSmall-C.svg",
         "D": "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/badges/score-ranks-v2019/GradeSmall-D.svg"}
mod_names = {"NF": "No Fail", "EZ": "Easy", "TD": "Touch Device", "HD": "Hidden", "HR": "Hard Rock",
             "SD": "Sudden Death", "DT": "Double Time", "RX": "Relax", "HT": "Half Time", "NC": "Nightcore",
             "FL": "Flashlight", "AT": "Auto", "SO": "Spun Out", "AP": "Autopilot", "PF": "Perfect"}


class ScoreData:
    def __init__(self, data, index):
        global ranked, loved
        self.replay_id, self.beatmap_id, self.score, self.username, self.count_300, self.count_100, self.count_50, self.count_miss,\
        self.max_combo, self.perfect, self.mods, self.user_id, self.date, self.rank, self.pp, self.star_rating = data
        self.accuracy_str = f"{round(100 * (self.count_300 + self.count_100 / 3 + self.count_50 / 6) / (self.count_300 + self.count_100 + self.count_50 + self.count_miss),2):<0.2f}%"
        self.score = f"{self.score:,}"
        self.date = datetime.strptime(self.date, "%Y-%m-%d %H:%M:%S%z")
        tdelta = datetime.now(timezone.utc)-self.date
        self.time_relative = f"{format_timedelta(tdelta, locale='en_US')} ago"
        time_rel = format_timedelta(tdelta, locale='en_US').split()
        self.time_relative_short = time_rel[0] + time_rel[1][0]
        total_seconds = int(tdelta.total_seconds())
        if total_seconds < 3600:
            self.time_relative_short = "now"
        self.time_str = self.date.strftime('%d %B %Y %H:%M:%S')
        self.pp = round(self.pp, 3)
        if self.beatmap_id not in ranked and self.beatmap_id not in loved:
            print(f"Attempting to add map {self.beatmap_id}")
            beatmapset = api.beatmapset(beatmap_id=self.beatmap_id)
            total_playcount = 0
            max_sr = -1
            min_sr = 1000000000
            for beatmap in beatmapset.beatmaps:
                total_playcount += beatmap.playcount
                max_sr = max(max_sr, beatmap.difficulty_rating)
                min_sr = min(min_sr, beatmap.difficulty_rating)
            for beatmap in beatmapset.beatmaps:
                if beatmap.mode == GameMode.OSU:
                    data = [(beatmap.id, str(beatmap.mode), str(beatmap.status), beatmap.difficulty_rating, beatmap.max_combo, beatmap.total_length, beatmap.hit_length, beatmap.bpm, beatmap.cs, beatmap.ar, beatmap.accuracy, beatmap.drain, beatmap.count_circles, beatmap.count_sliders, beatmap.count_spinners, beatmap.passcount, beatmap.playcount, str(beatmap.last_updated), beatmap.user_id, beatmapset.id, str(beatmapset.artist), str(beatmapset.creator), str(beatmapset.title), str(beatmap.version), total_playcount, max_sr, min_sr, str(beatmapset.ranked_date), beatmapset.favourite_count, f"{str(beatmapset.title)}―{str(beatmap.version)}―{str(beatmapset.artist)}―{str(beatmapset.creator)}―{str(beatmapset.id)}―{str(beatmap.id)}―{str(beatmapset.source)}―{str(beatmapset.tags)}")]
                    if str(beatmap.status) in ["RankStatus.RANKED", "RankStatus.APPROVED"]:
                        insert_map("ranked", data)
                    elif str(beatmap.status) == "RankStatus.LOVED":
                        insert_map("loved", data)
                if beatmap.id == self.beatmap_id:
                    self.diff_name = beatmap.version
                    self.map_name = beatmapset.title
                    self.creator = beatmapset.creator
                    self.artist = beatmapset.artist
                    self.beatmap_max_combo = beatmap.max_combo
            ranked = load_maps("ranked")
            loved = load_maps("loved")
        else:
            maptype = ranked if self.beatmap_id in ranked else loved
            self.diff_name = maptype[self.beatmap_id][23]
            self.map_name = maptype[self.beatmap_id][22]
            self.creator = maptype[self.beatmap_id][21]
            self.artist = maptype[self.beatmap_id][20]
            self.beatmap_max_combo = maptype[self.beatmap_id][4]
        self.rank_link = ranks[self.rank]
        self.mod_list = get_mods(self.mods)
        self.mod_names = mod_names
        self.index = index


class UserData:
    def __init__(self, data, lookup, rank):
        self.user_id = data[0]
        self.net_pp = f"{round(data[1]):,}"
        self.net_acc = f"{round(data[2],2):0.2f}%"
        self.net_sr = f"{round(data[3],2):0.2f}"
        self.username = lookup[data[0]]
        self.rank = f"#{rank}"
        self.num_scores = f"{data[4]:,}"
        if self.user_id in userdata:
            user = userdata[self.user_id]
            self.country_name = user[7]
            base = int("1f1e6", 16) - ord('A')
            d1 = ord(user[8][0]) + base
            d2 = ord(user[8][1]) + base
            self.country_image = f"https://osu.ppy.sh/assets/images/flags/{hex(d1)[2::]}-{hex(d2)[2::]}.svg"
            self.is_active = "true" if user[14]==1 else "false"
        else:
            self.username += " (likely restricted)"
            self.country_name = "Unknown"
            self.country_image = "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/flags/fallback.png"


class FullUser:
    def __init__(self, data):
        self.user_id = data[0]
        self.username = data[1]
        if len(data) == 2:
            data = ["Unknown"]*19
            data[2] = "https://osu.ppy.sh/images/layout/avatar-guest.png"
        self.avatar_url = data[2]
        self.badges = data[3]
        self.medals = data[4]
        self.replays_watched = data[5]
        self.playcount = data[6]
        self.country_name = data[7]
        self.country_code = data[8]
        self.cover_url = data[9]
        self.follower_count = data[10]
        self.loved_count = data[11]
        self.ranked_count = data[12]
        self.guest_count = data[13]
        self.is_active = data[14]
        self.join_data = data[15]
        self.previous_usernames = data[16]
        self.has_supporter = data[17]
        self.support_level = data[18]
        base = int("1f1e6", 16) - ord('A')
        d1 = ord(self.country_code[0]) + base
        d2 = ord(self.country_code[1]) + base
        self.country_image = f"https://osu.ppy.sh/assets/images/flags/{hex(d1)[2::]}-{hex(d2)[2::]}.svg"
        if self.user_id in user_ranking_lookup:
            self.ranking = f"#{user_ranking_lookup[self.user_id]:,}"
        else:
            self.ranking = "Unknown"


class BeatmapData:
    def __init__(self, data):
        self.beatmap_id = data[0]
        self.mode = data[1]
        self.status = data[2]
        self.star_rating = data[3]
        self.max_combo = data[4]
        self.total_length = data[5]
        self.total_length_str = f"{data[5]//60}:{data[5]%60:02d}"
        self.hit_length = data[6]
        self.hit_length_str = f"{data[6]//60}:{data[6]%60:02d}"
        self.bpm = round(data[7], 2)
        self.cs = data[8]
        self.ar = data[9]
        self.od = data[10]
        self.hp = data[11]
        self.circles = data[12]
        self.sliders = data[13]
        self.spinners = data[14]
        self.passcount = data[15]
        self.passcount_str = f"{data[15]:,}"
        self.playcount = data[16]
        self.playcount_str = f"{data[16]:,}"
        self.favouritecount = data[28]
        self.favouritecount_str = f"{data[28]:,}"
        if data[16] != 0:
            self.pass_percent = f"{round(100*data[15]/data[16],1)}%"
        else:
            self.pass_percent = "0%"
        self.last_updated = data[17]
        self.last_updated_long = data[17].strftime("%d %B %Y %H:%M:%S")
        self.last_updated_str = data[17].strftime("%d %b %Y")
        self.ranked_date = data[27]
        self.ranked_date_long = data[27].strftime("%d %B %Y %H:%M:%S")
        self.ranked_date_str = data[27].strftime("%d %b %Y")
        self.user_id = data[18]
        self.beatmapset_id = data[19]
        self.artist = data[20]
        self.creator = data[21]
        self.song_name = data[22]
        self.diff_name = data[23]
        self.colour = str(compute_colour(self.star_rating))
        self.tags = data[29].split("―")
        self.total_playcount = data[24]
        self.total_playcount_str = f"{data[24]:,}"
        temp_total = self.total_playcount
        units = ['', 'K', 'M', 'B', 'T']
        block = 1000
        for unit in units:
            if abs(temp_total) < block:
                self.total_playcount_short = f"{temp_total:.1f}{unit}"
                if len(unit) == 0:
                    self.total_playcount_short = str(temp_total)
                break
            temp_total /= block


def load_maps(status):
    global beatmapset_lookup
    if status not in ["ranked", "loved"]:
        return -1
    map_info = {}
    path = "db/maps.db"
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    query = f"SELECT * FROM {status}_maps"
    cursor.execute(query)
    rows = cursor.fetchall()

    bms_reset = set()
    for row in rows:
        map_info[row[0]] = beatmap_row(list(row))
        bms_reset.add(row[19])
    for bms_id in bms_reset:
        beatmapset_lookup[bms_id] = []
    for row in rows:
        beatmapset_lookup[row[19]] += [(row[0], row[3])]

    for bms_id in beatmapset_lookup:
        beatmapset_lookup[bms_id].sort(key=lambda x: x[1])

    return map_info


def load_users():
    global username_lookup
    conn = sqlite3.connect("db/users.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users"
    cursor.execute(query)
    rows = cursor.fetchall()

    users = {}
    username_lookup = {}

    for row in rows:
        users[row[0]] = users_row(list(row))
        for user in users[row[0]][16]:
            username_lookup[user.lower()] = row[0]
    return users


def select_user(cursor, username=None, userid=None):
    if username is not None:
        userid = username_lookup[username.lower()]

    select_query = '''
    SELECT replay_id, beatmap_id, score, username, count_300, count_100, count_50, count_miss,
           max_combo, perfect, mods, user_id, date, rank, pp, star_rating
    FROM (
        SELECT replay_id, beatmap_id, score, username, count_300, count_100, count_50, count_miss,
               max_combo, perfect, mods, user_id, date, rank, pp, star_rating,
               ROW_NUMBER() OVER (PARTITION BY user_id, beatmap_id ORDER BY pp DESC) AS rn
        FROM td_scores
        WHERE user_id = ?
    ) t
    WHERE rn = 1
    ORDER BY pp DESC;
    '''
    cursor.execute(select_query, (userid,))
    rows = cursor.fetchall()

    return rows


def get_score_all(cursor):
    query = '''
    SELECT username, user_id, beatmap_id, score, count_300, count_100, count_50, count_miss, star_rating
    FROM td_scores
    ORDER BY score DESC;
    '''
    cursor.execute(query)
    rows = cursor.fetchall()
    return rows


def get_pp_all(cursor):
    query = '''
    SELECT username, user_id, beatmap_id, pp, count_300, count_100, count_50, count_miss, star_rating
    FROM td_scores
    ORDER BY pp DESC;
    '''
    cursor.execute(query)
    rows = cursor.fetchall()
    return rows


def get_pp(status):
    if status == "ranked":
        conn = sqlite3.connect('db/td_scores.db')
        cursor = conn.cursor()
        table = "td_scores"
    elif status == "loved":
        conn = sqlite3.connect('db/td_scores-loved.db')
        cursor = conn.cursor()
        table = "td_scores_loved"
    else:
        print(f"invalid status: {status}")
        return
    query = f'''
    SELECT replay_id, beatmap_id, score, username, count_300, count_100, count_50, count_miss,
           max_combo, perfect, mods, user_id, date, rank, pp, star_rating
    FROM (
        SELECT replay_id, beatmap_id, score, username, count_300, count_100, count_50, count_miss,
               max_combo, perfect, mods, user_id, date, rank, pp, star_rating,
               ROW_NUMBER() OVER (PARTITION BY user_id, beatmap_id ORDER BY pp DESC) AS rn
        FROM {table}
    ) t
    WHERE rn = 1
    ORDER BY pp DESC;
    '''
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return rows


def beatmap_scores(beatmap_id):
    if beatmap_id in ranked:
        conn = sqlite3.connect('db/td_scores.db')
        cursor = conn.cursor()
        table = "td_scores"
    elif beatmap_id in loved:
        conn = sqlite3.connect('db/td_scores-loved.db')
        cursor = conn.cursor()
        table = "td_scores_loved"
    else:
        return -1
    query = f'''
    SELECT replay_id, beatmap_id, score, username, count_300, count_100, count_50, count_miss,
           max_combo, perfect, mods, user_id, date, rank, pp, star_rating
    FROM {table}
    WHERE beatmap_id = ?
    ORDER BY score DESC;
    '''
    cursor.execute(query, (beatmap_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def score_ranking():
    global user_score_ranking, user_score_lookup, user_score_ranking_lookup
    conn = sqlite3.connect('db/td_scores.db')
    cursor = conn.cursor()
    data = get_score_all(cursor)
    user_score_lookup = {}
    user_scores = {}
    for row in data:
        username, user_id, beatmap_id, score, count_300, count_100, count_50, count_miss, star_rating = row
        if username is not None:
            user_score_lookup[user_id] = username
        acc = (count_300 + count_100 / 3 + count_50 / 6) / (count_300 + count_100 + count_50 + count_miss)
        if user_id not in user_scores:
            user_scores[user_id] = {beatmap_id: [score, acc, star_rating]}
        elif beatmap_id in user_scores[user_id]:
            if score > user_scores[user_id][beatmap_id][0]:
                user_scores[user_id][beatmap_id] = [score, acc, star_rating]
        else:
            user_scores[user_id][beatmap_id] = [score, acc, star_rating]
    user_score_ranking = []
    user_score_ranking_lookup = {}
    for user_id in user_scores:
        sorted_score = sorted(user_scores[user_id].items(), key=lambda x: x[1][0], reverse=True)
        total_score = 0
        for score in sorted_score:
            total_score += score[1][0]
        user_score_ranking += [(user_id, total_score, 0, 0, len(user_scores[user_id]))]
    user_score_ranking = sorted(user_score_ranking, key=lambda x: x[1], reverse=True)
    for i in range(len(user_ranking)):
        user_score_ranking_lookup[user_ranking[i][0]] = i + 1
    return user_score_ranking, user_score_lookup, user_score_ranking_lookup


def pp_ranking():
    global user_ranking, user_lookup, user_ranking_lookup
    conn = sqlite3.connect('db/td_scores.db')
    cursor = conn.cursor()
    data = get_pp_all(cursor)
    user_lookup = {}
    user_scores = {}
    for row in data:
        username, user_id, beatmap_id, pp, count_300, count_100, count_50, count_miss, star_rating = row
        if username is not None:
            user_lookup[user_id] = username
        acc = (count_300 + count_100 / 3 + count_50 / 6) / (count_300 + count_100 + count_50 + count_miss)
        if user_id not in user_scores:
            user_scores[user_id] = {beatmap_id: [pp, acc, star_rating]}
        elif beatmap_id in user_scores[user_id]:
            if pp > user_scores[user_id][beatmap_id][0]:
                user_scores[user_id][beatmap_id] = [pp, acc, star_rating]
        else:
            user_scores[user_id][beatmap_id] = [pp, acc, star_rating]
    user_ranking = []
    user_ranking_lookup = {}
    for user_id in user_scores:
        sorted_pp = sorted(user_scores[user_id].items(), key=lambda x: x[1][0], reverse=True)
        net_pp = 0
        net_acc = 0
        net_sr = 0
        for i in range(min(100, len(sorted_pp))):
            net_pp += 0.95 ** i * sorted_pp[i][1][0]
            net_acc += 0.95 ** i * sorted_pp[i][1][1]
            net_sr += 0.95 ** i * sorted_pp[i][1][2]
        net_acc *= 100 / (20 * (1 - pow(0.95, min(100, len(sorted_pp)))))
        net_sr /= (20 * (1 - pow(0.95, min(100, len(sorted_pp)))))
        user_ranking += [(user_id, net_pp, net_acc, net_sr, len(user_scores[user_id]))]
    user_ranking = sorted(user_ranking, key=lambda x: x[1], reverse=True)
    for i in range(len(user_ranking)):
        user_ranking_lookup[user_ranking[i][0]] = i+1
    return user_ranking, user_lookup, user_ranking_lookup


app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
bootstrap = Bootstrap(app)


@app.route('/')
def index_redirect():
    return redirect(url_for('index'))


@app.route('/home')
def index():
    search_type = request.args.get('search_type')
    query = request.args.get('query')
    if search_type is None:
        return render_template('home.html')
    if query is None:
        return render_template('home.html', search_type=search_type)

    return render_template('home.html', search_type=search_type, query=query)


@app.route('/search', methods=['GET'])
def search():
    search_type = request.args.get('search_type')
    query = request.args.get('query')
    if search_type is None or query is None:
        return redirect(url_for('index'))
    if search_type == "username" or search_type == "userid":
        return redirect(url_for('users', search_type=search_type, query=query))
    elif search_type == "beatmapid":
        return redirect(url_for('beatmap', search_type=search_type, query=query))
    else:
        flash('Invalid search type')
        return redirect(url_for('index'))


@app.route('/users', methods=['GET'])
def users():
    conn = sqlite3.connect('db/td_scores.db')
    cursor = conn.cursor()
    search_type = request.args.get('search_type')
    query = request.args.get('query')
    if search_type is None or query is None:
        return redirect(url_for('index', search_type='username'))

    user_scores = []
    if search_type == "username":
        if query.lower() not in username_lookup:
            flash('Selected user has no plays!')
            return redirect(url_for('index', search_type=search_type, query=query))
        user_scores = select_user(cursor, username=query)
    elif search_type == "userid":
        if not query.isdigit():
            flash('Please enter a positive integer for User ID!')
            return redirect(url_for('index', search_type=search_type, query=query))
        else:
            user_scores = select_user(cursor, userid=int(query))

    ret = []
    count = 1
    for score in user_scores:
        ret += [ScoreData(score, count)]
        count += 1
        if count > 100: break
    if len(ret) == 0:
        flash('Selected user has no plays!')
        return redirect(url_for('index', search_type=search_type, query=query))
    if ret[0].user_id in userdata:
        render_user = userdata[ret[0].user_id]
    else:
        render_user = [user_scores[0][-5], user_scores[0][3]]
    return render_template('results.html', results=ret, user_data=FullUser(render_user))


@app.route('/beatmap', methods=['GET'])
def beatmap():
    search_type = request.args.get('search_type')
    query = request.args.get('query')
    if search_type is None or query is None:
        return redirect(url_for('beatmap_search'))
    if not query.isdigit():
        flash('Please enter a positive integer for Beatmap ID!')
        return redirect(url_for('index', search_type='beatmapid'))
    query = int(query)
    map_scores = beatmap_scores(query)
    # replay_id, beatmap_id, score, username, count_300, count_100, count_50, count_miss,
    #            max_combo, perfect, mods, user_id, date, rank, pp, star_rating
    if map_scores == -1:
        flash('No information about this beatmap available')
        return redirect(url_for('index', search_type='beatmapid'))

    ret = []
    map_user_mod = set()
    count = 1
    i = 0
    while count <= 100 and i < len(map_scores):
        if (map_scores[i][1], map_scores[i][-5], map_scores[i][-6]) in map_user_mod:
            i += 1
            continue
        if map_scores[i][-5] in userdata:
            user = userdata[map_scores[i][-5]]
            country_name = user[7]
            base = int("1f1e6", 16) - ord('A')
            d1 = ord(user[8][0]) + base
            d2 = ord(user[8][1]) + base
            country_image = f"https://osu.ppy.sh/assets/images/flags/{hex(d1)[2::]}-{hex(d2)[2::]}.svg"
        else:
            country_name = "Unknown"
            country_image = "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/flags/fallback.png"

        ret += [(ScoreData(map_scores[i], count), country_name, country_image)]
        map_user_mod.add((map_scores[i][1], map_scores[i][-5], map_scores[i][-6]))
        i += 1
        count += 1

    if query in ranked:
        beatmap_data = ranked[query]
    elif query in loved:
        beatmap_data = loved[query]
    else:
        beatmap_data = ["Unknown"]*30

    current_beatmap = BeatmapData(beatmap_data)
    current_beatmapset = []
    if beatmap_data[0] == "Unknown":
        return render_template('beatmap.html', results=ret, map=current_beatmap, beatmapset=current_beatmapset)

    for beatmap in beatmapset_lookup[current_beatmap.beatmapset_id]:
        if beatmap[0] in ranked:
            current_beatmapset += [BeatmapData(ranked[beatmap[0]])]
        elif beatmap[0] in loved:
            current_beatmapset += [BeatmapData(loved[beatmap[0]])]

    return render_template('beatmap.html', results=ret, map=current_beatmap, beatmapset=current_beatmapset)


@app.route('/beatmap/search')
def beatmap_search():
    query = request.args.get('query')
    sortmode = request.args.get('sort')
    sortorder = request.args.get('order')
    if sortmode is None or sortorder is None:
        return redirect(url_for('beatmap_search', sort='ranked', order='desc'))

    sort = f"{sortmode} {request.args.get('order')}"
    ret = []
    search_start = time.time()
    beatmapset_ids = search_beatmaps(query, sort)
    print(f"Search time: {time.time() - search_start}")
    for beatmapset_id in beatmapset_ids:
        beatmapset = []
        for beatmap in beatmapset_lookup[beatmapset_id]:
            if beatmap[0] in ranked:
                beatmapset += [BeatmapData(ranked[beatmap[0]])]
            elif beatmap[0] in loved:
                beatmapset += [BeatmapData(loved[beatmap[0]])]
        ret += [beatmapset]
    return render_template('beatmap_search.html', results=ret)


@app.route('/leaderboard')
def leaderboard():
    return redirect(url_for('leaderboard_performance'))


@app.route('/leaderboard/performance', methods=['GET'])
def leaderboard_performance():
    global user_ranking, user_lookup
    rank = 1
    user_data = []
    for i in range(50):
        user_data += [UserData(user_ranking[i], user_lookup, rank)]
        rank += 1

    query = request.args.get('rank')
    search = request.args.get('search')

    if search is not None:
        if len(search) > 0:
            count = 0
            rank = 1
            user_data = []
            for user in user_ranking:
                if search.lower() in user_lookup[user[0]].lower():
                    user_data += [UserData(user, user_lookup, rank)]
                    count += 1
                rank += 1
                if count >= 50:
                    break
            return render_template('leaderboard_performance.html', data=user_data)

    if query is None:
        return render_template('leaderboard_performance.html', data=user_data)

    if not query.isdigit():
        flash('Please enter a positive integer!')
        return render_template('leaderboard_performance.html', data=user_data)

    query = int(query)
    if query > len(user_ranking):
        flash(f"There are only {len(user_ranking)} users on this leaderboard!")
        return render_template('leaderboard_performance.html', data=user_data)
    elif query <= 0:
        flash(f"Please enter a positive integer!")
        return render_template('leaderboard_performance.html', data=user_data)
    else:
        rank = query
        user_data = []
        for i in range(query-1, min(query+49, len(user_ranking))):
            user_data += [UserData(user_ranking[i], user_lookup, rank)]
            rank += 1
        return render_template('leaderboard_performance.html', data=user_data)


@app.route('/leaderboard/score', methods=['GET'])
def score_performance():
    global user_score_ranking, user_score_lookup
    rank = 1
    user_data = []
    for i in range(50):
        user_data += [UserData(user_score_ranking[i], user_score_lookup, rank)]
        rank += 1

    query = request.args.get('rank')
    search = request.args.get('search')

    if search is not None:
        if len(search) > 0:
            count = 0
            rank = 1
            user_data = []
            for user in user_ranking:
                if search.lower() in user_score_lookup[user[0]].lower():
                    user_data += [UserData(user, user_score_lookup, rank)]
                    count += 1
                rank += 1
                if count >= 50:
                    break
            return render_template('leaderboard_score.html', data=user_data)

    if query is None:
        return render_template('leaderboard_score.html', data=user_data)

    if not query.isdigit():
        flash('Please enter a positive integer!')
        return render_template('leaderboard_score.html', data=user_data)

    query = int(query)
    if query > len(user_ranking):
        flash(f"There are only {len(user_ranking)} users on this leaderboard!")
        return render_template('leaderboard_score.html', data=user_data)
    elif query <= 0:
        flash(f"Please enter a positive integer!")
        return render_template('leaderboard_score.html', data=user_data)
    else:
        rank = query
        user_data = []
        for i in range(query-1, min(query+49, len(user_ranking))):
            user_data += [UserData(user_ranking[i], user_lookup, rank)]
            rank += 1
        return render_template('leaderboard_score.html', data=user_data)


@app.route('/plays', methods=['GET'])
def plays():
    query = request.args.get('rank')
    if query is None:
        query = "1"
    elif not query.isdigit():
        flash('Please enter a positive integer!')
        query = "1"

    query = int(query)
    if query < 1:
        flash('Please enter a positive integer!')
        query = 1
    if query > len(top_scores):
        flash(f"There are only {len(top_scores)} scores on this leaderboard!")
        query = 1

    ret = []
    count = query
    for i in range(query-1, min(len(top_scores), query+49)):
        if top_scores[i][-5] in userdata:
            user = userdata[top_scores[i][-5]]
            country_name = user[7]
            base = int("1f1e6", 16) - ord('A')
            d1 = ord(user[8][0]) + base
            d2 = ord(user[8][1]) + base
            country_image = f"https://osu.ppy.sh/assets/images/flags/{hex(d1)[2::]}-{hex(d2)[2::]}.svg"
        else:
            country_name = "Unknown"
            country_image = "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/flags/fallback.png"
        ret += [(ScoreData(top_scores[i], count), country_name, country_image)]
        count += 1
    return render_template('plays.html', results=ret)


@app.route('/loved', methods=['GET'])
def loved():
    query = request.args.get('rank')
    if query is None:
        query = "1"
    elif not query.isdigit():
        flash('Please enter a positive integer!')
        query = "1"

    query = int(query)
    if query < 1:
        flash('Please enter a positive integer!')
        query = 1
    if query > len(top_scores_loved):
        flash(f"There are only {len(top_scores_loved)} scores on this leaderboard!")
        query = 1

    ret = []
    count = query
    for i in range(query-1, min(len(top_scores_loved), query+49)):
        if top_scores_loved[i][-5] in userdata:
            user = userdata[top_scores_loved[i][-5]]
            country_name = user[7]
            base = int("1f1e6", 16) - ord('A')
            d1 = ord(user[8][0]) + base
            d2 = ord(user[8][1]) + base
            country_image = f"https://osu.ppy.sh/assets/images/flags/{hex(d1)[2::]}-{hex(d2)[2::]}.svg"
        else:
            country_name = "Unknown"
            country_image = "https://raw.githubusercontent.com/ppy/osu-web/master/public/images/flags/fallback.png"
        ret += [(ScoreData(top_scores_loved[i], count), country_name, country_image)]
        count += 1
    return render_template('loved.html', results=ret)


@app.route(admin_path, methods=['GET', 'POST'])
def admin():
    global update_queue
    if request.method == 'POST':
        password_hash = request.form.get("password")
        if password_hash == admin_hash:
            session["authenticated"] = True
            return redirect(admin_path)
        else:
            flash("Incorrect password")
            return render_template("admin_login.html")
    elif request.method == 'GET':
        if not session.get("authenticated"):
            return render_template("admin_login.html")
        else:
            action = request.args.get("action")
            if action is None:
                return render_template("admin_panel.html")
            if action in ["reprocess_maps", "reprocess_users"]:
                update_queue.append((action, 0))
            else:
                flash("Invalid action requested")
                return render_template("admin_panel.html")
            flash(f"Successfully queued action {action}")
            return render_template("admin_panel.html")


@app.route('/update', methods=['GET'])
def update():
    global update_queue
    search_type = request.args.get('search_type')
    redirect_status = request.args.get('redirect_status')
    if search_type is None:
        return render_template('update.html')
    if redirect_status is not None:
        return render_template('update.html', search_type=search_type)

    if search_type == "scoreid":
        scoreid = request.args.get('query')
        if scoreid is None:
            flash('Please enter a valid Score ID!')
            return redirect(url_for('update', search_type=search_type, redirect_status="none"))
        if not scoreid.isdigit():
            flash('Please enter a valid Score ID!')
            return redirect(url_for('update', search_type=search_type, redirect_status="none"))
        scoreid = int(scoreid)
        status, response = insert_score(scoreid, ranked, loved)
        if status == -1:
            print(f"An error occurred: {response}")
            flash(f"An error occurred: {response}")
        else:
            flash(f"Successfully added score with ID {scoreid}")
        return redirect(url_for('update', search_type=search_type, redirect_status="none"))

    elif search_type == "beatmapid":
        beatmapid = request.args.get('query')
        if beatmapid is None:
            flash('Please enter a valid Beatmap ID!')
            return redirect(url_for('update', search_type=search_type, redirect_status="none"))
        if not beatmapid.isdigit():
            flash('Please enter a valid Beatmap ID!')
            return redirect(url_for('update', search_type=search_type, redirect_status="none"))
        beatmapid = int(beatmapid)
        status, response = check_beatmap(beatmapid)
        if status == -1:
            print(f"An error occurred: {response}")
            flash(f"An error occurred: {response}")
        else:
            update_queue.append(("beatmap", beatmapid, response))
            flash(f"Successfully queued beatmap with ID {beatmapid}")
        return redirect(url_for('update', search_type=search_type, redirect_status="none"))

    elif search_type == "userbest" or search_type == "userrecent":
        userid = request.args.get('query')
        if userid is None:
            flash('Please enter a valid User ID!')
            return redirect(url_for('update', search_type=search_type, redirect_status="none"))
        if not userid.isdigit():
            flash('Please enter a valid User ID!')
            return redirect(url_for('update', search_type=search_type, redirect_status="none"))
        userid = int(userid)
        status, response = check_user(userid)
        if status == -1:
            print(f"An error occurred: {response}")
            flash(f"An error occurred: {response}")
        else:
            update_queue.append((search_type, userid))
            flash(f"Successfully queued user with ID {userid}")
        return redirect(url_for('update', search_type=search_type, redirect_status="none"))

    elif search_type == "beatmapuser":
        beatmapid = request.args.get('beatmapid')
        userid = request.args.get('userid')
        query = (beatmapid, userid)
        if query[0] is None or query[1] is None:
            flash('Please enter a valid Beatmap ID and User ID!')
            return redirect(url_for('update', search_type=search_type, redirect_status="none"))
        if not query[0].isdigit() or not query[1].isdigit():
            flash('Please enter a valid Beatmap ID and User ID!')
            return redirect(url_for('update', search_type=search_type, redirect_status="none"))
        userid = int(userid)
        status, response = check_user(userid)
        if status == -1:
            print(f"An error occurred: {response}")
            flash(f"An error occurred: {response}")
            return redirect(url_for('update', search_type=search_type, redirect_status="none"))
        beatmapid = int(beatmapid)
        status, response = check_beatmap(beatmapid)
        if status == -1:
            print(f"An error occurred: {response}")
            flash(f"An error occurred: {response}")
            return redirect(url_for('update', search_type=search_type, redirect_status="none"))
        update_queue.append(("beatmapuser", beatmapid, userid, response))
        flash(f"Successfully queued user with ID {userid} on map with ID {beatmapid}")
        return redirect(url_for('update', search_type=search_type, redirect_status="none"))

    else:
        flash("Invalid search type")
        return redirect(url_for('update'))


# background updaters
def update_all():
    global update_all_timer
    update_top_scores()
    update_ranking()
    update_all_timer = threading.Timer(60.0, update_all)
    update_all_timer.daemon = True
    update_all_timer.start()


def update_top_scores():
    global top_scores, top_scores_loved
    top_scores = get_pp("ranked")
    top_scores_loved = get_pp("loved")


def update_ranking():
    global user_ranking, user_lookup, user_ranking_lookup, user_score_ranking, user_score_lookup, user_score_ranking_lookup
    user_ranking, user_lookup, user_ranking_lookup = pp_ranking()
    user_score_ranking, user_score_lookup, user_score_ranking_lookup = score_ranking()


def process_queue():
    global update_queue, ranked, loved, userdata
    schedule.run_pending()
    if len(update_queue) > 0:
        request_start = time.time()
        update_request = update_queue[0]
        print(f"Started processing request: {update_request}")
        if update_request[0] == "beatmap":
            beatmap_id = update_request[1]
            rankstatus = update_request[2]
            if rankstatus == "ranked" and beatmap_id not in ranked:
                status, response = update_ranked(beatmap_id)
                ranked = load_maps("ranked")
                if status == 1:
                    status, response = insert_beatmap(beatmap_id, ranked, loved)
            elif rankstatus == "loved" and beatmap_id not in loved:
                status, response = -1, f"Unknown loved map requested: {beatmap_id}"
            else:
                status, response = insert_beatmap(beatmap_id, ranked, loved)
            if status == -1:
                print(f"An error occurred: {response}")

        elif update_request[0] == "userbest":
            user_id = update_request[1]
            if user_id not in userdata:
                status, response = insert_user(user_id)
                load_users()
            status, response = insert_user_scores(user_id)
            if status == -1:
                print(f"An error occurred: {response}")

        elif update_request[0] == "userrecent":
            user_id = update_request[1]
            if user_id not in userdata:
                status, response = insert_user(user_id)
                load_users()
            status, response = insert_user_recent(user_id)
            if status == -1:
                print(f"An error occurred: {response}")

        elif update_request[0] == "beatmapuser":
            beatmap_id = update_request[1]
            user_id = update_request[2]
            if user_id not in userdata:
                status, response = insert_user(user_id)
                load_users()
            rankstatus = update_request[3]
            if rankstatus == "ranked" and beatmap_id not in ranked:
                status, response = update_ranked(beatmap_id)
                ranked = load_maps("ranked")
                if status == 1:
                    status, response = insert_beatmap_user(beatmap_id, user_id, rankstatus, userdata[user_id][1], loved)
            elif rankstatus == "loved" and beatmap_id not in loved:
                status, response = -1, f"Unknown loved map requested: {beatmap_id}"
            else:
                status, response = insert_beatmap_user(beatmap_id, user_id, rankstatus, userdata[user_id][1], loved)
            if status == -1:
                print(f"An error occurred: {response}")

        elif update_request[0] == "reprocess_maps":
            reprocess_maps()
            ranked = load_maps("ranked")
            loved = load_maps("loved")

        elif update_request[0] == "reprocess_users":
            limit = update_request[1]
            while not update_all_timer.is_alive():
                time.sleep(1)
            update_all_timer.cancel()
            if limit == 0:
                limit = 1000 # hardcoded temp limit
            for i in range(limit):
                print(f"Updating user {user_ranking[i][0]:<10} (rank {i+1})")
                try:
                    insert_user_scores(user_ranking[i][0])
                    insert_user_recent(user_ranking[i][0])
                except Exception as e:
                    print(f"An error occurred: {e}")
            update_all()

        else:
            print(f"Invalid request type: {update_request}")

        print(f"Finished processing request: {update_request}")
        print(f"Request time: {time.time() - request_start}")
        update_queue.pop(0)

    timer = threading.Timer(1.0, process_queue)
    timer.daemon = True
    timer.start()


def daily_update():
    update_queue.append(("reprocess_users", 500))
    update_queue.append(("reprocess_maps", 0))


if __name__ == '__main__':
    # osu api connection
    api = Ossapi(config['apiv2_id'], config['apiv2_key'])
    apiv1 = OssapiV1(config['apiv1'])
    admin_hash = hashlib.sha256(config['admin'].encode()).hexdigest()

    beatmapset_lookup = {}
    ranked = load_maps("ranked")
    loved = load_maps("loved")
    print("maps loaded")

    userdata = load_users()
    print("userdata loaded")

    user_ranking, user_lookup, user_ranking_lookup, user_score_ranking, user_score_lookup, user_score_ranking_lookup = [None] * 6
    top_scores, top_scores_loved = [None] * 2
    update_all_timer = None
    update_all()
    print("ranking and scores loaded")

    update_queue = []
    process_queue()
    schedule.every().day.at("05:00").do(daily_update)
    app.run(port=8080)
