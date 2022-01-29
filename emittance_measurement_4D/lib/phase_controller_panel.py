"""This panel is to control the RTBT optics.

To do: add a panel that scans the model phase advances at WS24, then 
produces a heat map of the condition numbers and error/uncertainty
in emittances from Monte Carlo simulation, as in `sensitivity`
directory. Or could just have a button that runs the Monte Carlo
simulation once and prints the results to the terminal? Or just
display the condition number at all times in a text box?
"""
from __future__ import print_function
from java.awt import BorderLayout
from java.awt import Color
from java.awt import FlowLayout
from java.awt import Font
from java.awt.event import ActionListener
from javax.swing import BoxLayout
from javax.swing import GroupLayout
from javax.swing import JButton
from javax.swing import JComboBox
from javax.swing import JLabel
from javax.swing import JPanel
from javax.swing import JProgressBar
from javax.swing import JScrollPane
from javax.swing import JTable
from javax.swing import JTextField
from javax.swing import JFormattedTextField
from javax.swing.event import CellEditorListener
from javax.swing.table import AbstractTableModel
from java.text import NumberFormat

import optics
import plotting as plt
import utils


class PhaseControllerPanel(JPanel):

    def __init__(self):
        JPanel.__init__(self)
        self.setLayout(BorderLayout())
        self.phase_controller = optics.PhaseController(kinetic_energy=1e9)
        self.model_fields_list = []
        # Get the wire-scanner positions.
        self.ws_ids = optics.RTBT_WS_IDS
        self.sequence = self.phase_controller.sequence
        self.start_node = self.sequence.getNodeWithId('Begin_Of_RTBT1')
        self.ws_positions = []
        for ws_id in self.ws_ids:
            ws_node = self.sequence.getNodeWithId(ws_id)
            ws_position = self.sequence.getDistanceBetween(self.start_node, ws_node)
            self.ws_positions.append(ws_position)
        self.build_panels()

    def build_panels(self):
        # Model calculation panel
        #------------------------------------------------------------------------
        # Components
        text_field_width = 1
        self.ref_ws_id_dropdown = JComboBox(self.ws_ids)
        self.init_twiss_table = JTable(InitTwissTableModel(self))
        self.init_twiss_table.setShowGrid(True)
        self.energy_text_field = JTextField('1.0', text_field_width)
        self.phase_coverage_text_field = JTextField('30.0', text_field_width)
        formatter = NumberFormat.getIntegerInstance()
        formatter.setGroupingUsed(False)
        self.n_steps_text_field = JFormattedTextField(formatter)
        self.n_steps_text_field.setValue(10)
        self.scan_type_dropdown = JComboBox([1, 2])
        self.max_beta_text_field = JTextField('30.0', text_field_width)
        self.calculate_model_optics_button = JButton('Calculate model optics')

        # Action listeners
        self.energy_text_field.addActionListener(EnergyTextFieldListener(self))
        self.ref_ws_id_dropdown.addActionListener(RefWsIdDropdownListener(self))
        self.ref_ws_id_dropdown.setSelectedIndex(4)
        self.calculate_model_optics_button.addActionListener(CalculateModelOpticsButtonListener(self))
        self.init_twiss_table.getCellEditor(0, 0).addCellEditorListener(TwissTableListener(self))

        # Build panel
        self.model_calc_panel1 = AlignedLabeledComponentsPanel()
        self.model_calc_panel1.add_row(JLabel('Ref. wire-scanner'), self.ref_ws_id_dropdown)
        self.model_calc_panel2 = AlignedLabeledComponentsPanel()
        self.model_calc_panel2.add_row(JLabel('Energy [GeV]'), self.energy_text_field)
        self.model_calc_panel2.add_row(JLabel('Phase coverage [deg]'), self.phase_coverage_text_field)
        self.model_calc_panel2.add_row(JLabel("<html>Max. &beta; [m/rad]<html>"), self.max_beta_text_field)
        self.model_calc_panel2.add_row(JLabel('Steps in scan'), self.n_steps_text_field)
        self.model_calc_panel2.add_row(JLabel('Scan type'), self.scan_type_dropdown)

        self.model_calc_panel = JPanel()
        init_twiss_label = JLabel('Initial Twiss')
        init_twiss_label.setAlignmentX(0)
        self.model_calc_panel.add(init_twiss_label)
        self.model_calc_panel.add(self.init_twiss_table.getTableHeader())
        self.model_calc_panel.add(self.init_twiss_table)
        self.model_calc_panel.setLayout(BoxLayout(self.model_calc_panel, BoxLayout.Y_AXIS))
        self.model_calc_panel.add(self.model_calc_panel1)
        self.model_calc_panel.add(self.model_calc_panel2)

        # Machine update panel
        #------------------------------------------------------------------------
        # Components
        self.sleep_time_text_field = JTextField('0.5', 3)
        self.max_frac_change_text_field = JTextField('0.01', 4)
        self.set_live_optics_button1 = JButton('Set from scan')
        self.set_live_optics_button2 = JButton('Set manually ')
        self.quad_settings_table = JTable(QuadSettingsTableModel(self))
        self.quad_settings_table.setShowGrid(True)
        n_steps = int(self.n_steps_text_field.getText())
        self.scan_index_dropdown = JComboBox(['default'] + list(range(n_steps)))
        self.delta_mux_text_field = JTextField('0.0', 5)
        self.delta_muy_text_field = JTextField('0.0', 5)

        # Action listeners
        self.n_steps_text_field.addActionListener(NStepsTextFieldListener(self))
        self.set_live_optics_button1.addActionListener(SetLiveOpticsButton1Listener(self))
        self.set_live_optics_button2.addActionListener(SetLiveOpticsButton2Listener(self))

        # Build panel
        self.machine_update_panel = JPanel()
        self.machine_update_panel.setLayout(
            BoxLayout(self.machine_update_panel, BoxLayout.Y_AXIS))

        row = JPanel()
        row.setLayout(FlowLayout(FlowLayout.LEFT))
        row.add(JLabel('Sleep [s]'))
        row.add(self.sleep_time_text_field)
        row.add(JLabel('Max. frac. change'))
        row.add(self.max_frac_change_text_field)
        self.machine_update_panel.add(row)

        row = JPanel()
        row.setLayout(FlowLayout(FlowLayout.LEFT))
        row.add(self.set_live_optics_button1)
        row.add(JLabel('Scan index'))
        row.add(self.scan_index_dropdown)
        self.machine_update_panel.add(row)

        row = JPanel()
        row.setLayout(FlowLayout(FlowLayout.LEFT))
        row.add(self.set_live_optics_button2)
        row.add(JLabel("<html>&Delta&mu;<SUB>x</SUB> [deg]<html>"))
        row.add(self.delta_mux_text_field)
        row.add(JLabel("<html>&Delta&mu;<SUB>y</SUB> [deg]<html>"))
        row.add(self.delta_muy_text_field)
        self.machine_update_panel.add(row)

        self.machine_update_panel.add(self.quad_settings_table.getTableHeader())
        self.machine_update_panel.add(JScrollPane(self.quad_settings_table))

        # Build left panel
        #------------------------------------------------------------------------
        self.left_panel = JPanel()
        self.left_panel.setLayout(BoxLayout(self.left_panel, BoxLayout.Y_AXIS))

        label = JLabel('Compute model optics')
        font = label.getFont()
        label.setFont(Font(font.name, font.BOLD, int(1.1 * font.size)))
        temp_panel = JPanel()
        temp_panel.setLayout(FlowLayout(FlowLayout.LEFT))
        temp_panel.add(label)
        self.left_panel.add(temp_panel)

        self.left_panel.add(self.model_calc_panel)

        panel = JPanel()
        temp_panel = JPanel()
        temp_panel.add(self.calculate_model_optics_button)
        self.progress_bar = JProgressBar(0, int(self.n_steps_text_field.getText()))
        self.progress_bar.setValue(0)
        self.progress_bar.setStringPainted(True)
        temp_panel.add(self.progress_bar)
        panel.add(temp_panel)
        self.left_panel.add(panel)

        label = JLabel('Set live optics')
        label.setFont(Font(font.name, font.BOLD, int(1.1 * font.size)))
        row = JPanel()
        row.setLayout(FlowLayout(FlowLayout.LEFT))
        row.add(label)
        self.left_panel.add(row)
        self.left_panel.add(self.machine_update_panel)
        self.add(self.left_panel, BorderLayout.WEST)


        # Plotting panels
        #------------------------------------------------------------------------
        self.beta_plot_panel = plt.LinePlotPanel(
            xlabel='Position [m]', ylabel='[m/rad]',
            title='Beta function vs. position',
            n_lines=2, grid='y',
        )
        self.beta_plot_panel.setLimitsAndTicksY(0., 100., 10.)
        self.phase_plot_panel = plt.LinePlotPanel(
            xlabel='Position [m]', ylabel='Phase adv. mod 2pi [rad]',
            title='Phase advance vs. position',
            n_lines=2, grid='y',
        )
        self.bpm_plot_panel = plt.LinePlotPanel(
            xlabel='Position [m]', ylabel='Amplitude [mm]', title='BMP amplitudes',
            n_lines=2, lw=2, ms=5, grid='y',
        )

        # Get BPM positions
        self.bpms = self.phase_controller.sequence.getNodesOfType('BPM')
        seq = self.phase_controller.sequence
        start_node = seq.getNodes()[0]
        self.bpm_positions = [seq.getDistanceBetween(start_node, node) for node in self.bpms]

        # Add the plots to the panel.
        self.right_panel = JPanel()
        self.right_panel.setLayout(BoxLayout(self.right_panel, BoxLayout.Y_AXIS))
        self.right_panel.add(self.beta_plot_panel)
        self.right_panel.add(self.phase_plot_panel)
        self.right_panel.add(self.bpm_plot_panel)
        self.add(self.right_panel, BorderLayout.CENTER)
        self.update_plots()

    def read_bpms(self):
        x_avgs = list([bpm.getXAvg() for bpm in self.bpms])
        y_avgs = list([bpm.getYAvg() for bpm in self.bpms])
        return x_avgs, y_avgs

    def update_plots(self):
        # Plot model beta functions and phase advances.
        betas_x, betas_y = [], []
        phases_x, phases_y = [], []
        self.phase_controller.track()
        for params in self.phase_controller.tracked_twiss():
            mu_x, mu_y, alpha_x, alpha_y, beta_x, beta_y, eps_x, eps_y = params
            betas_x.append(beta_x)
            betas_y.append(beta_y)
            phases_x.append(mu_x)
            phases_y.append(mu_y)
        positions = self.phase_controller.positions
        self.beta_plot_panel.set_data(positions, [betas_x, betas_y])
        self.phase_plot_panel.set_data(positions, [phases_x, phases_y])
        
        # Plot BPM readings.
        x_avgs, y_avgs = self.read_bpms()
        self.bpm_plot_panel.set_data(self.bpm_positions, [x_avgs, y_avgs])

        # Add a vertical line at each wire-scanner locations.
        ref_ws_index = self.ws_ids.index(self.ref_ws_id_dropdown.getSelectedItem())
        for plot_panel in [self.beta_plot_panel, self.phase_plot_panel, self.bpm_plot_panel]:
            for i, ws_position in enumerate(self.ws_positions):
                color = Color(150, 150, 150) if i == ref_ws_index else Color(225, 225, 225)
                plot_panel.addVerticalLine(ws_position, color)

    def get_field_set_kws(self):
        field_set_kws = {
            'sleep_time': float(self.sleep_time_text_field.getText()),
            'max_frac_change': float(self.max_frac_change_text_field.getText()),
        }
        return field_set_kws


