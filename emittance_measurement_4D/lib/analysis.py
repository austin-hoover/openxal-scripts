"""Reconstruct covariance matrix from measurement data."""
from __future__ import print_function
import sys
import math
import random
from math import sqrt, sin, cos
from pprint import pprint
from datetime import datetime
from Jama import Matrix

from xal.extension.solver import Scorer
from xal.service.pvlogger.sim import PVLoggerDataSource
from xal.sim.scenario import Scenario
from xal.smf import Accelerator
from xal.smf import AcceleratorSeq
from xal.smf.data import XMLDataManager

# Local
from least_squares import lsq_linear
import utils
from xal_helpers import minimize
from xal_helpers import get_trial_vals


DIAG_WIRE_ANGLE = utils.radians(-45.0)


# Covariance matrix analysis
#-------------------------------------------------------------------------------
def rms_ellipse_dims(Sigma, dim1, dim2):
    """Return tilt angle and semi-axes of rms ellipse.

    Parameters
    ----------
    Sigma : Matrix, shape (4, 4)
        The covariance matrix for [x, x', y, y']. The rms ellipsoid is defined
        by w^T Sigma w, where w = [x, x', y, y']^T.
    dim1, dim2, {'x', 'xp', 'y', 'yp'}
        The horizontal (dim1) and vertical (dim2) dimension. The 4D ellipsoid
        is projected onto this 2D plane.
        
    Returns
    -------
    phi : float
        The tilt angle of the ellipse as measured below the horizontal axis.
        So, a positive tilt angle means a negative correlation.
    c1, c2 : float
        The horizontal and vertical semi-axes, respectively, of the ellipse
        when phi = 0.
    """
    str_to_int = {'x':0, 'xp':1, 'y':2, 'yp':3}
    i = str_to_int[dim1]
    j = str_to_int[dim2]
    sig_ii, sig_jj, sig_ij = Sigma.get(i, i), Sigma.get(j, j), Sigma.get(i, j)
    phi = -0.5 * math.atan2(2 * sig_ij, sig_ii - sig_jj)
    sn, cs = math.sin(phi), math.cos(phi)
    sn2, cs2 = sn**2, cs**2
    c1 = sqrt(abs(sig_ii*cs2 + sig_jj*sn2 - 2*sig_ij*sn*cs))
    c2 = sqrt(abs(sig_ii*sn2 + sig_jj*cs2 + 2*sig_ij*sn*cs))
    return phi, c1, c2


def intrinsic_emittances(Sigma):
    U = Matrix([[0, 1, 0, 0], [-1, 0, 0, 0], [0, 0, 0, 1], [0, 0, -1, 0]])
    SU = Sigma.times(U)
    SU2 = SU.times(SU)
    trSU2 = SU2.trace()
    detS = Sigma.det()
    eps_1 = 0.5 * sqrt(-trSU2 + sqrt(trSU2**2 - 16 * detS))
    eps_2 = 0.5 * sqrt(-trSU2 - sqrt(trSU2**2 - 16 * detS)) 
    return eps_1, eps_2


def apparent_emittances(Sigma):
    eps_x = sqrt(Sigma.get(0, 0) * Sigma.get(1, 1) - Sigma.get(0, 1)**2)
    eps_y = sqrt(Sigma.get(2, 2) * Sigma.get(3, 3) - Sigma.get(2, 3)**2)
    return eps_x, eps_y


def emittances(Sigma):
    eps_x, eps_y = apparent_emittances(Sigma)
    eps_1, eps_2 = intrinsic_emittances(Sigma)
    return eps_x, eps_y, eps_1, eps_2


def twiss2D(Sigma):
    eps_x, eps_y = apparent_emittances(Sigma)
    beta_x = Sigma.get(0, 0) / eps_x
    beta_y = Sigma.get(2, 2) / eps_y
    alpha_x = -Sigma.get(0, 1) / eps_x
    alpha_y = -Sigma.get(2, 3) / eps_y
    return alpha_x, alpha_y, beta_x, beta_y


def is_positive_definite(Sigma):
    """Return True if symmetric matrix is positive definite."""
    return all([e >= 0 for e in Sigma.eig().getRealEigenvalues()])


