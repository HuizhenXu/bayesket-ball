### Setup

# Libraries.
import bayes_lr
import numpy as np
import pandas as pd
import scipy as sp, scipy.stats

### Main Functionality

def logistic (s):
    """
    Sigmoid function. Just takes in a scalar and applies formula to it.
    """
    return 1 / (1+np.exp(-s))

def predict_games (data, features, model_mcmc=None, coefs=None, method='map'):
    """
    Inputs:
        data:       Dataframe with game data.
        features:   List of features in data dataframe.
        model_mcmc: PyMC MCMC object. Required if 'coefs' not supplied.
        coefs:      Numpy array of coefficients; each column corresponds to an element of 'features'. Required if 'model_mcmc' is not supplied.
        method:     'pp' for posterior predictive, 'map' for single estimate using MAP.
    Returns:
        Binary predictions for each game.
        Raw continuous predictions (in range [0,1]) for each game.
        Accuracy based on binary predictions (range [0,1]).
    """

    # Trace length.
    coef_samples = model_mcmc.trace('b_0')[:].shape[0] if coefs is None else len(coefs)
    
    # Get coefficients.
    if coefs is None:
        coefs = bayes_lr.feature_coefficients(model_mcmc, features)
    # Use MAP if we need to.
    if method == 'map' and coefs.shape[0] > 1:
        coefs = coefs.mean(axis=0).reshape((1,len(features)+1))
        coef_samples = 1
    
    # Get design matrix.
    X = np.concatenate((np.ones((len(data),1)), data[features]), axis=1)
    
    # Estimate wins. Start with a wins container.
    y_hat_raw = np.zeros((coef_samples,len(data)))
    # Traverse set of coefficients and assemble win estimates.
    for c_i, c in enumerate(coefs):
        y_hat_raw[c_i] = logistic((c.T*X).sum(axis=1))
    # Tag wins/losses with comparison.
    y_hat = (y_hat_raw >= .5).astype(np.int)
    
    # Compute accuracy by wins if they are available.
    y_hat_accuracy = None
    if 'win' in data:
        y_hat_accuracy = (np.array(data.win) == y_hat).mean()
    
    return y_hat_raw, y_hat, y_hat_accuracy

# Main function for simulating a tournament.
def simulate_tournament (bracket, team_stats, features, deterministic=False, model_mcmc=None, coef_trace=None):
    """
    Simulates a tournament, following all teams down the bracket to the championship.
    Inputs:
        bracket:       List of first round matchups. Should be first round of the tournament with the bracket "unrolled".
                       That is, the winner of game 1 will play the winner of game 2; 3 vs. 4; etc.
        team_stats:    Dataframe with team statistics.
        features:      List of features in data dataframe.
        deterministic: Declare the most likely winner as the winner if true; else use a Bernoulli trial to simulate each game.
        model_mcmc:    PyMC MCMC object. Trace length = simulations. Required if 'coef_trace' not supplied.
        coef_trace:    Numpy array of coefficients; each column corresponds to an element of 'features'. Trace length = simulations. Required if 'model_mcmc' is not supplied.
    Returns:
        Tournament outcomes as a data frame.
    """

    ### Setup

    # Get coefficients if we were not given them.
    if coef_trace is None:
        coef_trace = bayes_lr.feature_coefficients(model_mcmc, features)

    ### Simulations

    # Turn bracket into an array for easy manipulation.
    if type(bracket) == list:
        bracket = np.array(bracket)

    # Get sorted teams.
    teams = bracket.copy().ravel()
    teams.sort()
    # Use a numpy array to hold our outcomes.
    # Log base 2 works for determining how many rounds we have.
    round_outcomes = np.zeros((len(teams),int(np.log2(len(teams)))), dtype=np.int)

    # Create "team" DF by merging teams with statistics.
    teams_df = pd.DataFrame({'team':bracket.ravel()}).merge(team_stats, left_on='team', right_on='TeamName').drop(['TeamName'],axis=1)
    teams_df.columns = ['team_'+c if c in team_stats.columns else c for c in teams_df.columns]
    # teams_df = teams_df.reset_index().rename(columns={'index':'bracket_order'})
    # Reuse for "opponent" DF.
    opponents_df = teams_df.copy().rename(columns={'team':'opponent'})
    opponents_df.columns = [c.replace('team_','opponent_') if c.startswith('team_') else c for c in opponents_df.columns]

    # Generate location columns if in features. Append to the "team" DF.
    if 'location_Neutral' in features:
        teams_df['location_Neutral'] = 1 # Presume neutrality.
    for c in ['location_Home','location_Away','location_SemiAway','location_SemiHome']:
        if c in features:
            teams_df[c] = 0

    # Matchup information containers.
    matchups = []

    # Iterate over trace and start one branch per set of coefficients.
    for coefs in coef_trace:
        # Ensure correct shape for coefficients.
        coefs = coefs.reshape((1,coefs.shape[0]))
        # Simulate.
        coef_matchups, coefs_round_outcomes = simulate_bracket_coefs(bracket, teams_df, opponents_df, features, coefs, deterministic)
        # Add matchups to container.
        matchups = matchups + coef_matchups
        # Add simulation outcomes to main outcomes array.
        for t_i, t in enumerate(teams):
            round_outcomes[t_i,:] += coefs_round_outcomes[t]

    # Transform matchup information to DF.
    matchups_df = pd.DataFrame({
            'winner':  np.concatenate([r['winners'] for r in matchups]),
            'loser':   np.concatenate([r['losers']  for r in matchups]),
            'round_of': np.concatenate([np.repeat(r['round_of'],r['round_of']/2) for r in matchups]),
            'count': 1
        }).groupby(['winner','loser','round_of']).agg(np.sum).reset_index()

    # Turn team list and outcomes into a data frame.
    team_round_outcomes = pd.DataFrame(round_outcomes, index=teams, columns=['wins_round_'+str(rnd) for rnd in xrange(1,round_outcomes.shape[1]+1)])

    # Return teams and outcomes.
    return matchups_df, team_round_outcomes