# Tables
#-------------------------------------------------------------------------------
class QuadSettingsTableModel(AbstractTableModel):

    def __init__(self, panel):
        self.panel = panel
        self.phase_controller = panel.phase_controller
        self.quad_ids = self.phase_controller.ind_quad_ids
        self.column_names = ['Quad', 'Model [T/m]', 'Live [T/m]']
        self.nf4 = NumberFormat.getInstance()
        self.nf4.setMaximumFractionDigits(4)
        self.nf3 = NumberFormat.getInstance()
        self.nf3.setMaximumFractionDigits(3)

    def getValueAt(self, row, col):
        quad_id = self.quad_ids[row]
        if col == 0:
            return quad_id
        elif col == 1:
            return self.phase_controller.get_field(quad_id, 'model')
        elif col == 2:
            return self.phase_controller.get_field(quad_id, 'live')

    def getColumnCount(self):
        return len(self.column_names)

    def getRowCount(self):
        return len(self.quad_ids)

    def getColumnName(self, col):
        return self.column_names[col]


class InitTwissTableModel(AbstractTableModel):

    def __init__(self, panel):
        self.panel = panel
        self.phase_controller = panel.phase_controller
        self.column_names = [
            "<html>&alpha;<SUB>x</SUB> [m/rad]<html>",
            "<html>&alpha;<SUB>y</SUB> [m/rad]<html>",
            "<html>&beta;<SUB>x</SUB> [m/rad]<html>",
            "<html>&beta;<SUB>y</SUB> [m/rad]<html>"
        ]

    def getValueAt(self, row, col):
        if col == 0:
            return self.phase_controller.init_twiss['alpha_x']
        elif col == 1:
            return self.phase_controller.init_twiss['alpha_y']
        elif col == 2:
            return self.phase_controller.init_twiss['beta_x']
        elif col == 3:
            return self.phase_controller.init_twiss['beta_y']

    def getColumnCount(self):
        return len(self.column_names)

    def getRowCount(self):
        return 1

    def getColumnName(self, col):
        return self.column_names[col]

    def isCellEditable(self, row, col):
        return True


