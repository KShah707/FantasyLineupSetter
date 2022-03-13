from datetime import date, timedelta, datetime as dt
import pytz
from collections import Counter
import requests
import shutil
from itertools import chain

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa


class NHLScraper():
    def __init__(self):
        self.url_prefix = "https://statsapi.web.nhl.com/api/v1/"
        self._teams = {}

        standings = requests.get(self.url_prefix + 'standings').json()
        N_DIVISIONS = 4
        for div in range(N_DIVISIONS):
            div_records = standings['records'][div]['teamRecords']
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


class BacktrackingLineupSolver:
    def __init__(self, slots, players):
        self.slot_names = slots
        self.slot_pids = [None] * len(slots)
        self.players = players
        self.solutions = []

    def solve(self, slot_index):
        if slot_index == len(self.slot_names):
            # Reached the end, record our solution
            self.solutions.append(dict(zip(self.slot_pids, self.slot_names)))
            return

        atleast_one_player = False

        # For each active player,
        for pid, player in self.players.items():
            # If player can be put in this slot,
            if (
                pid not in self.slot_pids
                and self.slot_names[slot_index] in set(chain.from_iterable(d.values() for d in player["eligible_positions"]))
            ):
                # Put player in this slot and recurse on remaining slots
                atleast_one_player = True
                self.slot_pids[slot_index] = pid
                self.solve(slot_index + 1)

        # If no player will fit here, then skip slot and keep going
        if not atleast_one_player:
            self.slot_pids[slot_index] = None
            self.solve(slot_index + 1)

    def solve_lineup(self):
        self.solve(0)
        return self.solutions


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

    # #################################
    # #%% Generate possible lineups %%#
    # #################################
    STARTING_SLOTS = Counter({pos: posinfo['count'] for pos, posinfo in lg.positions().items() if posinfo['is_starting_position']})

    actives = {}
    inactives = {}
    for pid, player in players.items():
        player["tonights_game"] = team_game[player["editorial_team_full_name"]]
        if player["tonights_game"] and (player["selected_position"] in STARTING_SLOTS or player["selected_position"] == "BN"):
            actives[pid] = player
        elif not player["tonights_game"] and (player["selected_position"] in STARTING_SLOTS or player["selected_position"] == "BN"):
            inactives[pid] = player

    slot_names = list(STARTING_SLOTS.elements())
    lineup_solver = BacktrackingLineupSolver(slot_names, actives)
    solutions = lineup_solver.solve_lineup()

    #################################
    #%% Pick best possible lineup %%#
    #################################
    solution = solutions[0]

    ##########################
    #%% Submit API request %%#
    ##########################
    new_positions = []

    for pid, pos in solution.items():
        if pid:
            new_positions.append({
                "player_id": pid,
                "selected_position": pos
            })
    for pid, player in inactives.items():
        new_positions.append({
            "player_id": pid,
            "selected_position": "BN"
        })

    print("Attempting to set the following lineup:")
    for row in new_positions:
        print(f"{row['selected_position']}: {players[row['player_id']]['name']['full']}")
    tm.change_positions(day, new_positions)
    print("Update Succeeded!")

if __name__ == '__main__':
    set_lineup_handler(None, None)

