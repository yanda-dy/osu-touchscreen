import sqlite3, time, json, threading, os
from datetime import datetime, timedelta, timezone
from ossapi import Ossapi, OssapiV1, Mod, GameMode
from rosu_pp_py import Beatmap, Calculator


class TimeoutException(Exception):
    pass


def timeout_handler():
    raise TimeoutException("Function execution timed out")


def api_setup():
    global api, apiv1
    with open('config.json') as config_file:
        config = json.load(config_file)
    api = Ossapi(9769, config['apiv2'])
    apiv1 = OssapiV1(config['apiv1'])


def find_beatmap(beatmapset_id, diff_name):
    main_folder_name = "C:/Users/yanda/AppData/Local/osu!/Songs/"
    main_folder = os.listdir(main_folder_name)
    diff_name = f"[{diff_name}]"
    for folder_name in main_folder:
        if folder_name.split()[0] == str(beatmapset_id):
            folder_path = os.path.join(main_folder_name, folder_name)
            for file_name in os.listdir(folder_path):
                if file_name.endswith(".osu") and diff_name in file_name.lower():
                    return os.path.join(folder_path, file_name)

    return "0"


def check_beatmap(beatmapid):
    api_setup()
    try:
        beatmap = api.beatmap(beatmap_id=beatmapid)
    except Exception as e:
        return -1, "API request failed"
    if str(beatmap.status) not in ["RankStatus.APPROVED", "RankStatus.RANKED", "RankStatus.LOVED"]:
        return -1, f"Beatmap is {str(beatmap.status).split('.')[-1].lower()}"
    rankstatus = "ranked" if str(beatmap.status) in ["RankStatus.APPROVED", "RankStatus.RANKED"] else "loved"
    return 1, rankstatus


def check_user(userid):
    api_setup()
    try:
        print(userid)
        user = api.user(user=userid, key="id")
    except Exception as e:
        print(str(e))
        return -1, "API request failed"
    return 1, "success"


def update_ranked(beatmapid):
    api_setup()
    try:
        beatmapset = api.beatmapset(beatmap_id=beatmapid)
        total_playcount = 0
        max_sr = -1
        min_sr = 1000000000
        for beatmap in beatmapset.beatmaps:
            total_playcount += beatmap.playcount
            max_sr = max(max_sr, beatmap.difficulty_rating)
            min_sr = min(min_sr, beatmap.difficulty_rating)
        for beatmap in beatmapset.beatmaps:
            if beatmap.mode == GameMode.OSU:
                if str(beatmap.status) in ["RankStatus.RANKED", "RankStatus.APPROVED"]:
                    data = [(beatmap.id, str(beatmap.mode), str(beatmap.status), beatmap.difficulty_rating, beatmap.max_combo, beatmap.total_length, beatmap.hit_length, beatmap.bpm, beatmap.cs, beatmap.ar, beatmap.accuracy, beatmap.drain, beatmap.count_circles, beatmap.count_sliders, beatmap.count_spinners, beatmap.passcount, beatmap.playcount, str(beatmap.last_updated), beatmap.user_id, beatmapset.id, str(beatmapset.artist), str(beatmapset.creator), str(beatmapset.title), str(beatmap.version), total_playcount, max_sr, min_sr, str(beatmapset.ranked_date))]
                    insert_map("ranked", data)
    except Exception as e:
        return -1, str(e)
    return 1, "success"