# Listeners
#-------------------------------------------------------------------------------
class EnergyTextFieldListener(ActionListener):

    def __init__(self, panel):
        self.panel = panel
        self.text_field = panel.energy_text_field
        self.phase_controller = panel.phase_controller

    def actionPerformed(self, event):
        kin_energy = 1e9 * float(self.text_field.getText())
        if kin_energy < 0.0:
            raise ValueError('Kinetic energy must be positive.')
        self.phase_controller.set_kinetic_energy(kin_energy)
        self.panel.init_twiss_table.getModel().fireTableDataChanged()
        self.phase_controller.track()
        self.panel.update_plots()
        print('Updated kinetic energy to {:.3e} [eV]'.format(
              self.phase_controller.probe.getKineticEnergy()))


class RefWsIdDropdownListener(ActionListener):

    def __init__(self, panel):
        self.panel = panel
        self.dropdown = panel.ref_ws_id_dropdown
        self.phase_controller = panel.phase_controller

    def actionPerformed(self, event):
        self.phase_controller.ref_ws_id = self.dropdown.getSelectedItem()
        if hasattr(self.panel, 'right_panel'):
            self.panel.update_plots()
        print('Updated ref_ws_id to {}'.format(self.phase_controller.ref_ws_id))


class NStepsTextFieldListener(ActionListener):

    def __init__(self, panel):
        self.panel = panel

    def actionPerformed(self, event):
        n_steps = float(self.panel.n_steps_text_field.getText())
        n_steps = int(n_steps)
        self.panel.scan_index_dropdown.removeAllItems()
        self.panel.scan_index_dropdown.addItem('default')
        for scan_index in range(n_steps):
            self.panel.scan_index_dropdown.addItem(scan_index)


