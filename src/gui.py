import sys
import os
import numpy as np

from time import sleep, time
from PyQt6.QtCore import (
    Qt,
    QRunnable,
    QThreadPool,
    QObject,
    pyqtSignal,
    QSize
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QLineEdit,
    QPushButton,
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QCheckBox,
    QScrollArea,
    QTabWidget,
    QFrame,
    QSpacerItem,
    QDialog, QDialogButtonBox
)
from PyQt6.QtGui import (
    QAction,
    QFont,
    QPixmap
)

from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as QPltToolbar

from exceptions import PointNotDefinedException, InvalidParamsException
from psychrometric_calc import PsychrometricProperties, find_humidity_ratio_from_RH_temp
from unit_converter import convert_units, unit_equivalents
from components.load_cell import LoadCellArray
from components.sht45 import RHTSensorArray, SHT45
from plot import QMassPltCanvas, QPsychroPltCanvas


class QInputBox(QLineEdit):
    def __init__(self, property_name, *args, **kwargs):
        super(QLineEdit, self).__init__(*args, **kwargs)

        self.property_name = property_name


class QRCodeDlg(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('SOP QR Code')

        QBtn = QDialogButtonBox.StandardButton.Close
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.close.connect(self.close)

        self.layout = QVBoxLayout()
        qr_code = QLabel()
        qr_code_pixmap = QPixmap('home/admin/DesiGators/src/assets/qr_code.png')
        qr_code_pixmap = qr_code_pixmap.scaledToHeight(100, mode=Qt.TransformationMode.SmoothTransformation)
        qr_code.setPixmap(qr_code_pixmap)
        self.layout.addWidget(qr_code)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)


class MassSignals(QObject):
    """Signals associated with mass updating worker
    finished signal has no associated type

    result signal is a list of all the masses in LoadCellArray order
    """

    finished = pyqtSignal()
    error = pyqtSignal()
    result = pyqtSignal(list)


class RHTSignals(QObject):
    """Signals associated with the RHT updating worker. Works
    in the same way as the MassUpdater class.
    """

    finished = pyqtSignal()
    error = pyqtSignal()
    result = pyqtSignal(list)


class CoordinatorSignals(QObject):
    read = pyqtSignal()


class MeasurementCoordinator(QRunnable):
    def __init__(self, _cell_array: LoadCellArray, _sensor_array: RHTSensorArray, controls, interval: int = 10):
        super(MeasurementCoordinator, self).__init__()
        self.signals = CoordinatorSignals()
        self.rht_signals = RHTSignals()
        self.mass_signals = MassSignals()
        self.rht_array = _sensor_array
        self.mass_array = _cell_array
        self.interval = interval
        self.controls = controls

    def run(self):
        while True:
            if not self.controls['measure']:
                break
            else:
                measurement_start_time = time()
                try:
                    rht_readings = self.rht_array.take_measurement()
                except Exception as e:
                    print(e)
                    continue

                self.rht_signals.result.emit(rht_readings)

                mass_readings = self.mass_array.take_measurement()
                mass_readings.insert(0, time())
                self.mass_signals.result.emit(mass_readings)

                measurement_stop_time = time()
                time_elapsed = measurement_stop_time - measurement_start_time
                if time_elapsed < self.interval:
                    sleep(self.interval - time_elapsed)
                self.signals.read.emit()