def is_valid_cov(Sigma):
    """Return True if the covariance matrix `Sigma` is unphysical."""
    if not is_positive_definite(Sigma):
        return False
    if Sigma.det() < 0:
        return False
    eps_x, eps_y, eps_1, eps_2 = emittances(Sigma)
    if (eps_x * eps_y < eps_1 * eps_2):
        return False
    return True


def V_matrix_uncoupled(alpha_x, alpha_y, beta_x, beta_y):
    """4x4 normalization matrix for x-x' and y-y'."""
    V = Matrix([[sqrt(beta_x), 0, 0, 0],
                [-alpha_x/sqrt(beta_x), 1/sqrt(beta_x), 0, 0],
                [0, 0, sqrt(beta_y), 0],
                [0, 0, -alpha_y/sqrt(beta_y), 1/sqrt(beta_y)]])
    return V


class BeamStats:
    """Container for beam statistics calculated from the covariance matrix."""
    def __init__(self, Sigma):
        if type(Sigma) is list:
            Sigma = Matrix(Sigma)
        self.Sigma = Sigma
        self.eps_x, self.eps_y = apparent_emittances(Sigma)
        self.eps_1, self.eps_2 = intrinsic_emittances(Sigma)
        self.alpha_x, self.alpha_y, self.beta_x, self.beta_y = twiss2D(Sigma)
        self.coupling_coeff = 1.0 - sqrt(self.eps_1 * self.eps_2 / (self.eps_x * self.eps_y))
        
    def rms_ellipse_dims(dim1, dim2):
        return rms_ellipse_dims(self.Sigma, dim1, dim2)
    
    def print_all(self):
        print('eps_1, eps_2 = {} {} [mm mrad]'.format(self.eps_1, self.eps_2))
        print('eps_x, eps_y = {} {} [mm mrad]'.format(self.eps_x, self.eps_y))
        print('alpha_x, alpha_y = {} {} [rad]'.format(self.alpha_x, self.alpha_y))
        print('beta_x, beta_y = {} {} [m/rad]'.format(self.beta_x, self.beta_y))


def to_mat(moments):
    """Return covariance matrix from 10 element moment vector."""
    (sig_11, sig_22, sig_12,
     sig_33, sig_44, sig_34, 
     sig_13, sig_23, sig_14, sig_24) = moments
    return Matrix([[sig_11, sig_12, sig_13, sig_14], 
                   [sig_12, sig_22, sig_23, sig_24], 
                   [sig_13, sig_23, sig_33, sig_34], 
                   [sig_14, sig_24, sig_34, sig_44]])


def to_vec(Sigma):
    """Return 10 element moment vector from covariance matrix."""
    sig_11, sig_12, sig_13, sig_14 = Sigma[0][:]
    sig_22, sig_23, sig_24 = Sigma[1][1:]
    sig_33, sig_34 = Sigma[2][2:]
    sig_44 = Sigma[3][3]
    return np.array([sig_11, sig_22, sig_12, 
                     sig_33, sig_44, sig_34, 
                     sig_13, sig_23, sig_14, sig_24])

 

# Covariance matrix reconstruction
#-------------------------------------------------------------------------------
def get_sig_xy(sig_xx, sig_yy, sig_uu, diag_wire_angle):
    """Compute cov(x, y) from horizontal, vertical, and diagonal wires.
    
    Diagonal wire angle should be in radians.
    """
    phi = utils.radians(90.0) + diag_wire_angle
    sin, cos = math.sin(phi), math.cos(phi)
    sig_xy = (sig_uu - sig_xx*(cos**2) - sig_yy*(sin**2)) / (2 * sin * cos)
    return sig_xy