class TwissTableListener(CellEditorListener):

    def __init__(self, panel):
        self.panel = panel
        self.phase_controller = panel.phase_controller
        self.table = panel.init_twiss_table
        self.cell_editor = self.table.getCellEditor(0, 0)

    def editingStopped(self, event):
        value = float(self.cell_editor.getCellEditorValue())
        col = self.table.getSelectedColumn()
        key = ['alpha_x', 'alpha_y', 'beta_x', 'beta_y'][col]
        self.phase_controller.init_twiss[key] = value
        self.table.getModel().fireTableDataChanged()
        self.phase_controller.track()
        self.panel.update_plots()
        print('Updated initial Twiss:', self.phase_controller.init_twiss)


class CalculateModelOpticsButtonListener(ActionListener):

    def __init__(self, panel):
        self.panel = panel
        self.phase_controller = panel.phase_controller
        self.ind_quad_ids = self.phase_controller.ind_quad_ids

    def actionPerformed(self, event):
        """Calculate/store correct optics settings for each step in the scan."""
        self.panel.model_fields_list = []

        # Start from the default optics.
        self.phase_controller.restore_default_optics('model')
        self.phase_controller.track()

        # Make a list of phase advances.
        phase_coverage = float(self.panel.phase_coverage_text_field.getText())
        n_steps = int(self.panel.n_steps_text_field.getText())
        max_beta = float(self.panel.max_beta_text_field.getText())
        beta_lims = (max_beta, max_beta)
        scan_type = self.panel.scan_type_dropdown.getSelectedItem()
        phases = self.phase_controller.get_phases_for_scan(phase_coverage, n_steps, scan_type)
        print('index | mu_x  | mu_y [rad]')
        print('---------------------')
        for scan_index, (mu_x, mu_y) in enumerate(phases):
            print('{:<5} | {:.3f} | {:.3f}'.format(scan_index, mu_x, mu_y))

        # Compute the optics needed for step in the scan.
        self.panel.progress_bar.setValue(0)
        self.panel.progress_bar.setMaximum(n_steps)

        for scan_index, (mu_x, mu_y) in enumerate(phases):
            # Set the model optics.
            print('Scan index = {}/{}.'.format(scan_index, n_steps - 1))
            print('Setting phases at {}...'.format(self.phase_controller.ref_ws_id))
            self.phase_controller.set_ref_ws_phases(mu_x, mu_y, beta_lims, verbose=1)

            # Constrain beam size on target if it's too far from the default.
            beta_x_target, beta_y_target = self.phase_controller.beta_funcs('RTBT:Tgt')
            beta_x_default, beta_y_default = self.phase_controller.default_betas_at_target
            frac_change_x = abs(beta_x_target - beta_x_default) / beta_x_default
            frac_change_y = abs(beta_y_target - beta_y_default) / beta_y_default
            tol = 0.05
            if frac_change_x > tol or frac_change_y > tol:
                print('Setting betas at target...')
                self.phase_controller.constrain_size_on_target(verbose=1)
            max_betas_anywhere = self.phase_controller.max_betas(stop=None)
            print('  Max betas anywhere: {:.3f}, {:.3f}.'.format(*max_betas_anywhere))

            # Save the model quadrupole strengths.
            model_fields = []
            for quad_id in self.ind_quad_ids:
                field = self.phase_controller.get_field(quad_id, 'model')
                model_fields.append(field)

            # Store the model fields.
            self.panel.model_fields_list.append(model_fields)

            # Update the panel progress bar. (This doesn't work currently;
            # we would need to run on a separate thread.)
            self.panel.progress_bar.setValue(scan_index + 1)
            print()

        # Put the model back to its original state.
        self.phase_controller.restore_default_optics('model')
        self.phase_controller.track()


