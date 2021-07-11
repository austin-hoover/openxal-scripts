import math
import time
import sys

from java.awt import BorderLayout
from java.awt import Color
from java.awt import Component
from java.awt import Dimension
from java.awt import FlowLayout
from java.awt import Font
from java.awt import GridLayout
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
from javax.swing import JTable
from javax.swing import JTextField
from javax.swing import JFormattedTextField
from javax.swing.event import DocumentListener
from javax.swing.table import AbstractTableModel
from java.text import NumberFormat
from java.text import DecimalFormat

from xal.extension.widgets.plot import BasicGraphData
from xal.extension.widgets.plot import FunctionGraphsJPanel
from xal.smf import AcceleratorSeqCombo
from xal.smf.data import XMLDataManager

from lib.time_and_date_lib import DateAndTimeText
from lib.phase_controller import PhaseController
from lib import utils


COLOR_CYCLE = [
    Color(0.0, 0.44705882, 0.69803922),
    Color(0.83529412, 0.36862745, 0.0),
    Color(0.0, 0.61960784, 0.45098039),
    Color(0.8, 0.4745098, 0.65490196),
    Color(0.94117647, 0.89411765, 0.25882353),
    Color(0.3372549, 0.70588235, 0.91372549),
]


ws_ids = ['RTBT_Diag:WS20', 'RTBT_Diag:WS21', 'RTBT_Diag:WS23', 'RTBT_Diag:WS24']
                