def reconstruct(transfer_mats, moments, constr=True, **lsq_kws):
    """Reconstruct covariance matrix from measured moments and transfer matrices.
    
    Parameters
    ----------
    transfer_mats : list
        Each element is a list of shape (4, 4) representing a transfer matrix.
    moments : list
        Each element is list containing of [cov(x, x), cov(y, y), cov(x, y)], 
        where cov means covariance.
    constr: bool
        Whether to try nonlinear solver if LLSQ answer is unphysical. Default
        is True.
    **lsq_kws
        Key word arguments passed to `lsq_linear` method.
        
    Returns
    -------
    list, shape (4, 4)
        Reconstructed covariance matrix.
    """
    # Form A and b.
    A, b = [], []
    for M, (sig_xx, sig_yy, sig_xy) in zip(transfer_mats, moments):
        A.append([M[0][0]**2, M[0][1]**2, 2*M[0][0]*M[0][1], 0, 0, 0, 0, 0, 0, 0])
        A.append([0, 0, 0, M[2][2]**2, M[2][3]**2, 2*M[2][2]*M[2][3], 0, 0, 0, 0])
        A.append([0, 0, 0, 0, 0, 0, M[0][0]*M[2][2],  M[0][1]*M[2][2],  M[0][0]*M[2][3],  M[0][1]*M[2][3]])
        b.append(sig_xx)
        b.append(sig_yy)
        b.append(sig_xy)

    # Solve the problem Ax = b.
    lsq_kws.setdefault('solver', 'exact')
    moment_vec = lsq_linear(A, b, **lsq_kws)
    Sigma = to_mat(moment_vec)
    
    # Return the answer if we don't care if it's physical or not.
    if not constr:
        return Sigma

    # Return the answer if Sigma is physical.
    def is_positive_definite(Sigma):
        eig_decomp = Sigma.eig()
        return any([eigval < 0 for eigval in eig_decomp.getRealEigenvalues()])

    def is_physical_cov(Sigma):
        if is_positive_definite(Sigma) and Sigma.det() >= 0:
            eps_x, eps_y, eps_1, eps_2 = emittances(Sigma)
            if (eps_x * eps_y >= eps_1 * eps_2):
                return True
        return False

    if is_physical_cov(Sigma):
        print('Covariance matrix is physical.')
        return Sigma
    
    # Otherwise try different fitting.
    print('Covariance matrix is unphysical. Running solver.')
    Axy, bxy = [], []
    for M, (sig_xx, sig_yy, sig_xy) in zip(transfer_mats, moments):
        Axy.append([M[0][0]*M[2][2],  M[0][1]*M[2][2],  M[0][0]*M[2][3],  M[0][1]*M[2][3]])
        bxy.append([sig_xy])
    Axy = Matrix(Axy)
    bxy = Matrix(bxy)
    Sigma_new = Sigma.copy()
    
    eps_x, eps_y = apparent_emittances(Sigma)  
    alpha_x, alpha_y, beta_x, beta_y = twiss2D(Sigma)
    

    # This section puts bounds on the cross-plane moments. For some reason, it
    # doesn't seem to work on real data (it terminates at a solution I know
    # is wrong).
    #---------------------------------------------------------------------------
#     class MyScorer(Scorer):
        
#         def __init__(self):
#             return
        
#         def score(self, trial, variables):
#             sig_13, sig_23, sig_14, sig_24 = get_trial_vals(trial, variables)
#             vec = Matrix([[sig_13], [sig_23], [sig_14], [sig_24]])
#             residuals = Axy.times(vec).minus(target)
#             cost = residuals.normF()**2
#             print(cost)
#             return cost