class UnitConverterWindow(QWidget):
    def __init__(self, parent):
        super().__init__()

        self.setWindowTitle("Unit Converter")

        self.parent = parent

        # Define row layouts (rows ordered top to bottom)
        row_one_layout = QHBoxLayout()
        row_two_layout = QHBoxLayout()
        row_three_layout = QHBoxLayout()

        # Building row one (row to include title/large label and value dropdown)
        header_label = QLabel("Heading")

        self.value_type_dropdown = QComboBox()
        self.value_type_dropdown.addItems(['Select a value type', 'Mass', 'Volume', 'Temperature', 'Pressure',
                                           'Mass Flow Rate', 'Volumetric Flow Rate', 'Energy', 'Power',
                                           'Specific Enthalpy', 'Specific Heat Capacity'])
        self.value_type_dropdown.currentIndexChanged.connect(self.value_type_dropdown_index_changed)

        row_one_layout.addWidget(header_label)
        row_one_layout.addWidget(self.value_type_dropdown)

        # Building row two (row to include two input boxes, two dropdowns, and flip button)
        self.known_value_line_edit = QLineEdit()

        self.known_value_dropdown = QComboBox()
        self.known_value_dropdown.addItem("Select a value type above")

        flip_button = QPushButton('\u21D4')
        flip_button.setFont(QFont('Times', 16))
        flip_button.clicked.connect(self.flip_clicked)

        self.calc_value_line_edit = QLineEdit()
        self.calc_value_line_edit.setReadOnly(True)

        self.calc_value_dropdown = QComboBox()
        self.calc_value_dropdown.addItem("Select a value type above")

        row_two_layout.addWidget(self.known_value_line_edit)
        row_two_layout.addWidget(self.known_value_dropdown)
        row_two_layout.addWidget(flip_button)
        row_two_layout.addWidget(self.calc_value_line_edit)
        row_two_layout.addWidget(self.calc_value_dropdown)

        # Building row three (row to include spacers and calculate button)
        calculate_button = QPushButton("Calculate")
        calculate_button.clicked.connect(self.calculate_clicked)

        row_three_layout.addWidget(calculate_button)

        # Add together rows to make window layout
        layout = QVBoxLayout()
        layout.addLayout(row_one_layout)
        layout.addLayout(row_two_layout)
        layout.addLayout(row_three_layout)

        self.setLayout(layout)

    def calculate_clicked(self) -> None:
        value_type = self.value_type_dropdown.currentText()
        unit_a = self.known_value_dropdown.currentText()
        unit_b = self.calc_value_dropdown.currentText()
        try:
            value_a = float(self.known_value_line_edit.text())
        except ValueError as e:
            print(e)
            return

        value_b = convert_units(value_type, unit_a, unit_b, value_a)
        self.calc_value_line_edit.setText("{:.3f}".format(value_b))

    def value_type_dropdown_index_changed(self, index) -> list:
        units = None

        if self.value_type_dropdown.itemText(0) == 'Select a value type':
            self.value_type_dropdown.removeItem(0)
            index -= 1

        units = [unit for unit in unit_equivalents[self.value_type_dropdown.currentText()]]

        # if index == 0:
        #     # Mass
        #     units = [unit for unit in unit_equivalents['Mass']]
        # elif index == 1:
        #     # Volume
        #     units = ['ft³', 'm³', 'L', 'mL', 'butt', 'hogsheads']
        # elif index == 2:
        #     # Temperature
        #     units = [chr(176) + 'C', chr(176) + 'F', 'K', chr(176) + 'R', ]
        # elif index == 3:
        #     # Pressure
        #     units = ['Pa', 'psi', 'mmHg', 'atm', 'bar', 'torr', 'beard-second-black-hole']
        # elif index == 4:
        #     # Mass Flow Rate
        #     units = ['kg/s', 'lb/s']
        # elif index == 5:
        #     # Volumetric Flow Rate
        #     units = ['SCFM', 'SCFH', 'SLPM', 'm³/h']
        # elif index == 6:
        #     # Energy
        #     units = ['J', 'kJ', 'kWh', 'Btu', 'kcal', 'keV']
        # elif index == 7:
        #     # Power
        #     units = ['W', 'kW', 'hp', 'dp', 'Btu/h', 'RT']
        # elif index == 8:
        #     # Specific Enthalpy
        #     units = ['kJ/kg', 'Btu/lbm']
        # elif index == 9:
        #     # Specific Heat Capacity
        #     units = ['kJ/kg\u00B7K', 'Btu/lbm\u00B7\u00B0R']

        self.known_value_dropdown.clear()
        self.known_value_dropdown.addItems(units)

        self.calc_value_dropdown.clear()
        self.calc_value_dropdown.addItems(units)

        return units

    def flip_clicked(self) -> None:
        calc_value = self.calc_value_line_edit.text()

        self.known_value_line_edit.setText(calc_value)
        self.calc_value_line_edit.setText("")

        known_unit_index = self.known_value_dropdown.currentIndex()
        calc_unit_index = self.calc_value_dropdown.currentIndex()
        self.known_value_dropdown.setCurrentIndex(calc_unit_index)
        self.calc_value_dropdown.setCurrentIndex(known_unit_index)

    def closeEvent(self, event):
        # Override the closeEvent method that exists and replace with controls editing to exit ongoing threads
        self.parent.controls['converter_shown'] = False
        event.accept()