class GUI:
    
    def __init__(self, live=True):
        self.live = live
        self.phase_controller = PhaseController()

        # Main frame
        #------------------------------------------------------------------------
        self.frame = JFrame("RTBT Phase Controller")
        self.frame.setSize(Dimension(1000, 800))
        self.frame.getContentPane().setLayout(BorderLayout())
        time_text = DateAndTimeText()
        time_panel = JPanel(BorderLayout())
        time_panel.add(time_text.getTimeTextField(), BorderLayout.CENTER)
        self.frame.add(time_panel, BorderLayout.SOUTH)

        # Model calculation panel
        #------------------------------------------------------------------------
        # Labels
        ref_ws_id_label = JLabel('Ref. wire-scanner')
        energy_label = JLabel('Energy [GeV]')
        phase_coverage_label = JLabel('Phase coverage [deg]')
        n_steps_label = JLabel('Total steps')
        max_beta_label = JLabel("<html>Max. &beta; [m/rad]<html>")
        
        # Components
        text_field_width = 11
        self.ref_ws_id_dropdown = JComboBox(ws_ids)
        self.energy_text_field = JTextField('1.0', text_field_width)
        self.phase_coverage_text_field = JTextField('180.0', text_field_width)
        
        formatter = NumberFormat.getIntegerInstance()
        formatter.setGroupingUsed(False)
        self.n_steps_text_field = JFormattedTextField(formatter)
        self.n_steps_text_field.setValue(12)
        
        self.max_beta_text_field = JTextField('40.0', text_field_width)
        self.calculate_model_optics_button = JButton('Calculate model optics for scan')
        
        # Action listeners
        self.energy_text_field.addActionListener(EnergyTextFieldListener(self))
        self.ref_ws_id_dropdown.addActionListener(RefWsIdTextFieldListener(self))
        self.ref_ws_id_dropdown.setSelectedIndex(3)
        self.calculate_model_optics_button.addActionListener(CalculateModelOpticsButtonListener(self))
        
        # Build text fields panel
        self.model_calc_panel = AlignedLabeledComponentsPanel()
           
        self.model_calc_panel.add_row(ref_ws_id_label, self.ref_ws_id_dropdown)
        self.model_calc_panel.add_row(energy_label, self.energy_text_field)
        self.model_calc_panel.add_row(phase_coverage_label, self.phase_coverage_text_field)
        self.model_calc_panel.add_row(n_steps_label, self.n_steps_text_field)
        self.model_calc_panel.add_row(max_beta_label, self.max_beta_text_field)
    
        # Machine update panel
        #------------------------------------------------------------------------ 
        # Labels
        sleep_time_label = JLabel('Sleep time [s]')
        max_frac_change_label = JLabel('Max. frac. field change')
        scan_index_label = JLabel('Scan index')
        
        # Components        
        self.sleep_time_text_field = JTextField('0.5', text_field_width)
        self.max_frac_change_text_field = JTextField('0.01', text_field_width)
        self.set_optics_button = JButton('Set live optics')
        self.quad_settings_table = JTable(QuadSettingsTableModel(self))
        self.quad_settings_table.setShowGrid(True)
        
        n_steps = int(self.n_steps_text_field.getText())
        scan_indices = list(range(n_steps))
        self.scan_index_dropdown = JComboBox(scan_indices)
        
        # Action listeners
        self.n_steps_text_field.addActionListener(NStepsTextFieldListener(self))
        
        # Build panel
        self.machine_update_panel = JPanel()
        self.machine_update_panel.setLayout(BoxLayout(self.machine_update_panel, BoxLayout.Y_AXIS))
        temp_panel = AlignedLabeledComponentsPanel()
        temp_panel.add_row(sleep_time_label, self.sleep_time_text_field)
        temp_panel.add_row(max_frac_change_label, self.max_frac_change_text_field)  
        temp_panel.add_row(scan_index_label, self.scan_index_dropdown)
        self.machine_update_panel.add(temp_panel)
        self.machine_update_panel.add(self.set_optics_button)
        self.machine_update_panel.add(self.quad_settings_table.getTableHeader())
        self.machine_update_panel.add(self.quad_settings_table)
        
        
        # Build left panel
        #------------------------------------------------------------------------    
        self.left_panel = JPanel()
        self.left_panel.setLayout(BoxLayout(self.left_panel, BoxLayout.Y_AXIS))
        
        label = JLabel('Compute model')
        font = label.getFont()
        label.setFont(Font(font.name, font.BOLD, int(1.05 * font.size)));
        self.left_panel.add(label)
        
        self.left_panel.add(self.model_calc_panel)
        
        panel = JPanel()
        panel.add(self.calculate_model_optics_button)
        self.left_panel.add(panel)
        
        label = JLabel('Update machine')
        label.setFont(Font(font.name, font.BOLD, int(1.05 * font.size)));
        self.left_panel.add(label)
        
        self.left_panel.add(self.machine_update_panel)
        
        self.frame.add(self.left_panel, BorderLayout.WEST)
        
        # Plotting panels
        #------------------------------------------------------------------------
        self.beta_plot_panel = LinePlotPanel(
            xlabel='Position [m]', 
            ylabel='[m/rad]', 
            title='Model beta function vs. position',
            n_lines=2
        )
        self.phase_plot_panel = LinePlotPanel(
            xlabel='Position [m]', 
            ylabel='Phase adv. mod 2pi', 
            title='Model phase advance vs. position',
            n_lines=2
        )
        self.bpm_plot_panel = LinePlotPanel(xlabel='BPM', 
                                            ylabel='Amplitude [mm]', 
                                            title='BMP amplitudes',
                                            n_lines=2)
        self.right_panel = JPanel()
        self.right_panel.setLayout(BoxLayout(self.right_panel, BoxLayout.Y_AXIS))
        self.right_panel.add(self.beta_plot_panel)
        self.right_panel.add(self.phase_plot_panel)
        self.right_panel.add(self.bpm_plot_panel)
        self.frame.add(self.right_panel, BorderLayout.CENTER)   
        self.update_plots()
    
    def update_plots(self):
        betas_x, betas_y = [], []
        phases_x, phases_y = [], []
        for params in self.phase_controller.tracked_twiss():
            mu_x, mu_y, alpha_x, alpha_y, beta_x, beta_y, eps_x, eps_y = params
            betas_x.append(beta_x)
            betas_y.append(beta_y)
            phases_x.append(mu_x)
            phases_y.append(mu_y)
        positions = self.phase_controller.positions
        self.beta_plot_panel.set_data(positions, [betas_x, betas_y])
        self.phase_plot_panel.set_data(positions, [phases_x, phases_y])

    def launch(self):

        class WindowCloser(WindowAdapter):
            def __init__(self, phase_controller, field_set_kws, live=True):
                self.phase_controller = phase_controller
                self.field_set_kws = field_set_kws
                self.live = live
                
            def windowClosing(self, event):
                """Reset the real machine to its default state before closing window."""
                if self.live:
                    self.phase_controller.restore_default_optics('live', **self.field_set_kws)
                sys.exit(1)

        field_set_kws = {
            'sleep_time': float(self.sleep_time_text_field.getText()),
            'max_frac_change': float(self.max_frac_change_text_field.getText()),
        }
        self.frame.addWindowListener(WindowCloser(self.phase_controller, field_set_kws, self.live))
        self.frame.show()   
        
        
# Tables
#-------------------------------------------------------------------------------      
class QuadSettingsTableModel(AbstractTableModel):
    
    def __init__(self, gui):
        self.gui = gui
        self.phase_controller = gui.phase_controller
        self.column_names = ['Quad', 'Model [T/m]', 'Live [T/m]']
        self.nf4 = NumberFormat.getInstance()
        self.nf4.setMaximumFractionDigits(4)
        self.nf3 = NumberFormat.getInstance()
        self.nf3.setMaximumFractionDigits(3)

    def getValueAt(self, row, col):
        quad_id = self.phase_controller.ind_quad_ids[row]
        if col == 0:
            return quad_id
        elif col == 1:
            return self.phase_controller.get_field(quad_id, 'model')
        elif col == 2:
            return self.phase_controller.get_field(quad_id, 'live')
        
    def getColumnCount(self):
        return len(self.column_names)

    def getRowCount(self):
        return len(self.phase_controller.ind_quad_ids)
    
    def getColumnName(self, col):
        return self.column_names[col]
        
    