#     r_denom_13 = sqrt(Sigma.get(0, 0) * Sigma.get(2, 2))
#     r_denom_23 = sqrt(Sigma.get(1, 1) * Sigma.get(2, 2))
#     r_denom_14 = sqrt(Sigma.get(0, 0) * Sigma.get(3, 3))
#     r_denom_24 = sqrt(Sigma.get(1, 1) * Sigma.get(3, 3))
#     lb = [-r_denom_13, -r_denom_23, -r_denom_14, -r_denom_24]
#     ub = [+r_denom_13, +r_denom_23, +r_denom_14, +r_denom_24]
#     bounds = (lb, ub)
#     guess = 4 * [0.0]
#     scorer = MyScorer()
#     var_names = ['sig_13', 'sig_23', 'sig_14', 'sig_24']
#     sig_13, sig_23, sig_14, sig_24 = minimize(scorer, guess, var_names, bounds, verbose=2)
#     Sigma_new.set(0, 2, sig_13)
#     Sigma_new.set(2, 0, sig_13)
#     Sigma_new.set(1, 2, sig_23)
#     Sigma_new.set(2, 1, sig_23)
#     Sigma_new.set(0, 3, sig_14)
#     Sigma_new.set(3, 0, sig_14)
#     Sigma_new.set(1, 3, sig_24)
#     Sigma_new.set(3, 1, sig_24)
#     return Sigma_new


    # This section uses the parameterization of Edwards/Teng.
    #---------------------------------------------------------------------------
    def get_cov(eps_1, eps_2, alpha_x, alpha_y, beta_x, beta_y, a, b, c):
        E = utils.diagonal_matrix([eps_1, eps_1, eps_2, eps_2])
        V = Matrix(4, 4, 0.)
        V.set(0, 0, sqrt(beta_x))
        V.set(1, 0, -alpha_x / sqrt(beta_x))
        V.set(1, 1, 1 / sqrt(beta_x))
        V.set(2, 2, sqrt(beta_y))
        V.set(3, 2, -alpha_y / sqrt(beta_y))
        V.set(3, 3, 1 / sqrt(beta_y))
        if a == 0:
            if b == 0 or c == 0:
                d = 0
            else:
                raise ValueError("a is zero but b * c is not zero.")
        else:
            d = b * c / a
        C = Matrix([[1, 0, a, b], [0, 1, c, d], [-d, b, 1, 0], [c, -a, 0, 1]])
        VC = V.times(C)
        return VC.times(E.times(VC.transpose()))

    class MyScorer(Scorer):
        
        def __init__(self):
            return
        
        def score(self, trial, variables):
            eps_1, eps_2, a, b, c = get_trial_vals(trial, variables)
            S = get_cov(eps_1, eps_2, alpha_x, alpha_y, beta_x, beta_y, a, b, c)
            vec = Matrix([[S.get(0, 2)], [S.get(1, 2)], [S.get(0, 3)], [S.get(1, 3)]])
            residuals = Axy.times(vec).minus(bxy)
            cost = residuals.normF()**2
            f = 1.0
            cost += f * (S.get(0, 0) - Sigma.get(0, 0))**2
            cost += f * (S.get(0, 1) - Sigma.get(0, 1))**2
            cost += f * (S.get(1, 1) - Sigma.get(1, 1))**2
            cost += f * (S.get(2, 2) - Sigma.get(2, 2))**2
            cost += f * (S.get(2, 3) - Sigma.get(2, 3))**2
            cost += f * (S.get(3, 3) - Sigma.get(3, 3))**2
            return cost
                
    inf = 1e20
    lb = [0., 0., -inf, -inf, -inf]
    ub = inf
    bounds = (lb, ub)
    guess = [1.0 * eps_x, 1.0 * eps_y, 0.1 * random.random(), 0.1 * random.random(), -0.1 * random.random()]
    var_names = ['eps_1', 'eps_2', 'a', 'b', 'c']
    scorer = MyScorer()
    
    eps_1, eps_2, a, b, c = minimize(scorer, guess, var_names, bounds, maxiters=50000, tol=1e-15, verbose=2)
    S = get_cov(eps_1, eps_2, alpha_x, alpha_y, beta_x, beta_y, a, b, c)
    return S



# PTA file processing
#-------------------------------------------------------------------------------
def is_harp_file(filename):
    file = open(filename)
    for line in file:
        if 'Harp' in line:
            return True
    return False


class Stat:
    """Container for a signal parameter.
    
    Attributes
    ----------
    name : str
        Parameter name.
    rms : float
        Parameter value from rms calculation.
    fit : float
        Parameter value from Gaussian fit.
    """
    def __init__(self, name, rms, fit):
        self.name, self.rms, self.fit = name, rms, fit

        
class Signal:
    """Container for profile signal.
    
    Attributes
    ----------
    pos : list
        Wire positions.
    raw : list
        Raw signal amplitudes at each position.
    fit : list
        Gaussian fit amplitudes at each position.
    stats : dict
        Each key is a different statistical parameter: ('Area', 'Mean', etc.). 
        Each value is a Stat object that holds the parameter name, rms value, 
        and Gaussian fit value.
    """
    def __init__(self, pos, raw, fit, stats):
        self.pos, self.raw, self.fit, self.stats = pos, raw, fit, stats
        
        
