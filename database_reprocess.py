import sqlite3, json, time, shutil, os
from ossapi import Ossapi, OssapiV1, Cursor, GameMode
from datetime import datetime


def api_setup():
    global api, apiv1
    with open('config.json') as config_file:
        config = json.load(config_file)
    api = Ossapi(9769, config['apiv2'])
    apiv1 = OssapiV1(config['apiv1'])


def create_table_maps(sql_cursor):
    for status in ["ranked", "loved"]:
        sql_cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS {status}_maps (
                    beatmap_id INTEGER PRIMARY KEY UNIQUE,
                    mode TEXT,
                    status TEXT,
                    star_rating REAL,
                    max_combo INTEGER,
                    total_length INTEGER,
                    hit_length INTEGER,
                    bpm REAL,
                    cs REAL,
                    ar REAL,
                    od REAL,
                    hp REAL,
                    circles INTEGER,
                    sliders INTEGER,
                    spinners INTEGER,
                    passcount INTEGER,
                    playcount INTEGER,
                    last_updated TEXT,
                    user_id INTEGER,
                    beatmapset_id INTEGER,
                    artist TEXT,
                    creator TEXT,
                    title TEXT,
                    version TEXT,
                    total_playcount INTEGER,
                    max_star_rating REAL,
                    min_star_rating REAL,
                    ranked_date TEXT,
                    favourite_count INTEGER,
                    search_tags TEXT
                )
            ''')


def reprocess_maps():
    api_setup()
    conn = sqlite3.connect('db/maps.db')
    sql_cursor = conn.cursor()
    create_table_maps(sql_cursor)
    cursor = Cursor()
    processed = set()
    end_process = False
    ranked_data = []
    loved_data = []
    while True:
        search = api.search_beatmapsets(mode=0, category="leaderboard", explicit_content="show", sort="plays_desc", cursor=cursor)
        print(search.total, search.cursor, search.cursor_string)
        cursor = search.cursor
        for beatmapset in search.beatmapsets:
            total_playcount = 0
            max_sr = -1
            min_sr = 1000000000
            for beatmap in beatmapset.beatmaps:
                total_playcount += beatmap.playcount
                max_sr = max(max_sr, beatmap.difficulty_rating)
                min_sr = min(min_sr, beatmap.difficulty_rating)
            for beatmap in beatmapset.beatmaps:
                if beatmap.mode == GameMode.OSU and str(beatmap.status) in ["RankStatus.RANKED", "RankStatus.APPROVED", "RankStatus.LOVED"]:
                    if beatmap.id in processed:
                        end_process = True
                        break
                    processed.add(beatmap.id)
                    data = (beatmap.id, str(beatmap.mode), str(beatmap.status), beatmap.difficulty_rating,
                            beatmap.max_combo, beatmap.total_length, beatmap.hit_length, beatmap.bpm, beatmap.cs,
                            beatmap.ar, beatmap.accuracy, beatmap.drain, beatmap.count_circles, beatmap.count_sliders,
                            beatmap.count_spinners, beatmap.passcount, beatmap.playcount, str(beatmap.last_updated),
                            beatmap.user_id, beatmapset.id, str(beatmapset.artist), str(beatmapset.creator),
                            str(beatmapset.title), str(beatmap.version), total_playcount, max_sr, min_sr,
                            str(beatmapset.ranked_date), beatmapset.favourite_count,
                            f"{str(beatmapset.title)}―{str(beatmap.version)}―{str(beatmapset.artist)}―{str(beatmapset.creator)}―{str(beatmapset.id)}―{str(beatmap.id)}―{str(beatmapset.source)}―{str(beatmapset.tags)}")
                    if str(beatmap.status) in ["RankStatus.RANKED", "RankStatus.APPROVED"]:
                        ranked_data += [data]
                    elif str(beatmap.status) in ["RankStatus.LOVED"]:
                        loved_data += [data]

        time.sleep(0.1)
        if end_process:
            conn.executemany("INSERT OR REPLACE INTO ranked_maps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ranked_data)
            conn.executemany("INSERT OR REPLACE INTO loved_maps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", loved_data)
            conn.commit()
            conn.close()
            return


def save_backups():
    # Get the current date
    current_date = datetime.now().date()
    if not os.path.exists(f"backups/{current_date}"):
        os.makedirs(f"backups/{current_date}")

    # Create the backup filenames using the naming convention
    td_scores_backup_filename = f"backups/{current_date}/td_scores_backup_{current_date}.db"
    td_scores_loved_backup_filename = f"backups/{current_date}/td_scores-loved_backup_{current_date}.db"
    users_backup_filename = f"backups/{current_date}/users_backup_{current_date}.db"
    maps_backup_filename = f"backups/{current_date}/maps_backup_{current_date}.db"

    # Perform the backups by copying the files
    shutil.copyfile("db/td_scores.db", td_scores_backup_filename)
    shutil.copyfile("db/td_scores-loved.db", td_scores_loved_backup_filename)
    shutil.copyfile("db/users.db", users_backup_filename)
    shutil.copyfile("db/maps.db", maps_backup_filename)

    print(f"Backups created:")
    print(f"  - {td_scores_backup_filename}")
    print(f"  - {td_scores_loved_backup_filename}")
    print(f"  - {users_backup_filename}")
    print(f"  - {maps_backup_filename}")


if __name__ == '__main__':
    print("database_reprocess.py")
