#!/usr/bin/env python

##### Libraries

import json
import numpy as np
import os
import pandas as pd
import re

##### Setup

# Paths.
config_dir_path = '../../../config/'
data_dir_path = '../../../data/'
summary_dir_path = data_dir_path+'kenpom_summaries/'
snapshots_path = data_dir_path+'team_snapshots.json'
games_output_path = data_dir_path+'games.csv'

##### Main Execution

### KenPom

# Assemble KenPom data.
kenpom = None
kenpom_files = os.listdir(summary_dir_path)
# Traverse all files.
for kp_filename in kenpom_files:
	# Ignore non-final scores. Maybe we'll do something with these later.
	if not re.match(r'summary\d{2}.csv',kp_filename):
		continue
	# Get year.
	kp_year = int('20'+kp_filename[7:9])
	# Get data.
	kp_data = pd.read_csv(summary_dir_path+kp_filename)
	# Add year
	kp_data['year'] = kp_year
	# Save.
	if kenpom is None:
		kenpom = kp_data
	else:
		kenpom = kenpom.append(kp_data)

### Snapshots, Join

# Load snapshot data.
snapshots_dict = json.load(open(snapshots_path))

# Container for features.
game_features = None

# Traverse snapshots.
for snap in snapshots_dict:
	# Get snapshot games.
	snap_games = pd.DataFrame(snap['games'])
	# Append team, year.
	snap_games['team'] = snap['team']
	snap_games['year'] = snap['year']
	# Join team information; prefix KenPom columns.
	snap_games = snap_games.merge(kenpom, left_on=['team','year'], right_on=['TeamName','year'])
	snap_games.drop('TeamName', axis=1, inplace=True)
	snap_games.columns = ['team_'+c if (c in kenpom.columns and c != 'year') else c for c in snap_games.columns]
	# Join opponent information; prefix KenPom columns.
	snap_games = snap_games.merge(kenpom, left_on=['opponent','year'], right_on=['TeamName','year'])
	snap_games.drop('TeamName', axis=1, inplace=True)
	snap_games.columns = ['opponent_'+c if (c in kenpom.columns and c != 'year') else c for c in snap_games.columns]
	if game_features is None:
		game_features = snap_games
	else:
		game_features = game_features.append(snap_games)

### Game IDs

# Get all date strings.
g_dates = np.array(game_features.date, dtype=np.str)
g_dates = np.core.defchararray.replace(g_dates,'-','')

# Get team combinations and sort along second axis (default).
g_team_combos = np.array([
		list(game_features.team.str.lower().str.replace(r'[^a-z0-9]', '')),
		list(game_features.opponent.str.lower().str.replace(r'[^a-z0-9]', ''))
	]).T
g_team_combos.sort()

# Join all ID components together and save as game ID.
game_features['game_id'] = np.core.defchararray.add(g_dates,
			np.core.defchararray.add('-',
				np.core.defchararray.add(g_team_combos[:,0],
					np.core.defchararray.add('-',g_team_combos[:,1])
				)
			)
		)

# Sort on game ID. Ensures all games are paired and entire dataset sorted by year.
game_features.sort('game_id', inplace=True)
game_features.reset_index(drop=True, inplace=True)

# Now generate random 0s and 1s to identify delineations. Every two observations will sum to 1 and be 1 or 0.
game_group_1_indices = np.array([np.random.choice(2,replace=False,size=2) for _ in xrange(game_features.shape[0]/2)]).ravel()
# Set in DF.
game_features['game_group'] = game_group_1_indices

### Cleanup

# Integerize dummy variables.
for c, dt in zip(game_features.columns,game_features.dtypes):
	if dt == 'bool':
		game_features[c] = game_features[c].astype(np.int)

# Get location dummies.
location_dummies = pd.get_dummies(game_features.location, prefix='location').astype(np.int)
# Clean up.
location_dummies.columns = [re.sub('[^a-zA-Z\\_]','',c) for c in location_dummies.columns]

# Append location dummies to right.
game_features = pd.concat((game_features, location_dummies), axis=1)

# Reorder columns.
# Store main column list.
main_game_columns = [
		'game_id','game_group','year','date','team','opponent',
		'conference','conference_tournament','ncaa_tournament','other_tournament'
	]
outcome_columns = ['points_for','points_against','win']
# Add other columns.
kp_columns = [c for c in game_features.columns if c.startswith('team_') or c.startswith('opponent_')]

# Reorder columns.
game_features = game_features[main_game_columns+list(location_dummies.columns)+kp_columns+outcome_columns]

# Save.
game_features.to_csv(games_output_path, index=False)
