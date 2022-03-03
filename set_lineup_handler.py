from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa
from datetime import date

oauth = OAuth2(None, None, from_file='oauth_key.json')
if not oauth.token_is_valid():
    oauth.refresh_access_token()

gm = yfa.Game(oauth, 'nhl')
lg_key = gm.league_ids(year=2021)[0] #FIXME assert len 1, only 1 league
lg = gm.to_league(lg_key) #FIXME today's year
my_tm_key = lg.team_key()
tm = lg.to_team(my_tm_key)

roster = tm.roster()
# sample entry:
# {'player_id': 6750, 'name': 'Zach Werenski', 'status': 'O', 'position_type': 'P', 'eligible_positions': ['D', 'Util', 'IR+'], 'selected_position': 'D'}
tm.change_positions(date.today(), [
	{'player_id': 5983, 'selected_position': 'BN'}
])


# TODOs
# Clean up directory structure with other files (REMOVE SECRETS!)
# Commit to git
# Write terraform/ansible to deploy lambda in designated acct
#  - may need to set up config file with acct details
# https://github.com/YPlan/ansible-python-lambda
# Fix starting lineup logic:
#  - no empty roster spots from bench (choose randomly)
#  - stash IR players if poss (choose randomly)
#  - if time, start to improve logic