class Profile:
    """Stores data from single wire-scanner.
    
    Attributes
    ----------
    hor, ver, dia : Signal
        Signal object for horizontal, vertical and diagonal wire.
    diag_wire_angle : float
        Angle of diagonal wire above the x axis.
    """
    def __init__(self, pos, raw, fit=None, stats=None, diag_wire_angle=DIAG_WIRE_ANGLE):
        """Constructor.
        
        Parameters
        ----------
        pos : [xpos, ypos, upos]
            Position lists for each wire.
        raw : [xraw, yraw, uraw]
            List of raw signal amplitudes for each wire.
        fit : [xfit, yfit, ufit]
            List of Gaussian fit amplitudes for each wire.
        stats : [xstats, ystats, ustats]
            List of stats dictionaries for each wire.
        """
        self.diag_wire_angle = diag_wire_angle
        xpos, ypos, upos = pos
        xraw, yraw, uraw = raw
        if fit is None:
            xfit = yfit = ufit = None
        else:
            xfit, yfit, ufit = fit
        if stats is None:
            xstats = ystats = ustats = None
        else:
            xstats, ystats, ustats = stats
        self.hor = Signal(xpos, xraw, xfit, xstats)
        self.ver = Signal(ypos, yraw, yfit, ystats)
        self.dia = Signal(upos, uraw, ufit, ustats)
        

class Measurement(dict):
    """Dictionary of profiles for one measurement.

    Each key in this dictionary is a wire-scanner ID; each value is a Profile.
    
    Attributes
    ----------
    filename : str
        Full path to the PTA file.
    filename_short : str
        Only include the filename, not the full path.
    timestamp : datetime
        Represents the time at which the data was taken.
    pvloggerid : int
        The PVLoggerID of the measurement (this gives a snapshot of the machine state).
    node_ids : list[str]
        The ID of each wire-scanner. (These are the dictionary keys.)
    moments : dict
        The [<x^2>, <y^2>, <xy>] moments at each wire-scanner.
    transfer_mats : dict
        The linear 4x4 transfer matrix from a start node to each wire-scanner. 
        The start node is determined in the function call `get_transfer_mats`.
    """
    def __init__(self, filename):
        dict.__init__(self)
        self.filename = filename
        self.filename_short = filename.split('/')[-1]
        self.timestamp = None
        self.pvloggerid = None
        self.node_ids = None
        self.moments, self.transfer_mats = dict(), dict()
        self.read_pta_file()
        
    def read_pta_file(self):
        # Store the timestamp on the file.
        date, time = self.filename.split('WireAnalysisFmt-')[-1].split('_')
        time = time.split('.pta')[0]
        year, month, day = [int(token) for token in date.split('.')]
        hour, minute, second = [int(token) for token in time.split('.')]
        self.timestamp = datetime(year, month, day, hour, minute, second)
        
        # Collect lines corresponding to each wire-scanner
        file = open(self.filename, 'r')
        lines = dict()
        ws_id = None
        for line in file:
            line = line.rstrip()
            if line.startswith('RTBT_Diag'):
                ws_id = line
                continue
            if ws_id is not None:
                lines.setdefault(ws_id, []).append(line)
            if line.startswith('PVLoggerID'):
                self.pvloggerid = int(line.split('=')[1])
        file.close()
        self.node_ids = sorted(list(lines))

        # Read the lines
        for node_id in self.node_ids:
            # Split lines into three sections:
            #     stats: statistical signal parameters;
            #     raw: wire positions and raw signal amplitudes;
            #     fit: wire positions and Gaussian fit amplitudes.
            # There is one blank line after each section.
            sep = ''
            lines_stats, lines_raw, lines_fit = utils.split(lines[node_id], sep)[:3]

            # Remove headers and dashed lines beneath headers.
            lines_stats = lines_stats[2:]
            lines_raw = lines_raw[2:]
            lines_fit = lines_fit[2:]   

            # The columns of the following array are ['pos', 'yraw', 'uraw', 'xraw', 
            # 'xpos', 'ypos', 'upos']. (NOTE: This is not the order that is written
            # in the file header.)
            data_arr_raw = [utils.string_to_list(line) for line in lines_raw]
            pos, yraw, uraw, xraw, xpos, ypos, upos = utils.transpose(data_arr_raw)

            # This next array is the same, but it contains 'yfit', 'ufit', 'xfit', 
            # instead of 'yraw', 'uraw', 'xraw'.
            data_arr_fit = [utils.string_to_list(line) for line in lines_fit]
            pos, yfit, ufit, xfit, xpos, ypos, upos = utils.transpose(data_arr_fit)

            # Get statistical signal parameters. (Headers don't give true ordering.)
            xstats, ystats, ustats = dict(), dict(), dict()
            for line in lines_stats:
                tokens = line.split()
                name = tokens[0]
                vals = [float(val) for val in tokens[1:]]
                s_yfit, s_yrms, s_ufit, s_urms, s_xfit, s_xrms = vals
                xstats[name] = Stat(name, s_xrms, s_xfit)
                ystats[name] = Stat(name, s_yrms, s_yfit)
                ustats[name] = Stat(name, s_urms, s_ufit)

            self[node_id] = Profile([xpos, ypos, upos], 
                                    [xraw, yraw, uraw],
                                    [xfit, yfit, ufit], 
                                    [xstats, ystats, ustats])
            
    def read_harp_file(self, filename):
        file = open(filename, 'r')
        data = []
        pvloggerid = None
        for line in file:
            tokens = line.rstrip().split()
            if not tokens or tokens[0] in ['start', 'RTBT_Diag:Harp30']:
                continue
            if tokens[0] == 'PVLoggerID':
                pvloggerid = int(tokens[-1])
                continue
            data.append([float(token) for token in tokens])
        file.close()
        