# Helper function for simulating a bracket for one set of coefficients.
def simulate_bracket_coefs (bracket, teams_df, opponents_df, features, coefs, deterministic):
    """
    Simulates a tournament, following all teams down the bracket to the championship, for a specific set of coefficients.
    This function operates recursively.
    Inputs:
        bracket:       Array of first round matchups. Should be first round of the tournament with the bracket "unrolled" so that each row is a pair of teams.
                       That is, the winner of game 1 will play the winner of game 2; 3 vs. 4; etc.
        teams_df:      Bracket teams and statistics.
        opponents_df:  The above, but with different column labels.
        features:      List of features in data dataframe.
        coef_set:      Numpy array of one set of coefficients; each column corresponds to an element of 'features'.
        deterministic: Declare the most likely winner as the winner if true; else use a Bernoulli trial to simulate each game.
    Returns:
        TODO
    """

    ### Data

    # Start by randomly shuffling each pair of teams.
    shuffled_bracket = np.empty(bracket.shape, dtype=bracket.dtype)
    for g_i, game in enumerate(bracket):
        flip = np.random.randint(2)
        shuffled_bracket[g_i,:] = [game[flip],game[np.abs(flip-1)]]

    # Get team and opponent.
    games_df = pd.concat((
            teams_df[teams_df.team.isin(shuffled_bracket[:,0])].reset_index(drop=True),
            opponents_df[opponents_df.opponent.isin(shuffled_bracket[:,1])].reset_index(drop=True)
        ),
        axis=1
    )

    # Calculate aggregate columns
    # Get all team, opponent columns.
    team_cols     = [c for c in games_df.columns if c.startswith('team_')]
    opponent_cols = [c for c in games_df.columns if c.startswith('opponent_')]
    # Calculate diff and ratio col names.
    diff_col_names  = [c.replace('team_','diff_')  for c in team_cols]
    ratio_col_names = [c.replace('team_','ratio_') for c in team_cols]
    # Calculate differences and ratios as DF.
    diff_vals_df  = pd.DataFrame(np.array(games_df.ix[:,team_cols]) - np.array(games_df.ix[:,opponent_cols]),  columns=diff_col_names)
    ratio_vals_df = pd.DataFrame(np.array(games_df.ix[:,team_cols]) / np.array(games_df.ix[:,opponent_cols]), columns=ratio_col_names)
    # Append to game features.
    games_df = pd.concat((games_df,diff_vals_df,ratio_vals_df),  axis=1)

    ### Simulations

    # Simulate games.
    y_hat_raw, y_hat, _2 = predict_games(data=games_df, features=features, coefs=coefs, method='map')

    # Simulate winners/losers if needed. Otherwise just reshape existing results.
    if deterministic:
        winners_losers = y_hat.reshape((y_hat.shape[1],1))
    else:
        game_outcomes  = sp.stats.binom.rvs(n=1, p=y_hat_raw.ravel())
        if type(game_outcomes) == int:
            game_outcomes = np.array(game_outcomes)
        winners_losers = game_outcomes.reshape((y_hat_raw.shape[1],1))
        # Note: could make this even more random and use averages, but that leads to branches blowing up.
        # Every simulation leads to lots more simulations.

    # Add loser information for easy indexing.
    winners_losers = np.concatenate((winners_losers,(np.abs(winners_losers-1))), axis=1)
    winners_losers = winners_losers.ravel()
    # Get winners/losers.
    winners = shuffled_bracket.ravel()[winners_losers == 1]
    losers  = shuffled_bracket.ravel()[winners_losers == 0]

    # Construct dictionary of results.
    round_results = dict((w,[1]) for w in winners)
    round_results.update(dict((l,[0]*int(np.log2(len(bracket)*2))) for l in losers))

    # Construct matchup information.
    matchups = [{
        'winners':  winners,
        'losers':   losers,
        'round_of': len(bracket)*2
    }]

    # Different behavior for tournament end.
    if len(winners) == 1:
        # We just simulated the championship. Return the outcome.
        return matchups, round_results
    else:
        # There are still further rounds to go.
        # Calculate next bracket.
        next_bracket = winners.reshape((len(winners)/2,2))
        # Calculate next set of statistics.
        next_teams_df     = teams_df[teams_df.team.isin(winners)].copy()
        next_opponents_df = opponents_df[opponents_df.opponent.isin(winners)].copy()
        # Simulate.
        next_matchups, next_round_results = simulate_bracket_coefs(next_bracket, teams_df, opponents_df, features, coefs, deterministic)
        # Update round results.
        for t in next_round_results.keys():
            round_results[t] = round_results[t]+next_round_results[t]
        # Augment matchup information.
        matchups = matchups + next_matchups
        # Return both.
        return matchups, round_results

### Standalone Run

# Code to run if run stand-alone.
if __name__ == '__main__':
    main()
def main():
    pass