class PsychrometricCalculatorWindow(QWidget):
    def __init__(self, parent):
        super().__init__()

        self.setWindowTitle("Psychrometric Calculator")
        self.parent = parent

        params_layout = QVBoxLayout()

        # Create the parameter rows
        param_row_layouts_list = [pressure_layout := QHBoxLayout(),
                                  dry_bulb_layout := QHBoxLayout(),
                                  wet_bulb_layout := QHBoxLayout(),
                                  dew_point_layout := QHBoxLayout(),
                                  relative_humidity_layout := QHBoxLayout(),
                                  humidity_ratio_layout := QHBoxLayout(),
                                  partial_pressure_layout := QHBoxLayout(),
                                  total_enthalpy_layout := QHBoxLayout(),
                                  specific_heat_layout := QHBoxLayout(),
                                  specific_volume_layout := QHBoxLayout()]

        param_widgets_list = []
        unit_widgets_list = []

        # List all the psychrometric parameters in order (this order must be maintained)
        params = ['Total Pressure',
                  'Dry Bulb Temp',
                  'Wet Bulb Temp',
                  'Dew Point',
                  'Relative Humidity',
                  'Humidity Ratio',
                  'Partial Vapor Pressure',
                  'Total Enthalpy',
                  'Specific Heat',
                  'Specific Volume']

        # List all the units of the corresponding psychrometric parameters
        units = ['Pa',
                 chr(176) + 'C',
                 chr(176) + 'C',
                 chr(176) + 'C',
                 '%',
                 'kg water/kg dry air',
                 'Pa',
                 'kJ/kg dry air',
                 'kJ/kg*K',
                 'm^3/kg']

        # Create param labels
        for label in params:
            label_widget = QLabel(label)
            param_widgets_list.append(label_widget)

        # Create unit labels
        for label in units:
            label_widget = QLabel(label)
            unit_widgets_list.append(label_widget)

        # Create input boxes for each param
        self.total_pressure_input = QInputBox('total_pressure')
        self.dry_bulb_input = QInputBox('dry_bulb_temperature')
        self.wet_bulb_input = QInputBox('wet_bulb_temperature')
        self.dew_point_input = QInputBox('dew_point_temperature')
        self.relative_humidity_input = QInputBox('relative_humidity')
        self.humidity_ratio_input = QInputBox('humidity_ratio')
        self.vapor_pressure_input = QInputBox('partial_pressure_vapor')
        self.enthalpy_input = QInputBox('total_enthalpy')
        self.specific_heat_input = QInputBox('specific_heat_capacity')
        self.specific_vol_input = QInputBox('specific_volume')

        self.input_boxes = [self.total_pressure_input,
                            self.dry_bulb_input,
                            self.wet_bulb_input,
                            self.dew_point_input,
                            self.relative_humidity_input,
                            self.humidity_ratio_input,
                            self.vapor_pressure_input,
                            self.enthalpy_input,
                            self.specific_heat_input,
                            self.specific_vol_input]

        # Create row layouts for each parameter
        for i in range(len(param_row_layouts_list)):
            # Add 1. parameter name QLabel, 2. parameter QLineEdit, 3. parameter units QLabel
            param_widgets_list[i].setFixedWidth(130)
            param_row_layouts_list[i].addWidget(param_widgets_list[i])
            self.input_boxes[i].setFixedWidth(100)
            param_row_layouts_list[i].addWidget(self.input_boxes[i])
            unit_widgets_list[i].setFixedWidth(120)
            param_row_layouts_list[i].addWidget(unit_widgets_list[i])

            # Add parameter row to column on the left
            params_layout.addLayout(param_row_layouts_list[i])

        output_controls_layout = QVBoxLayout()

        calculate_button = QPushButton("Calculate")
        calculate_button.clicked.connect(self.calculate_clicked)

        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.clear_clicked)

        self.output_box = QLabel()
        self.output_box.setStyleSheet("border: 2px solid black;")

        output_controls_layout.addWidget(self.output_box)
        output_controls_layout.addWidget(calculate_button)
        output_controls_layout.addWidget(clear_button)

        layout = QHBoxLayout()
        layout.addLayout(params_layout, 75)
        layout.addLayout(output_controls_layout, 25)

        self.setLayout(layout)

    def calculate_clicked(self):
        self.output_box.setText("")

        params_dict = {'dry_bulb_temperature': None,
                       'wet_bulb_temperature': None,
                       'dew_point_temperature': None,
                       'total_pressure': None,
                       'humidity_ratio': None,
                       'relative_humidity': None,
                       'total_enthalpy': None,
                       'partial_pressure_vapor': None,
                       'specific_volume': None,
                       'specific_heat_capacity': None}

        for input_box in self.input_boxes:
            if input_box.text() != "":
                if input_box.property_name == 'relative_humidity':
                    params_dict['relative_humidity'] = float(input_box.text()) / 100
                else:
                    params_dict[input_box.property_name] = float(input_box.text())

        psy_point = None
        try:
            psy_point = PsychrometricProperties(**params_dict)
        except PointNotDefinedException:
            self.output_box.setText("Not enough information provided.")
        except InvalidParamsException as exception:
            self.output_box.setText(exception.message)

        if psy_point is not None:
            for input_box in self.input_boxes:
                if input_box.text() == "":
                    if input_box.property_name == 'dry_bulb_temperature':
                        input_box.setText(str(round(psy_point.dry_bulb_temperature, 2)))
                    elif input_box.property_name == 'wet_bulb_temperature':
                        input_box.setText(str(round(psy_point.wet_bulb_temperature, 2)))
                    elif input_box.property_name == 'dew_point_temperature':
                        input_box.setText(str(round(psy_point.dew_point_temperature, 2)))
                    elif input_box.property_name == 'total_pressure':
                        input_box.setText(str(round(psy_point.total_pressure, 2)))
                    elif input_box.property_name == 'humidity_ratio':
                        input_box.setText(str(round(psy_point.humidity_ratio, 5)))
                    elif input_box.property_name == 'relative_humidity':
                        input_box.setText(str(round(psy_point.relative_humidity * 100, 2)))
                    elif input_box.property_name == 'total_enthalpy':
                        input_box.setText(str(round(psy_point.total_enthalpy, 3)))
                    elif input_box.property_name == 'partial_pressure_vapor':
                        input_box.setText(str(round(psy_point.partial_pressure_vapor, 2)))
                    elif input_box.property_name == 'specific_volume':
                        input_box.setText(str(round(psy_point.specific_volume, 2)))
                    elif input_box.property_name == 'specific_heat_capacity':
                        input_box.setText(str(round(psy_point.specific_heat_capacity, 2)))

            self.output_box.setText("Calculated!")

    def clear_clicked(self):
        for input_box in self.input_boxes:
            input_box.setText("")
        self.output_box.setText("Cleared!")

    def closeEvent(self, event):
        # Override the closeEvent method that exists and replace with controls editing to exit ongoing threads
        self.parent.controls['calc_shown'] = False
        event.accept()


