### Setup

# Libraries.
import numpy as np
import pymc
from sklearn.cross_validation import KFold
import matplotlib, matplotlib.pyplot as plt

# Custom library
import game_predictions

### Main Functionality

def model_games (
    data,
    features=['team_Pythag'],
    coef_dists=None,
    coef_dist_params=None,
    b0_params={'mu':0, 'tau':0.0003, 'value':0},
    err_params=[.5],
    default_coef_dist = pymc.Normal,
    default_coef_params = {'mu':0, 'tau':0.0003, 'value':0},
    step_method = pymc.Metropolis,
    step_method_params = None,
    default_step_method_params = {'proposal_sd':1., 'proposal_distribution':'Normal'}
):
    """
    Inputs:
        data: Pandas dataframe of game information.
        features: String list of features from game data.
        coef_dists: Distribution for coefficients. Default: see default_coef_dist; usually Normal.
        coef_dist_params: List of dictionaries that parameterize coeficient distributions.
        b0_params: Parameters for intercept ("b0"). Default: mean=0, precision=0.0003; initial value=0.
        err_params: Parameters list for Bernoulli-distribued error distribution. Default: p=0.5.
        default_coef_dist: Coefficient distributions.
        default_coef_params: Default coefficient distribution parameters.
        step_method: MCMC stepping method.
        step_method_params: Parameters for stepping method for each coefficient. Default: see default_step_method_params.
        default_step_method_params: Default step method parameters for coefficient draws.
    Returns:
        PyMC MCMC object. Call with .sample() and desired parameters to perform actual sampling.
    """
    
    # Define priors on intercept and error. PyMC uses precision (inverse variance).
    b0 = pymc.Normal('b_0', **b0_params)
    err = pymc.Bernoulli('err', *err_params)
    
    # Containers for coefficients and data.
    b = np.empty(len(features), dtype=object)
    x = np.empty(len(features), dtype=object)
    
    # Traverse features.
    for i, f in enumerate(features):
        # Coefficient.
        # First start with the distribution. Use one if we've been given one; else use default.
        coef_dist_type = default_coef_dist if coef_dists is None or coef_dists[i] is None else coef_dists[i]
        # Now handle parameters.
        this_coef_dist_params = default_coef_params if coef_dist_params is None or coef_dist_params[i] is None else coef_dist_params[i]
        # Now actually create the coefficient distribution
        b[i] = coef_dist_type('b_'+f, **this_coef_dist_params)
        # Data distribution.
        x[i] = pymc.Normal('x_'+f, 0, 1, value=np.array(data[f]), observed=True)
    
    # Logistic function.
    @pymc.deterministic
    def logistic(b0=b0, b=b, x=x):
        return 1.0 / (1. + np.exp(-(b0 + b.dot(x))))

    # Get outcome data.
    y = np.array(data.win)
    # Model outcome as a Bernoulli distribution.
    y = pymc.Bernoulli('win', logistic, value=y, observed=True)
    
    # Define model, MCMC object.
    model = pymc.Model([logistic, pymc.Container(b), err, pymc.Container(x), y])
    mcmc  = pymc.MCMC(model)
    
    # Configure step methods.
    for var in list(b)+[b0,err]:
        coef_step_method_params = default_step_method_params if step_method_params is None or step_method_params[i] is None else step_method_params[i]
        if step_method == pymc.Slicer:
            mcmc.use_step_method(step_method, stochastic=var)
        else:
            mcmc.use_step_method(step_method, stochastic=var, **default_step_method_params)
    
    # Return MCMC object.
    return mcmc

### Ancillary Functions

def feature_coefficients(model_mcmc, features):
    """
    Get a Numpy array of the features from a model MCMC object.
    Inputs:
        model_mcmc: sampled PyMC object with the given features.
        features: List of features.
    Returns:
        Numpy array of features. Rows are trace history; columns are features starting with the intercept.
    """
    # Trace and feature info.
    trace_len = model_mcmc.trace('b_0')[:].shape[0]
    feat_len  = len(features)+1
    # Container for coefficients.
    coefs = np.empty((trace_len,feat_len))
    # Extract trace for each coefficient and return.
    for f_i, f in enumerate(['0']+features):
        coefs[:,f_i] = model_mcmc.trace('b_'+f)[:]
    return coefs

### Standalone Run

# Code to run if run stand-alone.
if __name__ == '__main__':
    main()
def main():
    pass

# Return the means of the pymc coefficients
# model_mcmc: pymc model
# features:   list of features in pymc
def mcmc_trace_means(model_mcmc, features, printMeans = False):
    means = []
    stds = []
    for feature in features:
        mean = model_mcmc.trace("b_"+feature)[:].mean()
        std = model_mcmc.trace("b_"+feature)[:].std()
        if printMeans:
            print "b_"+feature, mean, std
        means.append(mean)
        stds.append(std)
    return np.array(means), np.array(stds)

# function to perform cross validation
    """
    Inputs:
        X: Pandas dataframe of game information.
        features: String list of features from game data.
        K: K for K-fold cross-validation
        thin: thinning parameter for the sampling technique
    Returns:
        np.array of K-fold cross validated scores
    """
def mcmc_xval(X, features, K, thin, step_method_params=None, coef_dist_params=None):
    scores = []
    kf = KFold(len(X), 5,shuffle=True)
    for train, test in kf:
        X_train = X.ix[train]
        X_test = X.ix[test]
        model_mcmc = model_games(data=X_train,features=features,step_method_params=step_method_params, coef_dist_params=coef_dist_params)
        model_mcmc.sample(10000,2000, thin)
        y_hat_raw, y_hat, y_hat_accuracy = game_predictions.predict_games(X_test, model_mcmc, features, 'pp')
        scores.append(y_hat_accuracy)
    return np.array(scores)

# Function to store geweke scores from pymc's geweke function
    """
    Inputs:
        model_mcmc: pymc mcmc model object
        features: String list of features from game data.
    Returns:
        np.array of coefficients' geweke scores
    """
def geweke_statistics(model_mcmc, features):
    geweke_scores = []
    # Geweke Test
    for feature in features:
        print feature
        scores = pymc.geweke(model_mcmc.trace('b_'+feature)[:])
        geweke_scores.append(scores)
    return geweke_scores

# function to perform cross validation
    """
    Inputs:
        twoD_list: list of geweke score
    Returns:
        np.array of geweke scores
    """
def unravel_list(twoD_list):
    result = np.zeros((np.shape(twoD_list)[1], np.shape(twoD_list)[0]))
    for i in xrange(len(twoD_list)):
        result[0][i] = twoD_list[i][0]
        result[1][i] = twoD_list[i][1]
    return result

# Function to plot geweke scores on all one graph
    """
    Inputs:
        geweke_scores: np.array retruned from fxn geweke_statistics
        features: String list of features from game data.
    """
def plot_Geweke(geweke_scores, features):
    plt.figure(figsize=[8,5])
    for i in xrange(len(geweke_scores)):
#         geweke_MC = Geweke(model_mcmc.trace("b_"+feature)[:], 10, 1000)
        geweke_score_x, geweke_score_y = unravel_list(geweke_scores[i])
        plt.plot(geweke_score_x, geweke_score_y, label=features[i])
    plt.axhline(y=2,color = 'k',linestyle='--')
    plt.axhline(y=-2,color = 'k',linestyle='--')

    plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05),
          fancybox=True, shadow=False, ncol=3)
    plt.show()