# Listeners
#-------------------------------------------------------------------------------
class EnergyTextFieldListener(ActionListener):
    """Update the beam kinetic energy from the text field; retrack; replot."""
    def __init__(self, gui):
        self.gui = gui
        self.text_field = gui.energy_text_field
        self.phase_controller = gui.phase_controller
        
    def actionPerformed(self, event):
        kin_energy = float(self.text_field.getText())
        if kin_energy < 0:
            raise ValueError('Kinetic energy must be postive.')
        self.phase_controller.set_kin_energy(kin_energy)
        self.phase_controller.track()
        self.gui.update_plots()
        print 'Updated kinetic energy to {:.3e} [eV]'.format(
            self.phase_controller.probe.getKineticEnergy())

        
class RefWsIdTextFieldListener(ActionListener):
    """Update the reference wire-scanner ID from the text field."""
    def __init__(self, gui):
        self.gui = gui
        self.dropdown = gui.ref_ws_id_dropdown
        self.phase_controller = gui.phase_controller
        
    def actionPerformed(self, event):
        self.phase_controller.ref_ws_id = self.dropdown.getSelectedItem()
        print 'Updated ref_ws_id to {}'.format(self.phase_controller.ref_ws_id)
        
        
class NStepsTextFieldListener(ActionListener):
    """Update a dropdown menu based on the n_steps text field."""
    def __init__(self, gui):
        self.gui = gui
    
    def actionPerformed(self, event):
        n_steps = float(self.gui.n_steps_text_field.getText())
        n_steps = int(n_steps)
        self.gui.scan_index_dropdown.removeAllItems()
        for scan_index in range(n_steps):
            self.gui.scan_index_dropdown.addItem(scan_index)
        
        
class CalculateModelOpticsButtonListener(ActionListener):
    """Calculate the model optics to obtain selected phase advances."""
    def __init__(self, gui):
        self.gui = gui
        self.phase_controller = gui.phase_controller
        
    def actionPerformed(self, event):
        # 1. Get the phase advances from the GUI.
        # 2. Run the solver.
        # 3. Print the output.
        raise NotImplementedError
            
    
# Plotting
#-------------------------------------------------------------------------------
class LinePlotPanel(JPanel):
    """Class for 2D line plots."""
    def __init__(self, xlabel='', ylabel='', title='', n_lines=2):
        self.setLayout(GridLayout(1, 1))
        etched_border = BorderFactory.createEtchedBorder()
        self.setBorder(etched_border)
        self.graph = FunctionGraphsJPanel()
        self.graph.setLegendButtonVisible(False)
        self.graph.setName(title)
        self.graph.setAxisNames(xlabel, ylabel)
        self.graph.setBorder(etched_border)
        self.graph.setGraphBackGroundColor(Color.white)
        self.graph.setGridLineColor(Color(245, 245, 245))
        self.add(self.graph)
        self.n_lines = n_lines
        self.data_list = [BasicGraphData() for _ in range(n_lines)]
        for data, color in zip(self.data_list, COLOR_CYCLE):
            data.setGraphColor(color)
            data.setLineThick(3)
            data.setGraphPointSize(0)

    def set_data(self, x, y_list):
        if len(utils.shape(y_list)) == 1:
            y_list = [y_list]
        self.graph.removeAllGraphData()
        for data, y in zip(self.data_list, y_list):
            data.addPoint(x, y)  
            self.graph.addGraphData(data)        
            
            

# Miscellaneous
#-------------------------------------------------------------------------------
class AlignedLabeledComponentsPanel(JPanel):
    
    def __init__(self):
        JPanel.__init__(self)
        self.layout = GroupLayout(self)
        self.setLayout(self.layout)
        self.layout.setAutoCreateContainerGaps(True)
        self.layout.setAutoCreateGaps(True)
        self.group_labels = self.layout.createParallelGroup()
        self.group_components = self.layout.createParallelGroup()
        self.group_rows = self.layout.createSequentialGroup()
        self.layout.setHorizontalGroup(self.layout.createSequentialGroup()
                                  .addGroup(self.group_labels)
                                  .addGroup(self.group_components))
        self.layout.setVerticalGroup(self.group_rows)

    def add_row(self, label, component):
        self.group_labels.addComponent(label)
        self.group_components.addComponent(component)
        self.group_rows.addGroup(
            self.layout.createParallelGroup()
                .addComponent(label)
                .addComponent(
                    component, 
                    GroupLayout.PREFERRED_SIZE, 
                    GroupLayout.DEFAULT_SIZE, 
                    GroupLayout.PREFERRED_SIZE
                )
        )
            
            
            
            
gui = GUI()
gui.launch()





# When model or live quads are updated: call table.getModel().fireTableDataChanged()