class ChamberTabPage(QWidget):
    def __init__(self, mainwindow, num):
        super().__init__()
        self.mainwindow = mainwindow  # Import is used for communication with AppWindow processes
        self.num = num

        layout = QHBoxLayout()
        self.setLayout(layout)

        # Create two main columns
        left_layout = QVBoxLayout()  # left_layout contains psychro plot
        right_layout = QVBoxLayout()  # right_layout contains three boxes controls on top, then current operating
        # conditions, then log with warnings/errors

        # Define left_layout
        psychro_layout = QVBoxLayout()
        self.psychro_plot = QPsychroPltCanvas(self)
        self._psychro_plot_ref_in = None
        self._psychro_plot_ref_out = None
        self.psychro_plot.axes.set_title('Psychrometric Chart (P=%i Pa)' % int(self.psychro_plot.total_pressure))
        psychro_toolbar = QPltToolbar(self.psychro_plot, self)

        psychro_layout.addWidget(psychro_toolbar)
        psychro_layout.addWidget(self.psychro_plot)

        left_layout.addLayout(psychro_layout)

        # Define right_layout
        # Define and add controls box
        controls_box = QWidget()
        controls_box.setObjectName('controls_box')
        controls_box.setStyleSheet("QWidget#controls_box {border: 2px solid black;}")
        controls_box_layout = QVBoxLayout()
        controls_box.setLayout(controls_box_layout)

        heater_control_layout = QHBoxLayout()
        heater_control_layout.setSpacing(5)
        heater_control_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        heater_checkbox = QCheckBox()
        heater_label = QLabel('Heater On')
        heater_control_layout.addWidget(heater_checkbox)
        heater_control_layout.addWidget(heater_label)

        record_control_layout = QHBoxLayout()
        record_control_layout.setSpacing(5)
        record_control_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.record_checkbox = QCheckBox()
        self.record_checkbox.stateChanged.connect(self.record_checked)
        record_label = QLabel('Recording')
        record_control_layout.addWidget(self.record_checkbox)
        record_control_layout.addWidget(record_label)

        controls_box_layout.addLayout(heater_control_layout)
        controls_box_layout.addLayout(record_control_layout)

        right_layout.addWidget(controls_box)

        # Define and add operating conditions box
        conditions_box = QWidget()
        conditions_box.setObjectName('conditions_box')
        conditions_box.setStyleSheet("QWidget#conditions_box {border: 2px solid black;}")
        conditions_box_layout = QHBoxLayout()
        conditions_box.setLayout(conditions_box_layout)

        self.conditions_1 = QLabel('Operating Conditions 1')
        conditions_box_layout.addWidget(self.conditions_1)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setLineWidth(2)
        conditions_box_layout.addWidget(separator)
        self.conditions_2 = QLabel('Operating Conditions 2')
        conditions_box_layout.addWidget(self.conditions_2)

        right_layout.addWidget(conditions_box)

        # Define and add log box
        log_box = QScrollArea()
        log_box.setObjectName('log_box')
        log_box.setStyleSheet("QWidget#log_box {border: 2px solid black;}")
        self.log_label = QLabel('See terminal for log.')
        log_box.setWidget(self.log_label)

        right_layout.addWidget(log_box)

        # Define and add mass plot with toolbar
        mass_layout = QVBoxLayout()
        self.mass_plot = QMassPltCanvas(self)
        self._mass_plot_ref = None
        self.mass_plot.axes.set(title='Mass', xlabel='Time Elapsed [s]', ylabel='Mass [g]')
        mass_toolbar = QPltToolbar(self.mass_plot, self)

        mass_layout.addWidget(mass_toolbar)
        mass_layout.addWidget(self.mass_plot)

        right_layout.addLayout(mass_layout)

        # Add both layouts together
        layout.addLayout(left_layout, 3)
        layout.addLayout(right_layout, 1)

    def record_checked(self, checked) -> None:
        print("\'record_checked\' called.")
        if checked == 2:
            checked_bool = True
        else:
            checked_bool = False
        self.mainwindow.controls['measure'] = checked_bool
        self.mainwindow.measurement_clicked()


class HomePageTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Home page should look like (from top to bottom):
        # Title
        # Logo
        # Subtitle
        # (Lower left hand corner) Logos for IPPD & FSHN
        # (Lower right hand corner) Credits

        title_label = QLabel('Welcome, DesiGators', alignment=Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont('Arial', 15))

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_pixmap = QPixmap('home/admin/DesiGators/src/assets/desigators_logo.jpg')
        logo_pixmap = logo_pixmap.scaledToHeight(90, mode=Qt.TransformationMode.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)

        subtitle_label = QLabel('Subtitle', alignment=Qt.AlignmentFlag.AlignCenter)

        # Add a row on the bottom for creator names and relevant logos
        credits_layout = QHBoxLayout()
        ippd_logo_label = QLabel(alignment=Qt.AlignmentFlag.AlignLeft)
        ippd_logo_pixmap = QPixmap('home/admin/DesiGators/src/assets/ippd_logo.jpg')
        ippd_logo_pixmap = ippd_logo_pixmap.scaledToHeight(45, mode=Qt.TransformationMode.SmoothTransformation)
        ippd_logo_label.setPixmap(ippd_logo_pixmap)

        fshn_logo_label = QLabel(alignment=Qt.AlignmentFlag.AlignLeft)
        fshn_logo_pixmap = QPixmap('home/admin/DesiGators/src/assets/fshn_logo.jpg')
        fshn_logo_pixmap = fshn_logo_pixmap.scaledToHeight(45, mode=Qt.TransformationMode.SmoothTransformation)
        fshn_logo_label.setPixmap(fshn_logo_pixmap)

        credits_label = QLabel('Credits: Virginia Covert, Korynn Haetten,\nStanley Moonjeli, Alexander Weaver',
                               alignment=Qt.AlignmentFlag.AlignRight)

        credits_layout.addWidget(ippd_logo_label)
        credits_layout.addWidget(fshn_logo_label)
        credits_layout.addWidget(credits_label)

        layout.addWidget(title_label)
        layout.addWidget(logo_label)
        layout.addWidget(subtitle_label)
        layout.addLayout(credits_layout)


class AppWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super(AppWindow, self).__init__(*args, **kwargs)

        self.mass_data = None
        self.rht_data = None
        self.collection_start_time = None

        self.setWindowTitle("Desiccator Controller")
        layout = QHBoxLayout()

        show_calculator = QAction("&Calculator", self)
        show_calculator.setStatusTip("Display Psychrometric Calculator")
        show_calculator.triggered.connect(self.show_calculator_clicked)

        show_converter = QAction("&Unit Converter", self)
        show_converter.setStatusTip("Display Unit Converter")
        show_converter.triggered.connect(self.show_converter_clicked)

        open_qr_code = QAction("Display &QR Code", self)
        open_qr_code.setStatusTip("Show QR code linking to newest SOP")
        open_qr_code.triggered.connect(self.open_qr_code)

        menu = self.menuBar()
        menu_menubar = menu.addMenu("&Menu")
        menu_menubar.addAction(show_calculator)
        menu_menubar.addAction(show_converter)

        help_menubar = menu.addMenu("&Help")
        help_menubar.addAction(open_qr_code)

        # Defining the load cell array to be passed into the updater object
        self.load_cell_array = LoadCellArray()
        self.load_cell_array.load_array()

        self.rht_sensor_array = RHTSensorArray([SHT45(i) for i in range(8)])

        # Test tabs below buttons
        self.tabs = QTabWidget()
        self.tabs.blockSignals(True)
        self.tabs.currentChanged.connect(self.tab_changed)

        home_page_tab = HomePageTab()

        chamber_1_tab = ChamberTabPage(self, 1)
        chamber_2_tab = ChamberTabPage(self, 2)
        chamber_3_tab = ChamberTabPage(self, 3)
        chamber_4_tab = ChamberTabPage(self, 4)

        self.tabs.addTab(home_page_tab, "Home")
        self.tabs.addTab(chamber_1_tab, 'Chamber 1')
        self.tabs.addTab(chamber_2_tab, 'Chamber 2')
        self.tabs.addTab(chamber_3_tab, 'Chamber 3')
        self.tabs.addTab(chamber_4_tab, 'Chamber 4')
        self.current_tab = 0
        layout.addWidget(self.tabs)

        self.widget = QWidget()
        self.widget.setLayout(layout)
        self.setCentralWidget(self.widget)

        self.threadpool = QThreadPool()

        self.tab_dict = {0: home_page_tab,
                         1: chamber_1_tab,
                         2: chamber_2_tab,
                         3: chamber_3_tab,
                         4: chamber_4_tab}

        self.controls = {'measure': False,
                         'calc_shown': False,
                         'converter_shown': False,
                         'read_signal': False}

        self.tabs.blockSignals(False)

    def show_new_masses(self, masses: list) -> None:
        masses.pop(0)
        #mass_string = '\n'.join(["Load Cell %i: %f" % (i + 1, masses[i]) for i in range(len(masses))])
        mass_string = "Load Cell %i : %f g" % (1, masses[0] + masses[1])
        [self.tab_dict[i].conditions_1.setText(mass_string) for i in range(1, 5)]

    def show_new_rht(self, rhts: list) -> None:
        for i in range(1, 5):
            rht_string = '\n'.join(["Sensor %i - %f C\t %f %%" % (j + 1, rhts[j + (i-1) * 2][0], rhts[j + (i-1) * 2][1]) for j in range(2)])
            self.tab_dict[i].conditions_2.setText(rht_string)

    def store_masses(self, data: list) -> None:
        current_time = data.pop(0)
        time_elapsed = current_time - self.collection_start_time
        self.mass_data = np.append(self.mass_data, [[time_elapsed, *data]], axis=0)
        [self.tab_dict[i].log_label.setText('Time Elapsed: ' + str(time_elapsed)) for i in range(1, 5)]
        print(self.mass_data)
        self.show_mass_plot()

    def store_rht(self, data: list) -> None:
        self.rht_data = np.append(self.rht_data, [[x for t in data for x in t]], axis=0)
        print(self.rht_data)
        self.show_psychro_plot()

    def show_mass_plot(self) -> None:
        for i in range(1, 5):
            xdata = self.mass_data[1:, 0]
            ydata = np.add(self.mass_data[1:, 1+(i-1)*2], self.mass_data[1:, 2*i])

            if self.tab_dict[i]._mass_plot_ref is None:
                plot_refs = self.tab_dict[i].mass_plot.axes.plot(xdata, ydata)
                self.tab_dict[i]._mass_plot_ref = plot_refs[0]
            else:
                self.tab_dict[i]._mass_plot_ref.set(xdata=xdata, ydata=ydata)
                self.tab_dict[i].mass_plot.axes.set(xlim=(0, np.max(xdata) + 10),
                                                    ylim=(np.min(ydata) - 25, np.max(ydata) + 25))
            self.tab_dict[1].mass_plot.draw()

    def show_psychro_plot(self) -> None:
        for i in range(1, 5):
            xdata_in = self.rht_data[:, (i-1)*2]
            ydata_in = [find_humidity_ratio_from_RH_temp(self.rht_data[i, 1+(i-1)*2] / 100, xdata_in[i]) for i in
                        range(len(xdata_in))]
            xdata_out = self.rht_data[:, 2+(i-1)*2]
            ydata_out = [find_humidity_ratio_from_RH_temp(self.rht_data[i, 3+(i-1)*2] / 100, xdata_out[i]) for i in
                         range(len(xdata_out))]

            if self.tab_dict[i]._psychro_plot_ref_in is None:
                plot_refs = self.tab_dict[i].psychro_plot.axes.plot(xdata_in, ydata_in, 'ro')
                self.tab_dict[i]._psychro_plot_ref_in = plot_refs[0]

                plot_refs = self.tab_dict[i].psychro_plot.axes.plot(xdata_out, ydata_out, 'bo')
                self.tab_dict[i]._psychro_plot_ref_out = plot_refs[0]
            else:
                self.tab_dict[i]._psychro_plot_ref_in.set(xdata=xdata_in, ydata=ydata_in)
                self.tab_dict[i]._psychro_plot_ref_out.set(xdata=xdata_out, ydata=ydata_out)
            self.tab_dict[i].psychro_plot.draw()

    def emit_read_pulse(self) -> None:
        self.controls['read_signal'] = True
        sleep(0.8)
        self.controls['read_signal'] = False

    def measurement_handling(self) -> None:
        coordinator = MeasurementCoordinator(self.load_cell_array, self.rht_sensor_array, self.controls)
        coordinator.signals.read.connect(self.emit_read_pulse)
        coordinator.mass_signals.result.connect(self.show_new_masses)
        coordinator.mass_signals.result.connect(self.store_masses)
        coordinator.rht_signals.result.connect(self.show_new_rht)
        coordinator.rht_signals.result.connect(self.store_rht)

        self.threadpool.start(coordinator)

    def measurement_clicked(self) -> str:
        if self.controls['measure']:
            self.collection_start_time = int(time())
            self.mass_data = np.zeros((1, int(1 + self.load_cell_array.num_cells)))
            self.rht_data = np.zeros((1, int(2 * self.rht_sensor_array.num_sensors)))
            self.measurement_handling()
        else:
            # Add either auto-saving or a save-only button that doesn't stop data collection
            file_name = str(self.collection_start_time) + '_data.csv'
            headings = 'time, ' + ', '.join(
                ["mass %i" % (num + 1) for num in range(self.load_cell_array.num_cells)]) + ', ' + ', '.join(
                "temp %i, rh %i" % (num + 1, num + 1) for num in range(self.rht_sensor_array.num_sensors))
            self.mass_data = np.delete(self.mass_data, 0, 0)
            self.rht_data = np.delete(self.rht_data, 0, 0)
            try:
                data_to_save = np.append(self.mass_data, self.rht_data, axis=1)
            except Exception:
                data_to_save = np.append(np.append(self.mass_data, [[-1]*self.load_cell_array.num_cells + 1], axis=0), self.rht_data, axis=1)
            np.savetxt(file_name, data_to_save, header=headings, delimiter=', ', fmt='%1.4f')
            self.mass_data = None
            self.rht_data = None

            [self.tab_dict[i].log_label.setText('Time Elapsed: ') for i in range(1, 5)]
            for i in range(1, 5):
                self.tab_dict[i]._mass_plot_ref = None
                self.tab_dict[i]._psychro_plot_ref_in = None
                self.tab_dict[i]._psychro_plot_ref_out = None
            return file_name

    def show_calculator_clicked(self) -> None:
        if not self.controls['calc_shown']:
            # then show the calc
            self.controls['calc_shown'] = True
            self.calc_window = PsychrometricCalculatorWindow(self)
            self.calc_window.show()
        else:
            self.tab_dict[self.current_tab].log_label.setText(self.tab_dict[self.current_tab].log_label.text() + "\nCalculator already shown.")

    def show_converter_clicked(self) -> None:
        if not self.controls['converter_shown']:
            self.controls['converter_shown'] = True
            self.converter_window = UnitConverterWindow(self)
            self.converter_window.show()
        else:
            self.tab_dict[self.current_tab].log_label.setText(self.tab_dict[self.current_tab].log_label.text() + "\nUnit Converter already shown.")

    def open_qr_code(self) -> None:
        dlg = QRCodeDlg(self.widget)
        dlg.exec()

    def tab_changed(self, i):
        self.current_tab = i
        if i != 0:
            self.tab_dict[i].record_checkbox.blockSignals(True)
            self.tab_dict[i].record_checkbox.setChecked(self.controls['measure'])
            self.tab_dict[i].record_checkbox.blockSignals(False)

    def closeEvent(self, event):
        # Override the closeEvent method that exists and replace with controls editing to exit ongoing threads
        if self.controls['measure']:
            self.controls['measure'] = False
            self.measurement_clicked()
        event.accept()


def main() -> None:
    psy_chart_app = QApplication(sys.argv)

    if '--windows' in sys.argv:
        window = PsychrometricCalculatorWindow()
        window.show()
    else:
        window = AppWindow()
        window.show()

    psy_chart_app.exec()


if __name__ == '__main__':
    main()
