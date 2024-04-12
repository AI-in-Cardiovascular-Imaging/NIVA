from functools import partial
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QPushButton

from gui.display.gating_display import GatingDisplay
from gui.display.longitudinal_view import LongitudinalView
from gui.display.contours_gui import new_measure
from segmentation.segment import segment


class RightHalf:
    def __init__(self, main_window):
        self.main_window = main_window

        right_upper_hbox = QHBoxLayout()
        main_window.gating_display = GatingDisplay(main_window)
        gating_display_vbox = QVBoxLayout()
        gating_display_vbox.addWidget(main_window.gating_display.toolbar)
        gating_display_vbox.addWidget(main_window.gating_display)
        right_upper_hbox.addLayout(gating_display_vbox)
        main_window.right_vbox.addLayout(right_upper_hbox, stretch=2)

        right_middle_hbox = QHBoxLayout()
        main_window.longitudinal_view = LongitudinalView(main_window)
        right_middle_hbox.addWidget(main_window.longitudinal_view)
        main_window.right_vbox.addLayout(right_middle_hbox, stretch=3)

        right_lower_vbox = QVBoxLayout()
        self.main_window.use_diastolic_button = QPushButton('Diastolic Frames')
        self.main_window.use_diastolic_button.setStyleSheet(f'background-color: rgb{self.main_window.diastole_color}')
        self.main_window.use_diastolic_button.setCheckable(True)
        self.main_window.use_diastolic_button.setChecked(True)
        self.main_window.use_diastolic_button.clicked.connect(self.use_diastolic)
        self.main_window.use_diastolic_button.setToolTip('Press button to switch between diastolic and systolic frames')
        gating_button = QPushButton('Extract Diastolic and Systolic Frames')
        gating_button.setToolTip('Extract diastolic and systolic images from pullback')
        gating_button.clicked.connect(main_window.contour_based_gating)
        segment_button = QPushButton('Automatic Segmentation')
        segment_button.setToolTip('Run deep learning based segmentation of lumen')
        segment_button.clicked.connect(partial(segment, main_window))
        measure_button_1 = QPushButton('Measurement &1')
        measure_button_1.setToolTip('Measure distance between two points')
        measure_button_1.clicked.connect(partial(new_measure, main_window, index=0))
        measure_button_1.setStyleSheet(f'border-color: {main_window.measure_colors[0]}')
        measure_button_2 = QPushButton('Measurement &2')
        measure_button_2.setToolTip('Measure distance between two points')
        measure_button_2.clicked.connect(partial(new_measure, main_window, index=1))
        measure_button_2.setStyleSheet(f'border-color: {main_window.measure_colors[1]}')
        right_lower_vbox.addWidget(self.main_window.use_diastolic_button)
        command_buttons = QHBoxLayout()
        command_buttons.addWidget(gating_button)
        command_buttons.addWidget(segment_button)
        right_lower_vbox.addLayout(command_buttons)
        measures = QHBoxLayout()
        measures.addWidget(measure_button_1)
        measures.addWidget(measure_button_2)
        right_lower_vbox.addLayout(measures)
        main_window.right_vbox.addLayout(right_lower_vbox)

    def use_diastolic(self):
        if self.main_window.image_displayed:
            if self.main_window.use_diastolic_button.isChecked():
                self.main_window.use_diastolic_button.setText('Diastolic Frames')
                self.main_window.use_diastolic_button.setStyleSheet(
                    f'background-color: rgb{self.main_window.diastole_color}'
                )
                self.main_window.gated_frames = self.main_window.gated_frames_dia
            else:
                self.main_window.use_diastolic_button.setText('Systolic Frames')
                self.main_window.use_diastolic_button.setStyleSheet(
                    f'background-color: rgb{self.main_window.systole_color}'
                )
                self.main_window.gated_frames = self.main_window.gated_frames_sys

            self.main_window.display_slider.set_gated_frames(self.main_window.gated_frames)
