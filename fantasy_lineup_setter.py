from datetime import date, timedelta, datetime as dt
import pytz
from collections import Counter
import requests
import shutil

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa


class NHLScraper():
    def __init__(self):
        self.url_prefix = "https://statsapi.web.nhl.com/api/v1/"
        self._teams = {}

        standings = requests.get(self.url_prefix + 'standings').json()
        N_DIVISIONS = 4
        for div in range(N_DIVISIONS):
            div_records = requests.get(self.url_prefix + 'standings').json()['records'][div]['teamRecords']
            for record in div_records:
                self._teams[record['team']['id']] = record['team']

    def get_next_game_by_team(self, start_dt):
        '''
        :returns: dictionary mapping team full name to list of upcoming team dates within start_dt and end_dt
        '''
        start_dt = start_dt.strftime("%Y-%m-%d")

        # Get upcoming dates by team
        team_dates = {
            team_id: requests.get(
                self.url_prefix
                + "schedule?teamId="
                + str(team_id)
                + "&startDate=" + start_dt
                + "&endDate=2022-04-30"
            ).json()["dates"]
            for team_id in self._teams
        }

        team_game = {}

        for team_id, dates in team_dates.items():
            name = self._teams[team_id]["name"]

            if dates and dates[0]["totalGames"] and dates[0]["date"] == start_dt:
                team_game[name] = dates[0]["games"][0]
            else:
                team_game[name] = None

        return team_game


def set_lineup_handler(event, context):
    shutil.copy('oauth_key.json', '/tmp') # move file to writable directory as it will get updated

    oauth = OAuth2(None, None, from_file='/tmp/oauth_key.json')
    if not oauth.token_is_valid():
        oauth.refresh_access_token()

    day = dt.now(pytz.timezone('US/Eastern')).date()
    print("Attempting roster update for", day)

    gm = yfa.Game(oauth, 'nhl')
    lg_key = gm.league_ids(year=2021)[0]
    lg = gm.to_league(lg_key)
    my_tm_key = lg.team_key()
    tm = lg.to_team(my_tm_key)

    #######################
    #%% Get player info %%#
    #######################
    roster = tm.roster(day=day)
    # {'player_id': 6750, 'name': 'Zach Werenski', 'status': 'O', 'position_type': 'P', 'eligible_positions': ['D', 'Util', 'IR+'], 'selected_position': 'D'}

    ids = [player["player_id"] for player in roster]

    details = lg.player_details(ids)
    # {'player_key': '411.p.7498', 'player_id': '7498', 'name': {'full': 'Neal Pionk', 'first': 'Neal', 'last': 'Pionk', 'ascii_first': 'Neal', 'ascii_last': 'Pionk'}, 'editorial_player_key': 'nhl.p.7498', 'editorial_team_key': 'nhl.t.28', 'editorial_team_full_name': 'Winnipeg Jets', 'editorial_team_abbr': 'Wpg', 'uniform_number': '4', 'display_position': 'D', 'headshot': {'url': 'https://s.yimg.com/iu/api/res/1.2/jmjeGpIUuWkVWJj7b23kyA--~C/YXBwaWQ9eXNwb3J0cztjaD0yMzM2O2NyPTE7Y3c9MTc5MDtkeD04NTc7ZHk9MDtmaT11bGNyb3A7aD02MDtxPTEwMDt3PTQ2/https://s.yimg.com/xe/i/us/sp/v/nhl_cutout/players_l/11162021/7498.png', 'size': 'small'}, 'image_url': 'https://s.yimg.com/iu/api/res/1.2/jmjeGpIUuWkVWJj7b23kyA--~C/YXBwaWQ9eXNwb3J0cztjaD0yMzM2O2NyPTE7Y3c9MTc5MDtkeD04NTc7ZHk9MDtmaT11bGNyb3A7aD02MDtxPTEwMDt3PTQ2/https://s.yimg.com/xe/i/us/sp/v/nhl_cutout/players_l/11162021/7498.png', 'is_undroppable': '0', 'position_type': 'P', 'primary_position': 'D', 'eligible_positions': [{'position': 'D'}, {'position': 'Util'}], 'player_stats': {'0': {'coverage_type': 'season', 'season': '2021'}, 'stats': [{'stat': {'stat_id': '1', 'value': '2'}}, {'stat': {'stat_id': '2', 'value': '22'}}, {'stat': {'stat_id': '4', 'value': '5'}}, {'stat': {'stat_id': '8', 'value': '9'}}, {'stat': {'stat_id': '11', 'value': '0'}}, {'stat': {'stat_id': '14', 'value': '97'}}, {'stat': {'stat_id': '31', 'value': '122'}}, {'stat': {'stat_id': '32', 'value': '62'}}]}

    # Overwrite roster info with detailed player info
    players = {
        r["player_id"]: {**r, **d}
        for r, d in zip(roster, details)
    }

    #####################
    #%% Get team info %%#
    #####################
    nhl = NHLScraper()
    team_game = nhl.get_next_game_by_team(start_dt=day)

    ######################################
    #%% See which players can be moved %%#
    ######################################
    # TODO improve starting players algorithm
    STARTING_SLOTS = Counter({pos: posinfo['count'] for pos, posinfo in lg.positions().items() if posinfo['is_starting_position']})
    starters = {}
    startables = {}
    benchables = {}

    for pid, player in players.items():
        player["tonights_game"] = team_game[player["editorial_team_full_name"]]
        if player["tonights_game"] and player["selected_position"] in STARTING_SLOTS:
            starters[pid] = player
        elif player["tonights_game"] and player["selected_position"] == "BN":
            startables[pid] = player
        elif not player["tonights_game"] and player["selected_position"] in STARTING_SLOTS:
            benchables[pid] = player

    print("Starters", [p["name"]["full"] for p in starters.values()])
    print("Startables", [p["name"]["full"] for p in startables.values()])
    print("Benchables", [p["name"]["full"] for p in benchables.values()])

    ##########################
    #%% Submit API request %%#
    ##########################
    available_ct = STARTING_SLOTS - Counter(starter["selected_position"] for starter in starters.values())

    new_positions = []
    for sid, startable in startables.items():
        # available starting position for the player
        eligible_pos = Counter([posdict["position"] for posdict in startable["eligible_positions"]])

        try:
            new_pos = next((eligible_pos & available_ct).elements())
            new_positions.append({
                "player_id": sid,
                "selected_position": new_pos
            })
            available_ct.subtract(new_pos)
            bid, benchable = benchables.popitem()
            new_positions.append({
                "player_id": bid,
                "selected_position": "BN"
            })
        except StopIteration:
            pass

    if new_positions:
        tm.change_positions(day, new_positions)
        print("Update Succeeded!")
        for row in new_positions:
            print(f"Moved {players[row['player_id']]['name']['full']} to {row['selected_position']}")
    else:
        print("No Changes Needed!")