#         if pvloggerid != self.pvloggerid:
#             raise ValueError('PVLoggerID not the same as the wire-scans in this measurement.')
        
        xpos, xraw, ypos, yraw, upos, uraw = utils.transpose(data)
        self['RTBT_Diag:Harp30'] = Profile([xpos, ypos, upos], 
                                           [xraw, yraw, uraw])
            
    def get_moments(self):
        """Store/return dictionary of measured moments at each profile."""
        self.moments = dict()
        for node_id in self.node_ids:
            profile = self[node_id]
            sig_xx = profile.hor.stats['Sigma'].rms**2
            sig_yy = profile.ver.stats['Sigma'].rms**2
            sig_uu = profile.dia.stats['Sigma'].rms**2
            sig_xy = get_sig_xy(sig_xx, sig_yy, sig_uu, profile.diag_wire_angle)
            self.moments[node_id] = [sig_xx, sig_yy, sig_xy]
        return self.moments

    def get_transfer_mats(self, start_node_id, tmat_generator):
        """Store/return dictionary of transfer matrices from start_node to each profile."""
        self.transfer_mats = dict()
        tmat_generator.sync(self.pvloggerid)
        for node_id in self.node_ids:
            tmat = tmat_generator.generate(start_node_id, node_id)
            self.transfer_mats[node_id] = tmat
        return self.transfer_mats

    def export_files(self):
        raise NotImplementedError
    
    
def get_scan_info(measurements, tmat_generator, start_node_id):
    """Make dictionaries of measured moments and transfer matrices at each wire-scanner."""
    print( 'Reading files...')
    moments_dict, tmats_dict = dict(), dict()
    for measurement in measurements:
        print("  Reading file '{}'  pvloggerid = {}".format(measurement.filename_short, 
                                                            measurement.pvloggerid))
        measurement.get_moments()
        measurement.get_transfer_mats(start_node_id, tmat_generator)
        for node_id in measurement.node_ids:
            if node_id not in moments_dict:
                moments_dict[node_id] = []
            moments = measurement.moments[node_id]
            moments_dict[node_id].append(moments)
            if node_id not in tmats_dict:
                tmats_dict[node_id] = []
            tmat = measurement.transfer_mats[node_id]
            tmats_dict[node_id].append(tmat)
    print('Done.')
    return moments_dict, tmats_dict