import math
from Jama import Matrix

from java.awt import BorderLayout
from java.awt import Color
from java.awt import Component
from java.awt import Dimension
from java.awt import FlowLayout
from java.awt import Font
from java.awt import GridLayout
from java.awt import GridBagLayout
from java.awt import GridBagConstraints
from java.awt.event import ActionListener
from java.awt.event import WindowAdapter
from javax.swing import BorderFactory
from javax.swing import BoxLayout
from javax.swing import GroupLayout
from javax.swing import JButton
from javax.swing import JComboBox
from javax.swing import JFrame
from javax.swing import JLabel
from javax.swing import JPanel
from javax.swing import JProgressBar
from javax.swing import JTable
from javax.swing import JTabbedPane
from javax.swing import JTextField
from javax.swing import JFormattedTextField

from xal.extension.widgets.plot import BasicGraphData
from xal.extension.widgets.plot import CurveData
from xal.extension.widgets.plot import FunctionGraphsJPanel

# Local
import utils
import analysis


# 'Colorblind' color cycle
COLOR_CYCLE = [
    Color(0.0, 0.44705882, 0.69803922),
    Color(0.83529412, 0.36862745, 0.0),
    Color(0.0, 0.61960784, 0.45098039),
    Color(0.8, 0.4745098, 0.65490196),
    Color(0.94117647, 0.89411765, 0.25882353),
    Color(0.3372549, 0.70588235, 0.91372549),
]

GRID_COLOR = Color(245, 245, 245)


def rotate(x, y, phi):
    """Rotate point (x, y) counterclockwise by phi radians."""
    sn, cs = math.sin(phi), math.cos(phi)
    x_rot =  x * cs - y * sn
    y_rot =  x * sn + y * cs
    return x_rot, y_rot


def ellipse_points(width, height, tilt=0., n_pts=50):
    angles = utils.linspace(0, 2 * math.pi, n_pts)
    xvals = [width * math.cos(angle) for angle in angles]
    yvals = [height * math.sin(angle) for angle in angles]
    xvals, yvals = zip(*[utils.rotate(x, y, tilt) for x, y in zip(xvals, yvals)])
    return xvals, yvals


class PlotPanel(FunctionGraphsJPanel):
    
    def __init__(self, xlabel='', ylabel='', title='', grid=True):
        FunctionGraphsJPanel.__init__(self)
        self.setName(title)
        self.setAxisNames(xlabel, ylabel)
        self.setGraphBackGroundColor(Color.white)   
        self.setGridLineColor(GRID_COLOR)
        if grid == 'y' or not grid:
            self.setGridLinesVisibleX(False)
        if grid == 'x' or not grid:
            self.setGridLinesVisibleY(False)
        

class LinePlotPanel(PlotPanel):
    """Class for 2D line plots."""
    def __init__(self, xlabel='', ylabel='', title='', n_lines=2, lw=3, ms=0, grid=True):
        PlotPanel.__init__(self, xlabel, ylabel, title, grid)
        etched_border = BorderFactory.createEtchedBorder()
        self.setBorder(etched_border)
        self.setLegendButtonVisible(False)
        self.n_lines = n_lines
        self.data_list = [BasicGraphData() for _ in range(n_lines)]
        for data, color in zip(self.data_list, COLOR_CYCLE):
            data.setGraphColor(color)
            data.setLineThick(lw)
            data.setGraphPointSize(ms)
    
    def set_data(self, x_list, y_list):
        """Replot with provided data."""
        if not x_list or not y_list:
            return
        if len(utils.shape(y_list)) == 1: # single list provided
            y_list = [y_list]
        if len(utils.shape(x_list)) == 1: # single list provided
            x_list = len(y_list) * [x_list]
        self.removeAllGraphData()
        for data, x, y in zip(self.data_list, x_list, y_list):
            data.addPoint(x, y)  
            self.addGraphData(data) 
        
    def ellipse(self, width, height, tilt=0.0, points=50, lw=4):
        xvals, yvals = ellipse_points(width, height, tilt, points)
        curve_data = CurveData()
        curve_data.setPoints(xvals, yvals)
        curve_data.setLineWidth(lw)
        self.addCurveData(curve_data)
        
    def plot(self, xvals, yvals, color=None, lw=None, ms=None):
        """Add a line to the plot."""
        data = BasicGraphData()
        if color:
            data.setGraphColor(color)
        if lw:
            data.setLineThick(lw)
        if ms:
            data.setGraphPointSize(ms)
        for x, y in zip(xvals, yvals):
            data.addPoint(x, y)
        self.addGraphData(data) 
            
    def set_xlim(self, xmin, xmax, xstep):
        self.setLimitsAndTicksX(xmin, xmax, xstep)
        
    def set_ylim(self, ymin, ymax, ystep):
        self.setLimitsAndTicksX(ymin, ymax, ystep)
        
    
class CornerPlotPanel(JPanel):
    
    def __init__(self, grid=False, figsize=None):
        JPanel.__init__(self)
        self.setLayout(GridBagLayout())
        if figsize:
            self.setPreferredSize(Dimension(*figsize))
        
        constraints = GridBagConstraints()
        constraints.fill = GridBagConstraints.BOTH
        constraints.gridwidth = 1
        constraints.gridheight = 1
        constraints.weightx = 0.5
        constraints.weighty = 0.5
        
        dim_to_int = {'x':0, 'xp':1, 'y':2, 'yp':3}
        dims = ['x', 'xp', 'y', 'yp']
        xdims = dims[:-1]
        ydims = dims[1:]
        self.plots = dict()
        for ydim in ydims:
            for xdim in xdims:
                i = dim_to_int[ydim] - 1
                j = dim_to_int[xdim]
                if j <= i:
                    plot = LinePlotPanel(grid=grid)
                    constraints.gridx = j
                    constraints.gridy = i
                    if j == 0:
                        plot.setAxisNameY(ydim)
                    if i == 2:
                        plot.setAxisNameX(xdim)
                    self.add(plot, constraints)
                    key = ''.join([xdim, ',', ydim])
                    self.plots[key] = plot
                    
    def rms_ellipses(self, Sigma, lw=4, points=100):
        for key, panel in self.plots.items():
            dim1, dim2 = key.split(',')
            phi, cx, cy = analysis.rms_ellipse_dims(Sigma, dim1, dim2)
            panel.ellipse(cx, cy, phi, lw=lw, points=points)
                    
                    
                    
    