class SetLiveOpticsButton1Listener(ActionListener):

    def __init__(self, panel):
        self.panel = panel
        self.phase_controller = panel.phase_controller
        self.ind_quad_ids = self.phase_controller.ind_quad_ids

    def actionPerformed(self, action):
        quad_ids = self.phase_controller.ind_quad_ids
        field_set_kws = self.panel.get_field_set_kws()
        scan_index = self.panel.scan_index_dropdown.getSelectedItem()
        print('Syncing live quads with model...')
        print(field_set_kws)
        if scan_index == 'default':
            self.phase_controller.restore_default_optics('model')
            self.phase_controller.restore_default_optics('live')
        else:
            scan_index = int(scan_index)
            fields = self.panel.model_fields_list[scan_index]
            self.phase_controller.set_fields(quad_ids, fields, 'model')
            self.phase_controller.set_fields(quad_ids, fields, 'live', **field_set_kws)
        self.panel.quad_settings_table.getModel().fireTableDataChanged()
        self.panel.update_plots()
        print('Done.')


class SetLiveOpticsButton2Listener(ActionListener):

    def __init__(self, panel):
        self.panel = panel
        self.phase_controller = panel.phase_controller
        self.ind_quad_ids = self.phase_controller.ind_quad_ids

    def actionPerformed(self, action):
        # Set the phase advance at the reference wire-scanner.
        self.phase_controller.restore_default_optics('model')
        self.phase_controller.track()
        mux0, muy0 = self.phase_controller.phases(self.phase_controller.ref_ws_id)
        delta_mux = utils.radians(float(self.panel.delta_mux_text_field.getText()))
        delta_muy = utils.radians(float(self.panel.delta_muy_text_field.getText()))
        mux = utils.put_angle_in_range(mux0 + delta_mux)
        muy = utils.put_angle_in_range(muy0 + delta_muy)
        print('mux0, muy0 = {}, {} [deg]'.format(utils.degrees(mux0), utils.degrees(muy0)))
        print('mux, muy = {}, {} [deg]'.format(utils.degrees(mux), utils.degrees(muy)))
        print('Setting model phase advances...')
        self.phase_controller.set_ref_ws_phases(mux, muy, verbose=2)
        
        # Constrain the beam size on the target if it's too far from the default.
        beta_x_target, beta_y_target = self.phase_controller.beta_funcs('RTBT:Tgt')
        beta_x_default, beta_y_default = self.phase_controller.default_betas_at_target
        frac_change_x = abs(beta_x_target - beta_x_default) / beta_x_default
        frac_change_y = abs(beta_y_target - beta_y_default) / beta_y_default
        tol = 0.05
        if frac_change_x > tol or frac_change_y > tol:
            print('Setting betas at target...')
            self.phase_controller.constrain_size_on_target(verbose=1)
        max_betas_anywhere = self.phase_controller.max_betas(stop=None)
        print('  Max betas anywhere: {:.3f}, {:.3f}.'.format(*max_betas_anywhere))

        # Sync the live optics with the model.
        print('Syncing live quads with model...')
        field_set_kws = self.panel.get_field_set_kws()
        print(field_set_kws)
        self.phase_controller.sync_live_with_model(**field_set_kws)
        self.panel.quad_settings_table.getModel().fireTableDataChanged()
        self.panel.update_plots()
        print('Done.')


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
        self.layout.setHorizontalGroup(
            self.layout.createSequentialGroup()
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