def sql_insert_query(data, rankstatus):
    if len(data) == 0:
        return 1, "no data"
    table = ""
    if rankstatus == "ranked":
        conn = sqlite3.connect('db/td_scores.db')
        cursor = conn.cursor()
        table = "td_scores"
    elif rankstatus == "loved":
        conn = sqlite3.connect('db/td_scores-loved.db')
        cursor = conn.cursor()
        table = "td_scores_loved"
    else:
        return -1, "invalid status"
    # Insert a row of data into the td_scores table
    query = f'''
    INSERT OR REPLACE INTO {table} (
        replay_id, beatmap_id, score, username, count_300, count_100, count_50, count_miss,
        max_combo, perfect, mods, user_id, date, rank, pp, star_rating
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    try:
        cursor.executemany(query, data)
    except Exception as e:
        return -1, f"SQL error: {str(e)}"

    # Commit the changes and close the connection
    conn.commit()
    conn.close()
    return 1, "success"


def insert_score(scoreid, ranked, loved):
    api_setup()
    try:
        score = api.score(mode="osu", score_id=scoreid)
    except Exception as e:
        return -1, "API request failed"
    if (score.mods.value >> 2) & 1 != 1:
        return -1, "not a TD score"
    star_rating = api.beatmap_attributes(score.beatmap.id, mods=score.mods.value).attributes.star_rating
    data = [(score.id, score.beatmap.id, score.score, score.user().username, score.statistics.count_300,
             score.statistics.count_100, score.statistics.count_50, score.statistics.count_miss, score.max_combo,
             int(score.perfect), score.mods.value, score.user_id, str(score.created_at), str(score.rank.value),
             score.pp, star_rating)]
    if score.beatmap.id in ranked:
        status, message = sql_insert_query(data, "ranked")
        return status, message
    elif score.beatmap.id in loved:
        status, message = sql_insert_query(data, "loved")
        return status, message
    else:
        return -1, "beatmap not found (not implemented yet)"


def insert_beatmap_helper(beatmap_id, mod, star_rating, rankstatus):
    timer = threading.Timer(60, timeout_handler)
    try:
        timer.start()
        scores = apiv1.get_scores(beatmap_id, mods=mod, limit=100)
    except TimeoutException:
        return -1, "Error fetching scores: timeout (60s)"
    except Exception as e:
        return -1, f"Error fetching scores: {str(e)}"
    finally:
        timer.cancel()
    data = []
    for score in scores:
        # ensure score contains TD mod
        if (score.mods.value >> 2) & 1 == 1:
            if mod == -1:
                star_rating = api.beatmap_attributes(beatmap_id, mods=score.mods.value).attributes.star_rating
            data += [(score.replay_id, beatmap_id, score.score, score.username, score.count_300, score.count_100,
                      score.count_50, score.count_miss, score.max_combo, int(score.perfect), score.mods.value,
                      score.user_id, str(score.date), str(score.rank), score.pp, star_rating)]
    if len(data) > 0:
        return sql_insert_query(data, rankstatus)
    else:
        return 1, "success (no td scores found)"


def insert_beatmap(beatmapid, ranked, loved):
    api_setup()
    if beatmapid in ranked:
        mods = [Mod("TD").value, Mod("TDHD").value, Mod("TDHR").value, Mod("TDHDHR").value, Mod("TDDT").value,
                Mod("TDNC").value, Mod("TDHDDT").value, Mod("TDHDNC").value, Mod("NFTD").value, -1]
        for mod in mods:
            sr = 0 if mod == -1 else api.beatmap_attributes(beatmapid, mods=mod).attributes.star_rating
            status, response = insert_beatmap_helper(beatmapid, mod, sr, "ranked")
            if status == -1:
                return status, response
        return 1, "success"
    elif beatmapid in loved:
        mods = [Mod("TD").value, Mod("TDHD").value, Mod("TDHR").value, Mod("TDHDHR").value, Mod("EZTD").value,
                Mod("TDDT").value, Mod("TDHDDT").value, Mod("NFTD").value, Mod("TDHT").value, -1]
        for mod in mods:
            sr = 0 if mod == -1 else api.beatmap_attributes(beatmapid, mods=mod).attributes.star_rating
            status, response = insert_beatmap_helper(beatmapid, mod, sr, "loved")
            if status == -1:
                return status, response
        return 1, "success"
    return -1, "beatmap not found"


def insert_user_scores(userid):
    api_setup()
    scores = apiv1.get_user_best(userid, mode="osu", limit=100, user_type="id")
    conn = sqlite3.connect('db/users.db')
    cursor = conn.cursor()
    query = f"SELECT username FROM users WHERE user_id = {userid}"
    cursor.execute(query)
    username = cursor.fetchall()[0][0]
    conn.close()
    data = []
    for score in scores:
        # ensure score is not already processed
        conn = sqlite3.connect('db/td_scores.db')
        cursor = conn.cursor()
        query = f"SELECT replay_id FROM td_scores WHERE replay_id = {score.replay_id}"
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()

        if len(rows) == 0:
            # ensure score contains TD mod
            if (score.mods.value >> 2) & 1 == 1:
                star_rating = api.beatmap_attributes(score.beatmap_id, mods=score.mods.value).attributes.star_rating
                data += [(score.replay_id, score.beatmap_id, score.score, username, score.count_300, score.count_100,
                          score.count_50, score.count_miss, score.max_combo, int(score.perfect), score.mods.value,
                          score.user_id, str(score.date), str(score.rank), score.pp, star_rating)]
    if len(data) > 0:
        return sql_insert_query(data, "ranked")
    else:
        return 1, "success (no td scores found)"


def insert_user_recent(userid):
    api_setup()
    scores = api.user_scores(user_id=userid, type="recent", mode="osu", include_fails=False, limit=100)
    ranked_data = []
    loved_data = []
    characters = ["\"", "|", "*", "<", ">", ":", "?", "/", "â", "€", "¡"]
    translation_table = str.maketrans('', '', ''.join(characters))
    rankstatus_dict = {"RankStatus.RANKED": "ranked", "RankStatus.APPROVED": "ranked", "RankStatus.LOVED": "loved"}
    for score in scores:
        if str(score.beatmap.status) in rankstatus_dict:
            if score.mode == GameMode.OSU and (score.mods.value >> 2) & 1 == 1:
                beatmapid = score.beatmap.id
                rankstatus = rankstatus_dict[str(score.beatmap.status)]
                if rankstatus == "loved":
                    diffname = score.beatmap.version
                    beatmapsetid = score.beatmapset.id
                    map_name = diffname.translate(translation_table).lower()
                    map_path = find_beatmap(beatmapsetid, map_name)
                    if map_path == "0":
                        print(f"Map with id {beatmapsetid} not found locally")
                        continue
                elif rankstatus == "ranked" and score.pp is None:
                    continue
                star_rating = api.beatmap_attributes(beatmapid, mods=score.mods.value).attributes.star_rating
                score_pp = 0 if score.pp is None else score.pp
                if rankstatus == "loved":
                    beatmap = Beatmap(path=map_path)
                    calc = Calculator(mods=score.mods.value)
                    max_perf = calc.performance(beatmap)
                    calc.set_n100(score.statistics.count_100)
                    calc.set_n50(score.statistics.count_50)
                    calc.set_n_misses(score.statistics.count_miss)
                    calc.set_combo(score.max_combo)
                    calc.set_difficulty(max_perf.difficulty)
                    curr_perf = calc.performance(beatmap)
                    score_pp = curr_perf.pp
                data = (score.id, beatmapid, score.score, score.user().username, score.statistics.count_300,
                          score.statistics.count_100, score.statistics.count_50, score.statistics.count_miss,
                          score.max_combo, int(score.perfect), score.mods.value, score.user_id, str(score.created_at),
                          str(score.rank.value), score_pp, star_rating)
                if rankstatus == "ranked":
                    ranked_data += [data]
                elif rankstatus == "loved":
                    loved_data += [data]
    status_ranked, message_ranked = sql_insert_query(ranked_data, "ranked")
    status_loved, message_loved = sql_insert_query(loved_data, "loved")
    message = []
    if status_ranked == -1:
        message.append(message_ranked)
    if status_loved == -1:
        message.append(message_loved)
    return min(status_ranked, status_loved), ' '.join(message)


def insert_beatmap_user(beatmapid, userid, rankstatus, username, loved):
    api_setup()
    scores = api.beatmap_user_scores(beatmap_id=beatmapid, user_id=userid, mode=GameMode.OSU)
    data = []
    characters = ["\"", "|", "*", "<", ">", ":", "?", "/", "â", "€", "¡"]
    translation_table = str.maketrans('', '', ''.join(characters))
    if rankstatus == "loved":
        diffname = loved[beatmapid][23]
        beatmapsetid = loved[beatmapid][19]
        map_name = diffname.translate(translation_table).lower()
        map_path = find_beatmap(beatmapsetid, map_name)
        if map_path == "0":
            return -1, f"Map not found: {beatmapsetid}"

    for score in scores:
        # ensure score contains TD mod
        if (score.mods.value >> 2) & 1 == 1:
            star_rating = api.beatmap_attributes(beatmapid, mods=score.mods.value).attributes.star_rating
            score_pp = 0 if score.pp is None else score.pp

            if rankstatus == "loved":
                beatmap = Beatmap(path=map_path)
                calc = Calculator(mods=score.mods.value)
                max_perf = calc.performance(beatmap)
                calc.set_n100(score.statistics.count_100)
                calc.set_n50(score.statistics.count_50)
                calc.set_n_misses(score.statistics.count_miss)
                calc.set_combo(score.max_combo)
                calc.set_difficulty(max_perf.difficulty)
                curr_perf = calc.performance(beatmap)
                score_pp = curr_perf.pp

            data += [(score.id, beatmapid, score.score, username, score.statistics.count_300,
                      score.statistics.count_100, score.statistics.count_50, score.statistics.count_miss,
                      score.max_combo, int(score.perfect), score.mods.value, score.user_id, str(score.created_at),
                      str(score.rank.value), score_pp, star_rating)]
    if len(data) > 0:
        return sql_insert_query(data, rankstatus)
    else:
        return 1, "success (no td scores found)"


def insert_map(status, data):
    path = "db/maps.db"
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    # Insert a row of data into the td_scores_loved table
    query = f'''
    INSERT OR REPLACE INTO {status}_maps (
        beatmap_id, mode, status, star_rating, max_combo, total_length, hit_length, bpm, cs, ar, od, hp, circles, sliders, spinners, passcount, playcount, last_updated, user_id, beatmapset_id, artist, creator, title, version, total_playcount, max_star_rating, min_star_rating, ranked_date, favourite_count, search_tags
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    cursor.executemany(query, data)

    # Commit the changes and close the connection
    conn.commit()
    conn.close()


def user_format(row):
    row = list(row)
    row[14] = int(row[14])
    row[15] = str(row[15])
    row[16] = json.dumps([row[1]] + row[16])
    row[17] = int(row[17])
    row[19] = str(row[19])
    row = tuple(row)
    return row


def insert_user(userid):
    api_setup()
    try:
        user = api.user(userid, key="id")
        data = (user.id, user.username, user.avatar_url, len(user.badges), len(user.user_achievements),
                user.statistics.replays_watched_by_others, user.beatmap_playcounts_count, user.country.name,
                user.country_code, user.cover_url, user.follower_count, user.loved_beatmapset_count,
                user.ranked_and_approved_beatmapset_count, user.guest_beatmapset_count, user.is_active,
                user.join_date, user.previous_usernames, user.has_supported, user.support_level, datetime.now())
        sql_insert_user(user_format(data))
    except Exception as e:
        return -1, str(e)
    return 1, "success"


def sql_insert_user(data):
    path = "db/users.db"
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    # Insert a row of data into the td_scores_loved table
    query = f'''
        INSERT OR REPLACE INTO users (
            user_id, username, avatar_url, badge_count, medal_count, replays_watched, playcount, country_name, country_code, cover_url, follower_count, loved_count, ranked_count, guest_count, is_active, join_date, previous_usernames, has_supported, support_level, last_updated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
    cursor.executemany(query, data)

    # Commit the changes and close the connection
    conn.commit()
    conn.close()


def purge_user(userid):
    api_setup()
    # assert user no longer exists
    try:
        api.user(userid, key="id")
        return "user found"
    except ValueError:
        conn = sqlite3.connect("db/td_scores.db")
        cursor = conn.cursor()
        query_select = "SELECT replay_id from td_scores WHERE user_id = ?"
        cursor.execute(query_select, (userid,))
        rows = cursor.fetchall()

        query_delete = "DELETE FROM td_scores WHERE user_id = ?"
        cursor.execute(query_delete, (userid,))
        query_select = "SELECT replay_id from td_scores WHERE user_id = ?"
        cursor.execute(query_select, (userid,))
        rows = cursor.fetchall()
        if len(rows) == 0:
            print(f"Successfully deleted scores with user_id {userid} from td_scores")
        else:
            print("Error: delete operation was not successful")
        conn.commit()
        conn.close()

        conn = sqlite3.connect("db/td_scores-loved.db")
        cursor = conn.cursor()
        query_delete = "DELETE FROM td_scores_loved WHERE user_id = ?"
        cursor.execute(query_delete, (userid,))
        query_select = "SELECT replay_id from td_scores_loved WHERE user_id = ?"
        cursor.execute(query_select, (userid,))
        rows = cursor.fetchall()
        if len(rows) == 0:
            print(f"Successfully deleted scores with user_id {userid} from td_scores_loved")
        else:
            print("Error: delete operation was not successful")
        conn.commit()
        conn.close()

        conn = sqlite3.connect("db/users.db")
        cursor = conn.cursor()
        query_delete = "DELETE FROM users WHERE user_id = ?"
        cursor.execute(query_delete, (userid,))
        query_select = "SELECT user_id from users WHERE user_id = ?"
        cursor.execute(query_select, (userid,))
        rows = cursor.fetchall()
        if len(rows) == 0:
            print(f"Successfully deleted user with user_id {userid} from users")
        else:
            print("Error: delete operation was not successful")
        conn.commit()
        conn.close()

        return f"Purged user {userid}"


if __name__ == '__main__':
    print("database_update.py")
