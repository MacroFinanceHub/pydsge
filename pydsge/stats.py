#!/bin/python2
# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import warnings
import os
import scipy.stats as ss
import scipy.optimize as so
from scipy.special import gammaln


def mc_error(x):
    means = np.mean(x, 0)
    return np.std(means) / np.sqrt(x.shape[0])


def calc_min_interval(x, alpha):
    """Internal method to determine the minimum interval of
    a given width

    Assumes that x is sorted numpy array.
    """
    n = len(x)
    cred_mass = 1.0 - alpha

    interval_idx_inc = int(np.floor(cred_mass * n))
    n_intervals = n - interval_idx_inc
    interval_width = x[interval_idx_inc:] - x[:n_intervals]

    if len(interval_width) == 0:
        # raise ValueError('Too few elements for interval calculation')
        warnings.warn('Too few elements for interval calculation.')

        return None, None

    else:

        min_idx = np.argmin(interval_width)
        hdi_min = x[min_idx]
        hdi_max = x[min_idx + interval_idx_inc]

        return hdi_min, hdi_max


def _hpd_df(x, alpha):

    cnames = ['hpd_{0:g}'.format(100 * alpha / 2),
              'hpd_{0:g}'.format(100 * (1 - alpha / 2))]

    sx = np.sort(x.flatten())
    hpd_vals = np.array(calc_min_interval(sx, alpha)).reshape(1, -1)

    return pd.DataFrame(hpd_vals, columns=cnames)


def summary(trace, varnames, priors=None, alpha=0.05):
    # in parts stolen from pymc3 because it looks really nice

    with os.popen('stty size', 'r') as rows_cols:
        cols = rows_cols.read().split()[1]

    if priors is None:
        priors = varnames

    f_prs = [lambda x: pd.Series(x, name='distribution'),
             lambda x: pd.Series(x, name='mean/alpha'),
             lambda x: pd.Series(x, name='sd/beta')]

    funcs = [lambda x: pd.Series(np.mean(x), name='mean'),
             lambda x: pd.Series(np.std(x), name='sd'),
             lambda x: pd.Series(mc_error(x), name='mc_error'),
             lambda x: _hpd_df(x, alpha)]

    var_dfs = []
    for i, var in enumerate(varnames):
        lst = []
        vals = trace[:, :, i]

        if priors is not None and int(cols) > 90:
            prior = priors[var]
            [lst.append(f(prior[j])) for j, f in enumerate(f_prs)]

        [lst.append(f(vals)) for f in funcs]
        var_df = pd.concat(lst, axis=1)
        var_df.index = [var]
        var_dfs.append(var_df)

    dforg = pd.concat(var_dfs, axis=0)

    return dforg


def mc_mean(trace, varnames):
    # in most parts just stolen from pymc3 because it looks really nice

    p_means = []

    for i, var in enumerate(varnames):
        vals = trace[:, :, i]
        p_means.append(np.mean(vals))

    return p_means


class InvGamma(object):

    name = 'inv_gamma_dynare'

    def __init__(self, a, b):

        self.a = a
        self.b = b

    def logpdf(self, x):

        if x < 0:
            return -np.inf

        else:

            a = self.a
            b = self.b

            lpdf = (np.log(2) - gammaln(b/2) + b/2*np.log(b*a**2/2) -
                    (b+1)/2*np.log(x**2) - b*a**2/(2*x**2))

            return lpdf


class InvGammaDynare(ss.rv_continuous):

    name = 'inv_gamma_dynare'

    def _logpdf(self, x, s, nu):

        # xa = np.array(x)

        # lpdf = np.copy(xa)

        # lpdf[xa < 0] = -np.inf

        # lpdf[xa >= 0] = np.log(2) - gammaln(nu/2) - nu/2*(np.log(2) -
                                                          # np.log(s)) - (nu+1)*np.log(xa[xa >= 0]) - .5*s/xa[xa >= 0]**2

        if x < 0:
            lpdf = -np.inf

        else:
            lpdf = np.log(2) - gammaln(nu/2) - nu/2*(np.log(2) -
                                                     np.log(s)) - (nu+1)*np.log(x) - .5*s/x**2

        return lpdf

    def _pdf(self, x, s, nu):
        return np.exp(self._logpdf(x, s, nu))


def inv_gamma_spec_old(mu, sigma):

    # directly stolen and translated from dynare/matlab. It is unclear to me what the sigma parameter stands for, as it does not appear to be the standard deviation. This is provided for compatibility reasons, I strongly suggest to use the inv_gamma distribution that simply takes mean / stdd as parameters.

    ig1fun = lambda nu: np.log(2*mu**2) - np.log((sigma**2+mu**2) * (nu-2)) + 2*(gammaln(nu/2)-gammaln((nu-1)/2))

    nu0 = np.sqrt(2*(2+mu**2/sigma**2))
    res = so.root(ig1fun, nu0)

    nu = res['x'][0]
    s = (sigma**2 + mu**2)*(nu - 2)

    check0 = abs(sigma-np.sqrt(s/(nu-2)-mu*mu)) > 1e-7
    check1 = abs(np.log(mu)-np.log(np.sqrt(s/2))-gammaln((nu-1)/2)+gammaln(nu/2)) > 1e-7

    if res['success'] or check0 or check1:
        raise ValueError('Failed in solving for the hyperparameters!')

    return s, nu

def inv_gamma_spec(mu, sigma):

    # directly stolen and translated from dynare/matlab. It is unclear to me what the sigma parameter stands for, as it does not appear to be the standard deviation. This is provided for compatibility reasons, I strongly suggest to use the inv_gamma distribution that simply takes mean / stdd as parameters.

    ig1fun = lambda nu: np.log(2*mu**2) - np.log((sigma**2+mu**2) * (nu-2)) + 2*(gammaln(nu/2)-gammaln((nu-1)/2))

    nu = np.sqrt(2*(2+mu**2/sigma**2))
    nu2 = 2*nu
    nu1 = 2
    err  = ig1fun(nu)
    err2 = ig1fun(nu2)

    if err2 > 0: 
        while nu2 < 1e12: # Shift the interval containing the root. 
            nu1  = nu2
            nu2  = nu2*2
            err2 = ig1fun(nu2)
            if err2<0:
                break
        if err2>0:
            raise ValueError('[inv_gamma_spec:] Failed in finding an interval containing a sign change! You should check that the prior variance is not too small compared to the prior mean...')

    # Solve for nu using the secant method.
    while abs(nu2/nu1-1) > 1e-14:
        if err > 0:
            nu1 = nu
            if nu < nu2:
                nu = nu2
            else:
                nu = 2*nu
                nu2 = nu
        else:
            nu2 = nu
        nu =  (nu1+nu2)/2
        err = ig1fun(nu)

    s = (sigma**2+mu**2)*(nu-2)

    if abs(np.log(mu)-np.log(np.sqrt(s/2))-gammaln((nu-1)/2)+gammaln(nu/2))>1e-7:
        raise ValueError('[inv_gamma_spec:] Failed in solving for the hyperparameters!')
    if abs(sigma-np.sqrt(s/(nu-2)-mu*mu))>1e-7:
        raise ValueError('[inv_gamma_spec:] Failed in solving for the hyperparameters!')

    return s, nu
