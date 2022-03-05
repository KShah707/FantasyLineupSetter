from datetime import timedelta, datetime as dt
import dateutil.parser
import requests

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

    def get_games_by_team(self, start_dt):
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