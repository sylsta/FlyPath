import math
import os
import re
import shutil
import subprocess
import tempfile

from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QScrollArea, QFrame,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QSpinBox, QDoubleSpinBox,
    QMessageBox, QFileDialog,
)
from qgis.PyQt.QtCore import Qt, QObject, QEvent, QSettings, QVariant
from qgis.PyQt.QtGui import QColor, QFont

try:
    _AlignLeft    = Qt.AlignmentFlag.AlignLeft
    _AlignVCenter = Qt.AlignmentFlag.AlignVCenter
    _EventEnter   = QEvent.Type.Enter
    _EventLeave   = QEvent.Type.Leave
    _FrameNoFrame = QFrame.Shape.NoFrame
    _FontBold     = QFont.Weight.Bold
except AttributeError:
    _AlignLeft    = Qt.AlignLeft
    _AlignVCenter = Qt.AlignVCenter
    _EventEnter   = QEvent.Enter
    _EventLeave   = QEvent.Leave
    _FrameNoFrame = QFrame.NoFrame
    _FontBold     = QFont.Bold

from qgis.core import (
    Qgis,
    QgsProject,
    QgsWkbTypes,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsFillSymbol,
    QgsRuleBasedRenderer,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
)
from .map_tools import PolygonDrawTool
from .grid_planner import generate_flight_grid, find_optimal_direction
from .wpml_writer import write_kmz


# ── MTP PowerShell exit codes ─────────────────────────────────────────────
_MTP_EXIT_NAV_FAIL      = 1   # could not navigate path to waypoint folder
_MTP_EXIT_NO_UUID       = 2   # no UUID mission folder found in waypoint folder
_MTP_EXIT_UUID_MISSING  = 3   # UUID folder gone between script 1 and script 2
_MTP_EXIT_UUID_NO_OPEN  = 4   # UUID folder exists but GetFolder returned None

# ── Drone / camera specifications ─────────────────────────────────────────
DRONE_SPECS = {
    'DJI Mini 3 Pro': {
        'sensor_width_mm':  9.6,
        'sensor_height_mm': 7.2,
        'focal_length_mm':  6.9,
        'image_width_px':   4000,
        'image_height_px':  3000,
        'max_speed_ms':     12.0,
        'battery_time_min': 34,
        'info': '1/1.3" CMOS  ·  12 MP  ·  24 mm equiv',
    },
    'DJI Mini 4 Pro': {
        'sensor_width_mm':  9.6,
        'sensor_height_mm': 7.2,
        'focal_length_mm':  6.9,
        'image_width_px':   4000,
        'image_height_px':  3000,
        'max_speed_ms':     12.0,
        'battery_time_min': 34,
        'info': '1/1.3" CMOS  ·  12 MP  ·  24 mm equiv',
    },
    # Sensor dimensions use the standard Sony 1" format (13.2 × 8.8 mm).
    # Focal length derived from 24 mm equiv on a 1" sensor (crop factor ≈ 2.73).
    # Verify sensor_width_mm / focal_length_mm against official DJI EXIF data
    # if precision better than ~2% is needed for GSD calculations.
    # Drone enum (68) and mission compatibility community-verified on DJI RC2.
    'DJI Mini 5 Pro': {
        'sensor_width_mm':  13.2,
        'sensor_height_mm':  8.8,
        'focal_length_mm':   8.8,
        'image_width_px':   8192,
        'image_height_px':  6144,
        'max_speed_ms':     15.0,
        'battery_time_min':  45,
        'info': '1" CMOS  ·  50 MP  ·  24 mm equiv',
    },
}

# ── Dark stylesheet (Litchi-inspired) ─────────────────────────────────────
STYLESHEET = """
QWidget {
    background-color: #1E2128;
    color: #D0D0D0;
    font-size: 11px;
    font-family: "Segoe UI", Arial, sans-serif;
}
QGroupBox {
    border: 1px solid #3A3D45;
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 6px;
    font-weight: bold;
    color: #7FB3E8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background-color: #2A2D35;
    border: 1px solid #3A3D45;
    border-radius: 3px;
    padding: 3px 6px;
    color: #E0E0E0;
    selection-background-color: #2D6DB5;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #2D6DB5;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
    background-color: #3A3D45;
    border-radius: 0 3px 3px 0;
}
QComboBox::drop-down:hover { background-color: #4A4D55; }
QComboBox::down-arrow { image: url(ARROW_DOWN_PATH); width: 10px; height: 6px; }
QComboBox QAbstractItemView {
    background-color: #2A2D35;
    border: 1px solid #3A3D45;
    selection-background-color: #2D6DB5;
    color: #E0E0E0;
    outline: none;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button,       QSpinBox::down-button {
    background-color: #3A3D45; border: none; width: 16px;
}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover,
QSpinBox::up-button:hover,       QSpinBox::down-button:hover {
    background-color: #4A4D55;
}
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {
    image: url(ARROW_UP_PATH); width: 8px; height: 5px;
}
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {
    image: url(ARROW_DOWN_PATH); width: 8px; height: 5px;
}
QPushButton {
    background-color: #2D6DB5;
    color: white; border: none; border-radius: 4px;
    padding: 5px 10px; font-weight: bold;
}
QPushButton:hover   { background-color: #3A7EC6; }
QPushButton:pressed { background-color: #1F5A9E; }
QPushButton#exportBtn {
    background-color: #F0A500; color: #1A1A1A; font-size: 12px;
}
QPushButton#exportBtn:hover   { background-color: #FFB520; }
QPushButton#exportBtn:pressed { background-color: #D09000; }
QPushButton#clearPreviewBtn {
    background-color: #3A3D45; color: #D0D0D0; font-weight: normal;
}
QPushButton#clearPreviewBtn:hover { background-color: #4A4D55; }
QPushButton#drawPolygonBtn {
    background-color: #1E3A1E; color: #80C880;
    border: 1px solid #2E5A2E; font-weight: bold;
}
QPushButton#drawPolygonBtn:hover   { background-color: #2A4D2A; }
QPushButton#drawPolygonBtn:checked {
    background-color: #2A6A2A; border: 1px solid #40A040; color: #AAFAAA;
}
QPushButton#autoDirectionBtn {
    background-color: #3A3D45; color: #D0D0D0;
    font-weight: normal; font-size: 10px; padding: 3px 6px;
}
QPushButton#autoDirectionBtn:hover { background-color: #4A4D55; }
QPushButton#removePolygonBtn {
    background-color: #5A2020; color: #FF8888;
    border: 1px solid #7A3030; border-radius: 3px;
    font-weight: bold; padding: 3px 6px;
}
QPushButton#removePolygonBtn:hover { background-color: #7A2525; color: #FFAAAA; }
QPushButton#useSelectionBtn {
    background-color: #2A3A2A; color: #80C880;
    border: 1px solid #3A5A3A; border-radius: 3px;
    font-weight: normal; padding: 4px 8px;
}
QPushButton#useSelectionBtn:hover { background-color: #354535; color: #AAFAAA; }
QScrollArea { border: none; background-color: transparent; }
QScrollBar:vertical {
    background-color: #2A2D35; width: 7px; border-radius: 3px;
}
QScrollBar::handle:vertical {
    background-color: #4A4D55; border-radius: 3px; min-height: 20px;
}
QScrollBar::handle:vertical:hover  { background-color: #5A5D65; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLabel#gsdLabel, QLabel#areaLabel, QLabel#intervalLabel,
QLabel#frontOverlapLabel,
QLabel#flightTimeLabel, QLabel#distanceLabel, QLabel#photosLabel,
QLabel#linesLabel, QLabel#batteriesLabel, QLabel#coverageLabel {
    color: #F0A500; font-weight: bold;
}
QLabel#frontOverlapWarnLabel {
    color: #E05050; font-weight: bold;
}
QLabel#cameraInfoLabel { color: #7FB3E8; font-size: 10px; }
QWidget#actionBar {
    border-top: 1px solid #3A3D45; background-color: #181B22;
}
QPushButton#rcBrowseBtn {
    background-color: #2A3A4A; color: #7FB3E8;
    font-weight: normal; font-size: 10px; padding: 3px 6px;
    border-radius: 3px; border: 1px solid #3A5A7A;
}
QPushButton#rcBrowseBtn:hover { background-color: #354A5E; }
QLabel#infoBar {
    color: #7FB3E8;
    font-size: 10px;
    padding: 4px 8px 4px 10px;
    background-color: #1A1D24;
    border-top: 1px solid #2A2D35;
    border-left: 3px solid #2D6DB5;
}
QLabel#infoBarIdle {
    color: #4A5568;
    font-size: 10px;
    padding: 4px 8px 4px 10px;
    background-color: #1A1D24;
    border-top: 1px solid #2A2D35;
    border-left: 3px solid #3A3D45;
}
"""


_INFO_IDLE = 'ⓘ  Hover over any field to see what it does.'

# ── Map preview colour constants ───────────────────────────────────────────
_COLOR_START_MARKER  = '#CC2222'   # red filled circle — first waypoint
_COLOR_END_MARKER    = '#2D6DB5'   # blue filled circle — last waypoint
_COLOR_MID_MARKER    = 'white'     # white circle — intermediate waypoints

class _HoverFilter(QObject):
    """Event filter that writes a hint to a shared info label on mouse enter/leave."""

    def __init__(self, label, text, parent=None):
        super().__init__(parent)
        self._label = label
        self._text  = text

    def eventFilter(self, obj, event):
        if event.type() == _EventEnter:
            self._label.setObjectName('infoBar')
            self._label.setStyleSheet('')   # re-apply via object name
            self._label.setText('ⓘ  ' + self._text)
            self._label.style().unpolish(self._label)
            self._label.style().polish(self._label)
        elif event.type() == _EventLeave:
            self._label.setObjectName('infoBarIdle')
            self._label.setStyleSheet('')
            self._label.setText(_INFO_IDLE)
            self._label.style().unpolish(self._label)
            self._label.style().polish(self._label)
        return False   # never consume the event


class FlyPathDialog(QWidget):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface

        # State
        self._survey_polygon     = None
        self._survey_polygon_crs = None
        self._draw_tool          = None
        self._selected_layer_id  = None   # layer carrying the current map selection
        self._monitored_layer_id = None   # layer whose edit signals we're connected to
        self._prev_map_tool      = None
        self._syncing_selection  = False  # guard: prevent selectByIds re-entrance
        self._survey_area_layer_id = None  # temporary drawn-polygon layer
        self._preview_layer_ids  = []     # [path_line_id, waypoints_id]
        self._waypoints          = []
        self._shot_spacing_m     = 0.0

        self._build_ui()
        self._setup_combos()
        self._connect_signals()
        self._update_camera_info()
        self._update_gsd()
        self._update_interval()

    # ── Hover-hint helper ─────────────────────────────────────────────────

    def _tip(self, widget, text):
        """Attach a hover hint to widget — shown in the info bar, not as a tooltip."""
        widget.setToolTip('')   # disable floating tooltip
        f = _HoverFilter(self.infoBar, text, parent=widget)
        widget.installEventFilter(f)

    # ── UI construction ───────────────────────────────────────────────────

    def _build_ui(self):
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        arrow_down = os.path.join(plugin_dir, 'arrow_down.svg').replace('\\', '/')
        arrow_up   = os.path.join(plugin_dir, 'arrow_up.svg').replace('\\', '/')
        self.setStyleSheet(
            STYLESHEET
            .replace('ARROW_DOWN_PATH', arrow_down)
            .replace('ARROW_UP_PATH',   arrow_up)
        )

        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Scrollable form area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_FrameNoFrame)

        content = QWidget()
        scroll_layout = QVBoxLayout(content)
        scroll_layout.setSpacing(8)
        scroll_layout.setContentsMargins(8, 8, 8, 8)

        # Info bar must exist before group builders call self._tip()
        self.infoBar = QLabel(_INFO_IDLE)
        self.infoBar.setObjectName('infoBarIdle')
        self.infoBar.setWordWrap(True)
        self.infoBar.setMinimumHeight(32)

        scroll_layout.addWidget(self._build_mission_group())
        scroll_layout.addWidget(self._build_area_group())
        scroll_layout.addWidget(self._build_flight_group())
        scroll_layout.addWidget(self._build_camera_group())
        scroll_layout.addWidget(self._build_advanced_group())
        scroll_layout.addWidget(self._build_stats_group())
        scroll_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        outer.addWidget(self.infoBar)
        outer.addWidget(self._build_action_bar())

    def _build_mission_group(self):
        group = QGroupBox('Mission Setup')
        form  = QFormLayout(group)
        form.setLabelAlignment(_AlignLeft | _AlignVCenter)
        form.setSpacing(6)

        self.droneModelCombo = QComboBox()
        self._tip(self.droneModelCombo,
            'Your drone model — determines camera sensor specs, '
            'maximum speed, and battery endurance used in all calculations.')
        form.addRow('Drone', self.droneModelCombo)

        self.cameraInfoLabel = QLabel('—')
        self.cameraInfoLabel.setObjectName('cameraInfoLabel')
        self._tip(self.cameraInfoLabel,
            'Camera sensor summary for the selected drone. '
            'Used to calculate GSD, footprint size, and photo interval.')
        form.addRow('Camera', self.cameraInfoLabel)

        return group

    def _build_area_group(self):
        group = QGroupBox('Survey Area')
        form  = QFormLayout(group)
        form.setLabelAlignment(_AlignLeft | _AlignVCenter)
        form.setSpacing(6)

        self.layerCombo = QComboBox()
        self._tip(self.layerCombo,
            'Select a polygon layer from the QGIS project. '
            'Only polygon layers are listed. '
            'For multi-feature layers a Feature selector will appear below.')
        form.addRow('Layer', self.layerCombo)

        self.featureCombo = QComboBox()
        self.featureCombo.setVisible(False)
        self._tip(self.featureCombo,
            'Select which polygon feature to use as the survey area '
            'when the chosen layer contains more than one feature.')
        self._featureComboRow = form.rowCount()
        form.addRow('Feature', self.featureCombo)

        self.useSelectionBtn = QPushButton('Use QGIS Selection')
        self.useSelectionBtn.setObjectName('useSelectionBtn')
        self._tip(self.useSelectionBtn,
            'Adopt the polygon currently selected with the QGIS selection tool. '
            'Exactly one polygon must be selected across all layers.')
        form.addRow(self.useSelectionBtn)

        draw_row = QWidget()
        draw_layout = QHBoxLayout(draw_row)
        draw_layout.setContentsMargins(0, 0, 0, 0)
        draw_layout.setSpacing(4)

        self.drawPolygonBtn = QPushButton('Draw Polygon on Map')
        self.drawPolygonBtn.setObjectName('drawPolygonBtn')
        self.drawPolygonBtn.setCheckable(True)
        self._tip(self.drawPolygonBtn,
            'Activate the polygon drawing tool. '
            'Left-click to place vertices, right-click or double-click to finish, '
            'Backspace to undo the last vertex, Escape to cancel.')

        self.removePolygonBtn = QPushButton('✕ Remove')
        self.removePolygonBtn.setObjectName('removePolygonBtn')
        self._tip(self.removePolygonBtn,
            'Remove the drawn polygon and reset the survey area.')
        self.removePolygonBtn.setVisible(False)

        draw_layout.addWidget(self.drawPolygonBtn)
        draw_layout.addWidget(self.removePolygonBtn)
        form.addRow(draw_row)

        self.areaLabel = QLabel('—')
        self.areaLabel.setObjectName('areaLabel')
        self._tip(self.areaLabel, 'Total area of the survey polygon in hectares.')
        form.addRow('Area', self.areaLabel)

        return group

    def _build_flight_group(self):
        group = QGroupBox('Flight Parameters')
        form  = QFormLayout(group)
        form.setLabelAlignment(_AlignLeft | _AlignVCenter)
        form.setSpacing(6)

        self.altitudeSpin = QDoubleSpinBox()
        self.altitudeSpin.setRange(30.0, 500.0)
        self.altitudeSpin.setValue(100.0)
        self.altitudeSpin.setSingleStep(5.0)
        self.altitudeSpin.setDecimals(1)
        self.altitudeSpin.setSuffix(' m')
        self._tip(self.altitudeSpin,
            'Flight altitude above ground level (AGL). '
            'Higher altitude → wider coverage per photo but lower resolution (larger GSD). '
            'Lower altitude → sharper images but more flight lines and longer mission time.')
        form.addRow('Altitude', self.altitudeSpin)

        self.gsdLabel = QLabel('—')
        self.gsdLabel.setObjectName('gsdLabel')
        self._tip(self.gsdLabel,
            'Ground Sampling Distance — the real-world size of one pixel in your photos. '
            'Smaller GSD = higher resolution. Calculated from altitude, sensor size and focal length.')
        form.addRow('GSD', self.gsdLabel)

        self.sideOverlapSpin = QSpinBox()
        self.sideOverlapSpin.setRange(50, 95)
        self.sideOverlapSpin.setValue(70)
        self.sideOverlapSpin.setSuffix(' %')
        self._tip(self.sideOverlapSpin,
            'How much adjacent flight lines overlap each other. '
            'Higher → fewer gaps, better stitching, but more flight lines. '
            'Recommended: 60–75% for flat terrain, 70–80% for hilly terrain.')
        form.addRow('Side Overlap', self.sideOverlapSpin)

        self.speedSpin = QDoubleSpinBox()
        self.speedSpin.setRange(1.0, 12.0)
        self.speedSpin.setValue(5.0)
        self.speedSpin.setSingleStep(0.5)
        self.speedSpin.setDecimals(1)
        self.speedSpin.setSuffix(' m/s')
        self._tip(self.speedSpin,
            'Drone flight speed during the mission. '
            'Higher speed → shorter mission time but may cause motion blur. '
            'Keep speed low enough for your shutter speed at the chosen altitude.')
        form.addRow('Speed', self.speedSpin)

        # Direction row: spinbox + Auto button side by side
        dir_widget = QWidget()
        dir_layout = QHBoxLayout(dir_widget)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(4)

        self.directionSpin = QDoubleSpinBox()
        self.directionSpin.setRange(0.0, 359.9)
        self.directionSpin.setValue(0.0)
        self.directionSpin.setSingleStep(1.0)
        self.directionSpin.setDecimals(1)
        self.directionSpin.setSuffix(' °')
        self.directionSpin.setWrapping(True)
        self._tip(self.directionSpin,
            'Flight line direction in degrees clockwise from North. '
            '0° = North–South lines, 90° = East–West lines. '
            'Align with the longest axis of the polygon to minimise turns.')

        self.autoDirectionBtn = QPushButton('Auto')
        self.autoDirectionBtn.setObjectName('autoDirectionBtn')
        self.autoDirectionBtn.setFixedWidth(52)
        self._tip(self.autoDirectionBtn,
            'Automatically find the optimal flight direction '
            'that minimises the number of flight lines for this polygon.')

        dir_layout.addWidget(self.directionSpin)
        dir_layout.addWidget(self.autoDirectionBtn)
        form.addRow('Direction', dir_widget)

        self.marginSpin = QDoubleSpinBox()
        self.marginSpin.setRange(0.0, 200.0)
        self.marginSpin.setValue(0.0)
        self.marginSpin.setSingleStep(5.0)
        self.marginSpin.setDecimals(1)
        self.marginSpin.setSuffix(' m')
        self._tip(self.marginSpin,
            'Buffer distance added around the survey polygon boundary. '
            'Ensures full photo coverage at the edges. '
            'Typically 0–50 m depending on altitude and terrain.')
        form.addRow('Margin', self.marginSpin)

        return group

    def _build_camera_group(self):
        group = QGroupBox('Camera Settings')
        form  = QFormLayout(group)
        form.setLabelAlignment(_AlignLeft | _AlignVCenter)
        form.setSpacing(6)

        self.gimbalAngleSpin = QSpinBox()
        self.gimbalAngleSpin.setRange(-90, -30)
        self.gimbalAngleSpin.setValue(-90)
        self.gimbalAngleSpin.setSingleStep(5)
        self.gimbalAngleSpin.setSuffix(' °')
        self._tip(self.gimbalAngleSpin,
            'Gimbal pitch angle. -90° points straight down (nadir) for '
            '2D orthomosaic mapping. Tilt toward 0° for oblique photography.')
        form.addRow('Gimbal Angle', self.gimbalAngleSpin)

        self.photoIntervalSpin = QDoubleSpinBox()
        self.photoIntervalSpin.setRange(2.0, 60.0)
        self.photoIntervalSpin.setValue(2.0)
        self.photoIntervalSpin.setSingleStep(0.5)
        self.photoIntervalSpin.setDecimals(1)
        self.photoIntervalSpin.setSuffix(' s')
        self._tip(self.photoIntervalSpin,
            'Time between each photo in seconds. The drone uses auto interval '
            'shooting — minimum 2 s at 12 MP JPEG (DJI Mini 4 Pro / Mini 3 Pro). '
            'Actual along-track spacing = speed × interval.')
        form.addRow('Photo Interval', self.photoIntervalSpin)

        self.intervalLabel = QLabel('—')
        self.intervalLabel.setObjectName('intervalLabel')
        self._tip(self.intervalLabel,
            'Effective along-track distance between photos: speed × interval. '
            'Smaller spacing means more photos and higher overlap.')
        form.addRow('Shot Spacing', self.intervalLabel)

        self.frontOverlapLabel = QLabel('—')
        self.frontOverlapLabel.setObjectName('frontOverlapLabel')
        self._tip(self.frontOverlapLabel,
            'Calculated front overlap between consecutive photos along the flight line. '
            'Based on speed, interval, altitude and drone sensor. '
            'Aim for 75–85% for mapping, 85–90% for 3D models. '
            'Reduce speed or increase interval to raise overlap.')
        form.addRow('Front Overlap', self.frontOverlapLabel)

        return group

    def _build_advanced_group(self):
        group = QGroupBox('Safety Actions')
        form  = QFormLayout(group)
        form.setLabelAlignment(_AlignLeft | _AlignVCenter)
        form.setSpacing(6)

        self.finishActionCombo = QComboBox()
        self._tip(self.finishActionCombo,
            'What the drone does after the last waypoint. '
            'Return to Home: flies back and lands at takeoff. '
            'Hover: holds position at the last waypoint. '
            'Land: lands immediately at the last waypoint.')
        form.addRow('Finish Action', self.finishActionCombo)

        self.rcLostActionCombo = QComboBox()
        self._tip(self.rcLostActionCombo,
            'What the drone does if the RC signal is lost during the mission. '
            'Return to Home: flies back to takeoff point. '
            'Hover: holds position and waits for signal. '
            'Land: lands immediately at current position. '
            'Continue: keeps flying the mission regardless.')
        form.addRow('RC Lost Action', self.rcLostActionCombo)

        return group

    def _build_stats_group(self):
        group = QGroupBox('Statistics')
        form  = QFormLayout(group)
        form.setLabelAlignment(_AlignLeft | _AlignVCenter)
        form.setSpacing(6)

        stats = [
            ('flightTimeLabel', 'Flight Time',
             'Estimated total flight duration based on path length and speed. '
             'Does not include takeoff, landing, or battery swap time.'),
            ('distanceLabel',   'Distance',
             'Total distance the drone will fly along all flight lines.'),
            ('photosLabel',     'Photos',
             'Estimated number of photos the camera will take during the mission.'),
            ('linesLabel',      'Flight Lines',
             'Number of parallel flight lines needed to cover the survey area.'),
            ('batteriesLabel',  'Batteries',
             'Estimated number of battery charges needed to complete the mission, '
             'based on the drone\'s rated endurance at the selected speed.'),
            ('coverageLabel',   'Coverage',
             'Total survey area in hectares as calculated from the polygon.'),
        ]
        for attr, caption, tip in stats:
            lbl = QLabel('—')
            lbl.setObjectName(attr)
            self._tip(lbl, tip)
            setattr(self, attr, lbl)
            form.addRow(caption, lbl)

        return group

    def _build_action_bar(self):
        bar = QWidget()
        bar.setObjectName('actionBar')
        layout = QVBoxLayout(bar)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 6, 8, 10)

        # RC waypoint folder row
        rc_row = QWidget()
        rc_layout = QHBoxLayout(rc_row)
        rc_layout.setContentsMargins(0, 0, 0, 0)
        rc_layout.setSpacing(4)

        self.rcPathEdit = QLineEdit()
        self.rcPathEdit.setPlaceholderText('Paste RC waypoint folder path…')
        self.rcPathEdit.setText(
            QSettings('FlyPath', 'FlyPath').value('rc_waypoint_dir', '')
        )
        self._tip(self.rcPathEdit,
            'Path to the waypoint folder on your DJI RC. '
            'Paste it here once — FlyPath will auto-replace the latest mission on export.')

        self.rcBrowseBtn = QPushButton('Browse…')
        self.rcBrowseBtn.setObjectName('rcBrowseBtn')
        self.rcBrowseBtn.setFixedWidth(58)
        self._tip(self.rcBrowseBtn,
            'Open File Explorer at "This PC" so you can navigate to the DJI RC, '
            'copy the waypoint folder path from the address bar, and paste it here.')

        rc_layout.addWidget(self.rcPathEdit)
        rc_layout.addWidget(self.rcBrowseBtn)
        layout.addWidget(rc_row)

        self.previewBtn = QPushButton('Preview on Map')
        self.previewBtn.setMinimumHeight(30)
        self._tip(self.previewBtn,
            'Generate the flight grid and display the waypoint path '
            'on the QGIS map canvas for review before exporting.')

        self.clearPreviewBtn = QPushButton('Clear Preview')
        self.clearPreviewBtn.setObjectName('clearPreviewBtn')
        self.clearPreviewBtn.setMinimumHeight(26)
        self._tip(self.clearPreviewBtn,
            'Remove the flight path preview layers from the map '
            'and reset the survey area selection.')

        self.exportBtn = QPushButton('Export KMZ')
        self.exportBtn.setObjectName('exportBtn')
        self.exportBtn.setMinimumHeight(36)
        self._tip(self.exportBtn,
            'Export the mission as a DJI WPML KMZ file. '
            'Load the file in the DJI Fly app to fly the mission.')

        layout.addWidget(self.previewBtn)
        layout.addWidget(self.clearPreviewBtn)
        layout.addWidget(self.exportBtn)

        return bar

    # ── Combo population ──────────────────────────────────────────────────

    def _setup_combos(self):
        self.droneModelCombo.addItems(list(DRONE_SPECS.keys()))
        self.droneModelCombo.setCurrentText('DJI Mini 4 Pro')


        self.finishActionCombo.addItems([
            'Return to Home',
            'Hover in place',
            'Land at last waypoint',
        ])
        self.rcLostActionCombo.addItems([
            'Return to Home',
            'Hover in place',
            'Land immediately',
            'Continue mission',
        ])
        self._refresh_layer_combo()

    def _refresh_layer_combo(self, _=None):
        previously_selected = self.layerCombo.currentData()
        self.layerCombo.blockSignals(True)
        self.layerCombo.clear()
        self.layerCombo.addItem('— none —', None)
        for layer in QgsProject.instance().mapLayers().values():
            if (hasattr(layer, 'wkbType') and
                    QgsWkbTypes.geometryType(layer.wkbType()) ==
                    QgsWkbTypes.PolygonGeometry and
                    not layer.customProperty('flypath_internal')):
                self.layerCombo.addItem(layer.name(), layer.id())
        # Restore previous selection if the layer still exists
        idx = self.layerCombo.findData(previously_selected)
        self.layerCombo.setCurrentIndex(idx if idx >= 0 else 0)
        self.layerCombo.blockSignals(False)

    # ── Signal wiring ─────────────────────────────────────────────────────

    def _connect_signals(self):
        # Refresh layer combo when layers are added/removed
        QgsProject.instance().layersAdded.connect(self._refresh_layer_combo)
        QgsProject.instance().layersRemoved.connect(self._refresh_layer_combo)

        self.droneModelCombo.currentIndexChanged.connect(self._on_drone_changed)
        self.altitudeSpin.valueChanged.connect(self._on_param_changed)
        self.sideOverlapSpin.valueChanged.connect(self._on_param_changed)
        self.speedSpin.valueChanged.connect(self._on_param_changed)
        self.photoIntervalSpin.valueChanged.connect(self._on_param_changed)
        self.gimbalAngleSpin.valueChanged.connect(self._update_stats)
        self.directionSpin.valueChanged.connect(self._update_stats)
        self.layerCombo.currentIndexChanged.connect(self._on_layer_changed)
        self.featureCombo.currentIndexChanged.connect(self._on_feature_changed)
        self.useSelectionBtn.clicked.connect(self._on_use_qgis_selection)
        self.rcBrowseBtn.clicked.connect(self._on_browse_rc_path)
        self.rcPathEdit.textChanged.connect(self._on_rc_path_changed)
        self.drawPolygonBtn.clicked.connect(self._on_draw_polygon)
        self.removePolygonBtn.clicked.connect(self._on_remove_drawn_polygon)
        self.autoDirectionBtn.clicked.connect(self._on_auto_direction)
        self.previewBtn.clicked.connect(self._on_preview)
        self.clearPreviewBtn.clicked.connect(self._on_clear_preview)
        self.exportBtn.clicked.connect(self._on_export)

    def _on_param_changed(self):
        self._update_gsd()
        self._update_interval()
        self._update_stats()
        self._on_clear_preview(reset_area=False)

    # ── Drone / camera ────────────────────────────────────────────────────

    def _on_drone_changed(self):
        self._update_camera_info()
        self._on_param_changed()

    def _update_camera_info(self):
        drone = self.droneModelCombo.currentText()
        self.cameraInfoLabel.setText(
            DRONE_SPECS[drone]['info'] if drone in DRONE_SPECS else '—'
        )

    # ── GSD ───────────────────────────────────────────────────────────────

    def _calc_gsd(self):
        drone = self.droneModelCombo.currentText()
        if drone not in DRONE_SPECS:
            return None
        s = DRONE_SPECS[drone]
        return round(
            (self.altitudeSpin.value() * s['sensor_width_mm'] * 100) /
            (s['focal_length_mm'] * s['image_width_px']), 2
        )

    def _update_gsd(self):
        gsd = self._calc_gsd()
        self.gsdLabel.setText(f'{gsd:.2f} cm/px' if gsd else '—')

    # ── Footprint & trigger interval ──────────────────────────────────────

    def _footprint(self):
        drone = self.droneModelCombo.currentText()
        if drone not in DRONE_SPECS:
            return None, None
        s   = DRONE_SPECS[drone]
        alt = self.altitudeSpin.value()
        return (alt * s['sensor_width_mm'] / s['focal_length_mm'],
                alt * s['sensor_height_mm'] / s['focal_length_mm'])

    def _update_interval(self):
        _, fh = self._footprint()
        spd = self.speedSpin.value()
        interval = self.photoIntervalSpin.value()
        if fh is None or spd <= 0 or interval <= 0:
            self.intervalLabel.setText('—')
            self.frontOverlapLabel.setText('—')
            self.frontOverlapLabel.setObjectName('frontOverlapLabel')
            self.frontOverlapLabel.style().unpolish(self.frontOverlapLabel)
            self.frontOverlapLabel.style().polish(self.frontOverlapLabel)
            return
        actual_spacing = spd * interval
        overlap_pct = (1.0 - actual_spacing / fh) * 100.0
        self.intervalLabel.setText(f'{actual_spacing:.1f} m')
        if overlap_pct < 60:
            self.frontOverlapLabel.setText(f'{overlap_pct:.0f} %  — too low, reduce speed or interval')
            self.frontOverlapLabel.setObjectName('frontOverlapWarnLabel')
        elif overlap_pct < 70:
            self.frontOverlapLabel.setText(f'{overlap_pct:.0f} %  — marginal')
            self.frontOverlapLabel.setObjectName('frontOverlapWarnLabel')
        else:
            self.frontOverlapLabel.setText(f'{overlap_pct:.0f} %')
            self.frontOverlapLabel.setObjectName('frontOverlapLabel')
        self.frontOverlapLabel.style().unpolish(self.frontOverlapLabel)
        self.frontOverlapLabel.style().polish(self.frontOverlapLabel)

    # ── QGIS selection sync ───────────────────────────────────────────────

    def _on_use_qgis_selection(self):
        """
        Inspect the current QGIS selection across all non-internal polygon
        layers and adopt it as the FlyPath survey polygon.

        Rules:
          0 selected features total → error
          > 1 selected features total → error
          exactly 1 selected feature  → sync Layer/Feature combos + survey polygon
        """
        candidates = []
        for layer in QgsProject.instance().mapLayers().values():
            if (not hasattr(layer, 'wkbType') or
                    layer.customProperty('flypath_internal') or
                    QgsWkbTypes.geometryType(layer.wkbType()) !=
                    QgsWkbTypes.PolygonGeometry):
                continue
            for fid in layer.selectedFeatureIds():
                candidates.append((layer, fid))

        if len(candidates) == 0:
            QMessageBox.information(
                self, 'Nothing Selected',
                'No polygon is selected in QGIS.\n\n'
                'Select a single polygon with the QGIS selection tool and try again.'
            )
            return

        if len(candidates) > 1:
            QMessageBox.warning(
                self, 'Multiple Polygons Selected',
                f'{len(candidates)} polygons are selected across one or more layers.\n\n'
                'FlyPath supports one survey polygon at a time.\n'
                'Select exactly one polygon and try again.'
            )
            return

        layer, fid = candidates[0]
        feat = next(layer.getFeatures([fid]))

        # Remove any active drawn polygon
        if self._survey_area_layer_id:
            self._on_remove_drawn_polygon()

        # Sync Layer combo
        layer_idx = self.layerCombo.findData(layer.id())
        if layer_idx < 0:
            return
        self.layerCombo.blockSignals(True)
        self.layerCombo.setCurrentIndex(layer_idx)
        self.layerCombo.blockSignals(False)

        # Connect layer edit signals if not already done
        if self._monitored_layer_id != layer.id():
            self._disconnect_layer_signals()
            self._connect_layer_signals(layer)

        # Sync Feature combo for multi-feature layers
        if layer.featureCount() > 1:
            self._populate_feature_combo(layer)
            feat_idx = self.featureCombo.findData(fid)
            if feat_idx >= 0:
                self.featureCombo.blockSignals(True)
                self.featureCombo.setCurrentIndex(feat_idx)
                self.featureCombo.blockSignals(False)
        else:
            self.featureCombo.setVisible(False)

        self._set_survey_polygon(feat.geometry(), layer.crs(),
                                 layer_id=layer.id(), fid=fid)

    # ── Survey area ───────────────────────────────────────────────────────

    def _on_layer_changed(self):
        layer_id = self.layerCombo.currentData()
        self._disconnect_layer_signals()

        # Reset feature combo
        self.featureCombo.blockSignals(True)
        self.featureCombo.clear()
        self.featureCombo.setVisible(False)
        self.featureCombo.blockSignals(False)

        if not layer_id:
            self._survey_polygon     = None
            self._survey_polygon_crs = None
            self._on_clear_preview(reset_area=False)
            self._clear_stats()
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return

        # A layer-based polygon replaces any drawn polygon
        if self._survey_area_layer_id:
            self._remove_survey_area_layer()
            self._on_clear_preview(reset_area=False)
            self._survey_polygon     = None
            self._survey_polygon_crs = None

        self._connect_layer_signals(layer)
        self._populate_feature_combo(layer)

    def _populate_feature_combo(self, layer):
        """Populate (or refresh) the feature combo for the given layer."""
        layer_id = layer.id()

        # Remember current selection to restore it after refresh
        prev_fid = self.featureCombo.currentData()

        self.featureCombo.blockSignals(True)
        self.featureCombo.clear()

        count = layer.featureCount()

        if count == 0:
            self.featureCombo.setVisible(False)
            self.featureCombo.blockSignals(False)
            self._survey_polygon     = None
            self._survey_polygon_crs = None
            self.areaLabel.setText('—')
            self._clear_stats()
            return

        if count == 1:
            self.featureCombo.setVisible(False)
            self.featureCombo.blockSignals(False)
            feat = next(layer.getFeatures())
            self._set_survey_polygon(feat.geometry(), layer.crs(),
                                     layer_id=layer_id, fid=feat.id())
        else:
            self.featureCombo.addItem('— select a feature —', None)
            name_field = self._guess_name_field(layer)
            for feat in layer.getFeatures():
                fid   = feat.id()
                label = (f'FID {fid}  —  {feat[name_field]}'
                         if name_field else f'FID {fid}')
                self.featureCombo.addItem(label, fid)
            self.featureCombo.setVisible(True)

            # Restore previous selection if the feature still exists
            idx = self.featureCombo.findData(prev_fid)
            if idx >= 0:
                self.featureCombo.setCurrentIndex(idx)
            else:
                # Previously selected feature was deleted — reset survey area
                self.featureCombo.setCurrentIndex(0)
                self._survey_polygon     = None
                self._survey_polygon_crs = None
                self.areaLabel.setText('—')
                self._clear_stats()

            self.featureCombo.blockSignals(False)

    def _connect_layer_signals(self, layer):
        """Connect to a layer's edit signals to keep the feature combo in sync."""
        layer.featureAdded.connect(self._on_layer_features_changed)
        layer.featuresDeleted.connect(self._on_layer_features_changed)
        layer.editingStopped.connect(self._on_layer_features_changed)
        layer.attributeValueChanged.connect(self._on_layer_features_changed)
        self._monitored_layer_id = layer.id()

    def _disconnect_layer_signals(self):
        """Disconnect from the previously monitored layer's edit signals."""
        if not self._monitored_layer_id:
            return
        layer = QgsProject.instance().mapLayer(self._monitored_layer_id)
        if layer:
            try:
                layer.featureAdded.disconnect(self._on_layer_features_changed)
                layer.featuresDeleted.disconnect(self._on_layer_features_changed)
                layer.editingStopped.disconnect(self._on_layer_features_changed)
                layer.attributeValueChanged.disconnect(self._on_layer_features_changed)
            except RuntimeError:
                pass  # signals already disconnected — safe to ignore
        self._monitored_layer_id = None

    def _on_layer_features_changed(self, *_args):
        """Refresh the feature combo whenever features are added, deleted, or edited."""
        layer_id = self.layerCombo.currentData()
        if not layer_id:
            return
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer:
            self._populate_feature_combo(layer)

    def _on_feature_changed(self):
        fid = self.featureCombo.currentData()
        if fid is None:
            self._clear_layer_selection()
            self._survey_polygon     = None
            self._survey_polygon_crs = None
            self._on_clear_preview(reset_area=False)
            self._clear_stats()
            return
        layer_id = self.layerCombo.currentData()
        layer    = QgsProject.instance().mapLayer(layer_id)
        if not layer:
            return
        feats = list(layer.getFeatures([fid]))
        if not feats:
            return
        self._set_survey_polygon(feats[0].geometry(), layer.crs(),
                                 layer_id=layer_id, fid=fid)

    def _set_survey_polygon(self, geom, crs, layer_id=None, fid=None):
        self._on_clear_preview(reset_area=False)   # clear old flight path
        self._clear_layer_selection()
        self._survey_polygon     = geom
        self._survey_polygon_crs = crs
        # Highlight the chosen feature in the map canvas
        if layer_id and fid is not None:
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer:
                self._syncing_selection = True
                layer.selectByIds([fid])
                self._syncing_selection = False
                self._selected_layer_id = layer_id
                self.iface.mapCanvas().refresh()
        area_ha = self._area_ha()
        self.areaLabel.setText(f'{area_ha:.2f} ha')
        self._update_stats()
        self._check_area_advisory(area_ha)

    def _clear_layer_selection(self):
        if self._selected_layer_id:
            layer = QgsProject.instance().mapLayer(self._selected_layer_id)
            if layer:
                layer.removeSelection()
                self.iface.mapCanvas().refresh()
            self._selected_layer_id = None

    def _check_area_advisory(self, area_ha):
        if area_ha > 200:
            QMessageBox.information(
                self, 'Large Survey Area',
                f'The selected area is {area_ha:.0f} ha.\n\n'
                'Missions this size will require multiple battery swaps. '
                'Check the estimated Batteries field in Statistics and '
                'plan your swap stops before flying.'
            )

    @staticmethod
    def _guess_name_field(layer):
        """Return the first text-like field name, or None."""
        for field in layer.fields():
            if field.type() in (QVariant.String,):
                return field.name()
        return None

    def _on_draw_polygon(self, checked):
        if checked:
            if self._survey_polygon is not None:
                reply = QMessageBox.question(
                    self, 'Replace Survey Area?',
                    'A survey area is already defined.\n\n'
                    'Do you want to discard it and draw a new polygon?',
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    self.drawPolygonBtn.setChecked(False)
                    return
                # User confirmed — clear everything before drawing
                self._on_clear_preview(reset_area=True)

            # Reset layer / feature selection — drawn polygon is standalone
            self._disconnect_layer_signals()
            self._clear_layer_selection()
            self.layerCombo.blockSignals(True)
            self.layerCombo.setCurrentIndex(0)
            self.layerCombo.blockSignals(False)
            self.featureCombo.blockSignals(True)
            self.featureCombo.clear()
            self.featureCombo.setVisible(False)
            self.featureCombo.blockSignals(False)

            canvas = self.iface.mapCanvas()
            self._prev_map_tool = canvas.mapTool()
            self._draw_tool = PolygonDrawTool(canvas)
            self._draw_tool.polygon_completed.connect(self._on_polygon_drawn)
            self._draw_tool.drawing_cancelled.connect(self._on_drawing_cancelled)
            canvas.setMapTool(self._draw_tool)
            self.drawPolygonBtn.setText('Drawing…  (right-click or double-click to finish)')
        else:
            self._cancel_draw_tool()

    def _on_polygon_drawn(self, geom):
        self.drawPolygonBtn.setChecked(False)
        self.drawPolygonBtn.setText('Draw Polygon on Map')
        if self._prev_map_tool:
            self.iface.mapCanvas().setMapTool(self._prev_map_tool)
            self._prev_map_tool = None
        crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        self._show_drawn_polygon(geom, crs)
        self._set_survey_polygon(geom, crs)

    def _show_drawn_polygon(self, geom, crs):
        """Add the drawn survey boundary as a styled temporary layer."""
        self._remove_survey_area_layer()

        # Reproject to WGS84 for consistency with other preview layers
        wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
        xform = QgsCoordinateTransform(crs, wgs84, QgsProject.instance())
        g = QgsGeometry(geom)
        g.transform(xform)

        layer = QgsVectorLayer('Polygon?crs=EPSG:4326',
                               'FlyPath — Survey Area', 'memory')
        layer.setCustomProperty('flypath_internal', True)
        feat = QgsFeature()
        feat.setGeometry(g)
        layer.dataProvider().addFeatures([feat])

        symbol = QgsFillSymbol.createSimple({
            'color': '255,20,147,85',
            'outline_color': '#FF1493',
            'outline_width': '0.8',
            'outline_style': 'dash',
        })
        layer.renderer().setSymbol(symbol)

        # Track geometry edits made via QGIS tools
        layer.editingStopped.connect(self._on_survey_area_edited)
        layer.geometryChanged.connect(self._on_survey_area_geometry_changed)

        QgsProject.instance().addMapLayer(layer)
        self._survey_area_layer_id = layer.id()
        self.removePolygonBtn.setVisible(True)
        self.iface.mapCanvas().refresh()

    def _on_survey_area_edited(self):
        """Called after the user commits edits to the survey area layer."""
        if not self._survey_area_layer_id:
            return
        layer = QgsProject.instance().mapLayer(self._survey_area_layer_id)
        if not layer or layer.featureCount() == 0:
            return
        feat = next(layer.getFeatures())
        self._survey_polygon     = feat.geometry()
        self._survey_polygon_crs = layer.crs()
        self._on_clear_preview(reset_area=False)
        area_ha = self._area_ha()
        self.areaLabel.setText(f'{area_ha:.2f} ha')
        self._update_stats()

    def _on_survey_area_geometry_changed(self, _fid, geom):
        """Update the stored polygon in real-time as the geometry is being edited."""
        if not self._survey_area_layer_id:
            return
        layer = QgsProject.instance().mapLayer(self._survey_area_layer_id)
        if not layer:
            return
        self._survey_polygon     = geom
        self._survey_polygon_crs = layer.crs()
        self._on_clear_preview(reset_area=False)
        self.areaLabel.setText(f'{self._area_ha():.2f} ha')
        self._update_stats()

    def _on_remove_drawn_polygon(self):
        """Remove the drawn polygon and reset the survey area."""
        self._remove_survey_area_layer()
        self._on_clear_preview(reset_area=False)
        self._survey_polygon     = None
        self._survey_polygon_crs = None
        self._waypoints          = []
        self._shot_spacing_m     = 0.0
        self.removePolygonBtn.setVisible(False)
        self._clear_stats()
        self.iface.mapCanvas().refresh()

    def _remove_survey_area_layer(self):
        """Remove the temporary drawn-polygon layer if it exists."""
        if self._survey_area_layer_id:
            layer = QgsProject.instance().mapLayer(self._survey_area_layer_id)
            if layer:
                try:
                    layer.editingStopped.disconnect(self._on_survey_area_edited)
                    layer.geometryChanged.disconnect(self._on_survey_area_geometry_changed)
                except Exception:
                    pass
                QgsProject.instance().removeMapLayer(self._survey_area_layer_id)
            self._survey_area_layer_id = None
        self.removePolygonBtn.setVisible(False)

    def _on_drawing_cancelled(self):
        self.drawPolygonBtn.setChecked(False)
        self.drawPolygonBtn.setText('Draw Polygon on Map')
        if self._prev_map_tool:
            self.iface.mapCanvas().setMapTool(self._prev_map_tool)
            self._prev_map_tool = None

    def _cancel_draw_tool(self):
        if self._draw_tool:
            self.iface.mapCanvas().unsetMapTool(self._draw_tool)
            self._draw_tool = None

    def _area_ha(self):
        """Return survey polygon area in hectares (metric, via EPSG:3857)."""
        if self._survey_polygon is None:
            return 0.0
        utm = QgsCoordinateReferenceSystem('EPSG:3857')
        xf  = QgsCoordinateTransform(
            self._survey_polygon_crs, utm, QgsProject.instance()
        )
        g = QgsGeometry(self._survey_polygon)
        g.transform(xf)
        return g.area() / 10_000

    # ── Auto direction ────────────────────────────────────────────────────

    def _on_auto_direction(self):
        if not self._has_survey_area(silent=True):
            QMessageBox.information(
                self, 'No Survey Area',
                'Define a survey area first to enable automatic direction optimisation.'
            )
            return
        fw, _ = self._footprint()
        if fw is None:
            return
        line_spacing = fw * (1.0 - self.sideOverlapSpin.value() / 100.0)
        best = find_optimal_direction(
            self._survey_polygon, self._survey_polygon_crs, line_spacing
        )
        self.directionSpin.setValue(best)

    # ── Statistics ────────────────────────────────────────────────────────

    def _update_stats(self):
        if not self._has_survey_area(silent=True):
            self._clear_stats()
            return
        drone = self.droneModelCombo.currentText()
        if drone not in DRONE_SPECS:
            self._clear_stats()
            return

        s     = DRONE_SPECS[drone]
        speed = self.speedSpin.value()
        fw, fh = self._footprint()
        if fw is None:
            self._clear_stats()
            return

        line_spacing   = max(fw * (1.0 - self.sideOverlapSpin.value()  / 100.0), 0.5)
        actual_spacing = max(speed * self.photoIntervalSpin.value(), 0.5)

        utm = QgsCoordinateReferenceSystem('EPSG:3857')
        xf  = QgsCoordinateTransform(
            self._survey_polygon_crs, utm, QgsProject.instance()
        )
        g = QgsGeometry(self._survey_polygon)
        g.transform(xf)
        bbox  = g.boundingBox()
        a_rad = math.radians(self.directionSpin.value())

        across = (abs(bbox.width()  * math.cos(a_rad)) +
                  abs(bbox.height() * math.sin(a_rad)))
        along  = (abs(bbox.width()  * math.sin(a_rad)) +
                  abs(bbox.height() * math.cos(a_rad)))

        n_lines    = max(1, math.ceil(across / line_spacing) + 1)
        dist_m     = n_lines * along + (n_lines - 1) * line_spacing
        n_photos   = max(0, int(dist_m / actual_spacing))
        flight_min = dist_m / (speed * 60) if speed > 0 else 0
        batteries  = math.ceil(flight_min / s['battery_time_min'])
        area_ha    = g.area() / 10_000

        self.flightTimeLabel.setText(f'{flight_min:.1f} min')
        self.distanceLabel.setText(f'{dist_m / 1000:.2f} km')
        self.photosLabel.setText(f'{n_photos:,}')
        self.linesLabel.setText(str(n_lines))
        self.batteriesLabel.setText(str(batteries))
        self.coverageLabel.setText(f'{area_ha:.2f} ha')

    def _clear_stats(self):
        for attr in ('flightTimeLabel', 'distanceLabel', 'photosLabel',
                     'linesLabel', 'batteriesLabel', 'coverageLabel'):
            getattr(self, attr).setText('—')
        self.areaLabel.setText('—')
        # GSD and Interval depend only on drone + altitude, not on a survey
        # polygon — always recompute them rather than blanking them out.
        self._update_gsd()
        self._update_interval()

    # ── Map preview ───────────────────────────────────────────────────────

    def _on_preview(self):
        if not self._has_survey_area():
            return
        result = self._generate_waypoints()
        if result is None:
            return
        waypoints, shot_spacing_m = result
        self._waypoints      = waypoints
        self._shot_spacing_m = shot_spacing_m
        self._on_clear_preview(reset_area=False)
        line_layer = self._build_path_layer(waypoints)
        wp_layer   = self._build_waypoints_layer(waypoints)
        self._preview_layer_ids = [line_layer.id(), wp_layer.id()]
        self.iface.mapCanvas().refresh()

    def _build_path_layer(self, waypoints):
        """Create and register a yellow LineString layer for the flight path."""
        layer = QgsVectorLayer(
            'LineString?crs=EPSG:4326&field=id:integer',
            'FlyPath — Path', 'memory'
        )
        layer.setCustomProperty('flypath_internal', True)
        feat = QgsFeature()
        feat.setGeometry(QgsGeometry.fromPolylineXY(
            [QgsPointXY(lon, lat) for lon, lat in waypoints]
        ))
        feat.setAttributes([0])
        layer.dataProvider().addFeatures([feat])
        layer.renderer().setSymbol(QgsLineSymbol.createSimple({
            'color': '#FFE600', 'width': '0.8',
            'capstyle': 'round', 'joinstyle': 'round',
        }))
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _build_waypoints_layer(self, waypoints):
        """Create and register a rule-based Point layer for waypoint markers."""
        layer = QgsVectorLayer(
            'Point?crs=EPSG:4326&field=seq:integer&field=wp_type:string(10)',
            'FlyPath — Waypoints', 'memory'
        )
        layer.setCustomProperty('flypath_internal', True)

        last_idx  = len(waypoints) - 1
        wp_feats  = []
        for i, (lon, lat) in enumerate(waypoints):
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
            if i == 0:
                wp_type = 'start'
            elif i == last_idx:
                wp_type = 'end'
            else:
                wp_type = 'mid'
            f.setAttributes([i + 1, wp_type])
            wp_feats.append(f)
        layer.dataProvider().addFeatures(wp_feats)

        root = QgsRuleBasedRenderer.Rule(None)
        for expr, color, border, size, label in [
            ('"wp_type" = \'start\'', _COLOR_START_MARKER, _COLOR_MID_MARKER, '7.5', 'Start'),
            ('"wp_type" = \'end\'',   _COLOR_END_MARKER,   _COLOR_MID_MARKER, '7.5', 'End'),
            ('"wp_type" = \'mid\'',   _COLOR_MID_MARKER,   '#FFE600',         '4.0', 'Waypoint'),
        ]:
            sym = QgsMarkerSymbol.createSimple({
                'name': 'circle', 'color': color,
                'outline_color': border, 'outline_width': '0.4',
                'size': size,
            })
            root.appendChild(QgsRuleBasedRenderer.Rule(sym, filterExp=expr, label=label))
        layer.setRenderer(QgsRuleBasedRenderer(root))

        lbl = QgsPalLayerSettings()
        lbl.fieldName = 'seq'
        try:
            lbl.placement = Qgis.LabelPlacement.OverPoint
        except AttributeError:
            lbl.placement = QgsPalLayerSettings.OverPoint
        lbl.priority = 10
        fmt = QgsTextFormat()
        fmt.setFont(QFont('Segoe UI', 7, _FontBold))
        fmt.setColor(QColor('#1E2128'))
        fmt.setSize(7)
        lbl.setFormat(fmt)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(lbl))
        layer.setLabelsEnabled(True)

        QgsProject.instance().addMapLayer(layer)
        return layer

    def _on_clear_preview(self, reset_area=True):
        # Always remove the flight-path preview layers
        for lid in self._preview_layer_ids:
            if QgsProject.instance().mapLayer(lid):
                QgsProject.instance().removeMapLayer(lid)
        self._preview_layer_ids = []

        if reset_area:
            # Full reset — also remove the survey boundary layer
            self._remove_survey_area_layer()
            self._clear_layer_selection()
            self._survey_polygon     = None
            self._survey_polygon_crs = None
            self._waypoints          = []
            self._shot_spacing_m     = 0.0
            self.areaLabel.setText('—')
            self.layerCombo.setCurrentIndex(0)
            self.featureCombo.clear()
            self.featureCombo.setVisible(False)
            self._clear_stats()

        self.iface.mapCanvas().refresh()

    # ── Export ────────────────────────────────────────────────────────────

    # Standard DJI waypoint subpath on the RC internal storage
    _DJI_WAYPOINT_SUBPATH = 'Android/data/dji.go.v5/files/waypoint'

    def _on_browse_rc_path(self):
        """
        Open File Explorer at 'This PC' so the user can navigate to the DJI RC,
        copy the waypoint folder path from the address bar, and paste it here.
        MTP devices like DJI RC 2 only appear in Windows Explorer — they cannot
        be accessed via a standard file dialog.
        """
        # ::{20D04FE0-3AEA-1069-A2D8-08002B30309D} is the CLSID for "This PC"
        explorer_exe = os.path.join(
            os.environ.get('SystemRoot', r'C:\Windows'), 'explorer.exe'
        )
        try:
            subprocess.Popen(
                [explorer_exe, '::{20D04FE0-3AEA-1069-A2D8-08002B30309D}']
            )
        except Exception as exc:
            QMessageBox.warning(self, 'Could Not Open Explorer',
                                f'Failed to open File Explorer:\n{exc}')
            return

        QMessageBox.information(
            self, 'Open File Explorer',
            'File Explorer has been opened at "This PC".\n\n'
            'Steps:\n'
            '  1. Navigate to your DJI RC:\n'
            '     DJI RC 2 \u203a Internal shared storage\n'
            '     \u203a Android \u203a data \u203a dji.go.v5 \u203a files \u203a waypoint\n\n'
            '  2. Click the address bar at the top of Explorer\n'
            '     to reveal and select the full path.\n\n'
            '  3. Copy it (Ctrl+C) and paste it into the\n'
            '     RC path field, then click Set.'
        )

    def _on_rc_path_changed(self, text):
        QSettings('FlyPath', 'FlyPath').setValue('rc_waypoint_dir', text.strip())

    # DJI mission UUID folder format: 8-4-4-4-12 hex characters
    _UUID_RE = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}'
        r'-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )

    def _latest_mission_kmz(self, rc_waypoint_dir):
        """
        Find the KMZ file inside the most recently modified UUID folder
        in the RC waypoint directory.  Returns the KMZ filepath or None.
        Only considers folders whose names match the DJI UUID format.
        """
        try:
            folders = [
                os.path.join(rc_waypoint_dir, d)
                for d in os.listdir(rc_waypoint_dir)
                if (os.path.isdir(os.path.join(rc_waypoint_dir, d)) and
                    self._UUID_RE.match(d))
            ]
            if not folders:
                return None
            latest = max(folders, key=os.path.getmtime)
            uuid_name = os.path.basename(latest)
            kmz_path  = os.path.join(latest, uuid_name + '.kmz')
            return kmz_path if os.path.exists(kmz_path) else None
        except Exception:
            return None

    def _write_mission_kmz(self, filepath, waypoints, mission):
        """Write the KMZ file using current UI parameter values."""
        write_kmz(
            filepath=filepath,
            waypoints=waypoints,
            drone_name=self.droneModelCombo.currentText(),
            altitude_m=self.altitudeSpin.value(),
            speed_ms=self.speedSpin.value(),
            finish_action_label=self.finishActionCombo.currentText(),
            rc_lost_action_label=self.rcLostActionCombo.currentText(),
            gimbal_pitch=self.gimbalAngleSpin.value(),
            mission_name=mission,
        )

    def _resolve_local_export_path(self, rc_dir):
        """
        Return the target .kmz path for a local or network drive export.
        Shows any necessary confirmation dialogs.
        Returns None if the user cancels or a directory cannot be created.
        """
        if not os.path.isdir(rc_dir):
            reply = QMessageBox.question(
                self, 'Create Folder?',
                f'The folder does not exist:\n{rc_dir}\n\n'
                f'Create it and save FlyPath_Mission.kmz there?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return None
            try:
                os.makedirs(rc_dir, exist_ok=True)
            except Exception as exc:
                QMessageBox.critical(self, 'Cannot Create Folder', str(exc))
                return None

        kmz = self._latest_mission_kmz(rc_dir)
        if kmz:
            uuid_name = os.path.basename(os.path.dirname(kmz))
            reply = QMessageBox.question(
                self, 'Replace RC Mission?',
                f'Replace the latest mission on the RC?\n\n'
                f'UUID: {uuid_name}\n'
                f'File: {kmz}',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return None
            return kmz

        return os.path.join(rc_dir, 'FlyPath_Mission.kmz')

    def _on_export(self):
        if not self._has_survey_area():
            return
        mission = 'FlyPath Mission'

        # ── Resolve waypoints first (needed for all export paths) ─────────
        if self._waypoints and self._shot_spacing_m:
            waypoints      = self._waypoints
            shot_spacing_m = self._shot_spacing_m
        else:
            result = self._generate_waypoints()
            if result is None:
                return
            waypoints, shot_spacing_m = result

        rc_dir   = self.rcPathEdit.text().strip()
        filepath = None

        if rc_dir:
            drive, _ = os.path.splitdrive(rc_dir)
            is_local = bool(drive) or rc_dir.startswith('\\\\')

            if is_local:
                filepath = self._resolve_local_export_path(rc_dir)
                if filepath is None:
                    return
            else:
                # ── MTP device path (e.g. "This PC\DJI RC 2\...") ─────────
                ok, detail = self._export_to_mtp_rc(rc_dir, mission,
                                                     waypoints, shot_spacing_m)
                if ok:
                    QMessageBox.information(
                        self, 'Exported to RC',
                        f'Waypoints: {len(waypoints):,}  ·  '
                        f'Interval: {self.photoIntervalSpin.value():.1f} s\n\n'
                        f'Replaced mission on RC:\n{detail}'
                    )
                else:
                    QMessageBox.critical(self, 'RC Export Failed', detail)
                return

        # ── Fall back to standard save dialog ─────────────────────────────
        if not filepath:
            filepath, _ = QFileDialog.getSaveFileName(
                self, 'Export Mission KMZ',
                'FlyPath_Mission.kmz',
                'DJI Mission File (*.kmz)'
            )
        if not filepath:
            return

        try:
            self._write_mission_kmz(filepath, waypoints, mission)
            QMessageBox.information(
                self, 'Export Complete',
                f'Waypoints: {len(waypoints):,}  ·  '
                f'Interval: {self.photoIntervalSpin.value():.1f} s\n\n'
                f'Saved to:\n{filepath}'
            )
        except Exception as exc:
            QMessageBox.critical(self, 'Export Failed', str(exc))

    def _export_to_mtp_rc(self, rc_dir, mission, waypoints, shot_spacing_m):
        """
        Export the KMZ directly to a DJI RC connected as an MTP device.

        Shell.Namespace() cannot resolve 'This PC\\...' paths directly.
        Instead we navigate step-by-step from the 'This PC' CLSID using
        GetFolder, which works with MTP virtual filesystem items.

        Returns (success: bool, detail: str)
          success=True  → detail is the UUID that was replaced
          success=False → detail is a human-readable error message
        """
        ps_exe = os.path.join(
            os.environ.get('SystemRoot', r'C:\Windows'),
            r'System32\WindowsPowerShell\v1.0\powershell.exe'
        )
        rc_norm  = rc_dir.replace('/', '\\')
        if rc_norm.lower().startswith('this pc\\'):
            rc_norm = rc_norm[len('this pc\\'):]
        parts    = [p for p in rc_norm.split('\\') if p]
        ps_parts = ', '.join("'" + p.replace("'", "''") + "'" for p in parts)
        nav      = self._mtp_nav_fragment(ps_parts)

        tmp_dir = tempfile.mkdtemp(prefix='flypath_')
        try:
            uuid_name, err = self._mtp_find_uuid(ps_exe, nav, tmp_dir, rc_dir)
            if uuid_name is None:
                return False, err

            tmp_kmz = os.path.join(tmp_dir, uuid_name + '.kmz')
            try:
                self._write_mission_kmz(tmp_kmz, waypoints, mission)
            except Exception as exc:
                return False, f'Could not write KMZ: {exc}'

            return self._mtp_copy_kmz(ps_exe, nav, tmp_dir, uuid_name, tmp_kmz)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def _mtp_nav_fragment(ps_parts):
        """Return the PowerShell fragment that navigates from 'This PC' to the waypoint folder."""
        return (
            '$shell = New-Object -ComObject Shell.Application\n'
            "$folder = $shell.Namespace('::{20D04FE0-3AEA-1069-A2D8-08002B30309D}')\n"
            '$parts = @(' + ps_parts + ')\n'
            'foreach ($part in $parts) {\n'
            '    $found = $null\n'
            '    foreach ($item in $folder.Items()) {\n'
            '        if ($item.Name -eq $part) { $found = $item; break }\n'
            '    }\n'
            '    if (-not $found) {\n'
            '        foreach ($item in $folder.Items()) {\n'
            '            if ($item.Name -like ("*" + $part + "*")) { $found = $item; break }\n'
            '        }\n'
            '    }\n'
            f'    if (-not $found) {{ Write-Error ("Not found: " + $part); exit {_MTP_EXIT_NAV_FAIL} }}\n'
            '    $next = $found.GetFolder\n'
            f'    if (-not $next) {{ Write-Error ("Cannot open: " + $part); exit {_MTP_EXIT_NAV_FAIL} }}\n'
            '    $folder = $next\n'
            '}\n'
        )

    @staticmethod
    def _mtp_find_uuid(ps_exe, nav, tmp_dir, rc_dir):
        """
        Run Script 1: navigate to waypoint folder and return the latest UUID folder name.

        Returns (uuid_name, None) on success, or (None, error_message) on failure.
        """
        find_ps = os.path.join(tmp_dir, 'find_uuid.ps1')
        with open(find_ps, 'w', encoding='utf-8') as fh:
            fh.write(
                nav +
                '$uuidPattern = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"\n'
                '$latest = $null; $latestDate = [DateTime]::MinValue\n'
                'foreach ($item in $folder.Items()) {\n'
                '    if ($item.IsFolder -and $item.Name -match $uuidPattern -and $item.ModifyDate -gt $latestDate) {\n'
                '        $latestDate = $item.ModifyDate; $latest = $item\n'
                '    }\n'
                '}\n'
                f'if (-not $latest) {{ exit {_MTP_EXIT_NO_UUID} }}\n'
                'Write-Output $latest.Name\n'
            )

        try:
            r = subprocess.run(
                [ps_exe, '-NoProfile', '-NonInteractive',
                 '-ExecutionPolicy', 'Bypass', '-File', find_ps],
                capture_output=True, text=True, timeout=30
            )
        except subprocess.TimeoutExpired:
            return None, 'Timed out reading the RC waypoint folder.\nCheck the RC is connected via USB.'
        except Exception as exc:
            return None, f'PowerShell error: {exc}'

        if r.returncode == _MTP_EXIT_NAV_FAIL:
            return None, (
                'Could not navigate to the RC waypoint folder.\n\n'
                f'Path used:\n{rc_dir}\n\n'
                'Check that the RC is connected via USB and the path is correct.\n\n'
                f'Details:\n{r.stderr.strip()}'
            )
        if r.returncode == _MTP_EXIT_NO_UUID or not r.stdout.strip():
            return None, (
                'No valid mission folder found on the RC.\n\n'
                'Open DJI Fly on the RC, create a waypoint mission '
                '(even a 3-point dummy), then export again.\n\n'
                'FlyPath only replaces folders with a valid DJI UUID name.'
            )
        return r.stdout.strip().splitlines()[0].strip(), None

    @staticmethod
    def _mtp_copy_kmz(ps_exe, nav, tmp_dir, uuid_name, tmp_kmz):
        """
        Run Script 2: copy the KMZ into the UUID subfolder on the RC via Shell.CopyHere.

        Returns (True, uuid_name) on success, or (False, error_message) on failure.
        """
        tmp_kmz_ps = tmp_kmz.replace('/', '\\')
        copy_ps = os.path.join(tmp_dir, 'copy_kmz.ps1')
        with open(copy_ps, 'w', encoding='utf-8') as fh:
            fh.write(
                nav +
                "$uuid = '" + uuid_name.replace("'", "''") + "'\n"
                '$uuidItem = $null\n'
                'foreach ($item in $folder.Items()) {\n'
                '    if ($item.Name -eq $uuid) { $uuidItem = $item; break }\n'
                '}\n'
                f'if (-not $uuidItem) {{ Write-Error "UUID folder not found on RC"; exit {_MTP_EXIT_UUID_MISSING} }}\n'
                '$uuidFolder = $uuidItem.GetFolder\n'
                f'if (-not $uuidFolder) {{ Write-Error "Cannot open UUID folder"; exit {_MTP_EXIT_UUID_NO_OPEN} }}\n'
                # 0x10 = FOF_NOCONFIRMATION — keep progress UI so Windows Shell drives the MTP transfer
                "$uuidFolder.CopyHere('" + tmp_kmz_ps.replace("'", "''") + "', 0x10)\n"
                # CopyHere is async — sleep before PowerShell exits and tears down the COM apartment
                'Start-Sleep -Seconds 8\n'
                'Write-Output "OK"\n'
            )

        try:
            r2 = subprocess.run(
                [ps_exe, '-NoProfile', '-NonInteractive', '-STA',
                 '-ExecutionPolicy', 'Bypass', '-File', copy_ps],
                capture_output=True, text=True, timeout=60
            )
        except subprocess.TimeoutExpired:
            return False, 'Copy to RC timed out. Check the RC is still connected.'
        except Exception as exc:
            return False, f'Copy error: {exc}'

        if r2.returncode == 0 and 'OK' in r2.stdout:
            return True, uuid_name
        if 'TIMEOUT' in r2.stdout:
            return False, 'Copy to RC timed out waiting for the file to appear.'
        return False, (
            f'Copy to RC failed (exit {r2.returncode}).\n'
            f'{r2.stderr.strip() or r2.stdout.strip()}'
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def cleanup(self):
        """Remove all FlyPath-owned QGIS layers. Called on plugin unload."""
        self._disconnect_layer_signals()
        self._remove_survey_area_layer()
        self._on_clear_preview(reset_area=False)
        # Belt-and-suspenders: remove any remaining flypath_internal layers
        # (e.g. if the user moved the panel or state got out of sync)
        to_remove = [
            lid for lid, layer in QgsProject.instance().mapLayers().items()
            if layer.customProperty('flypath_internal')
        ]
        for lid in to_remove:
            QgsProject.instance().removeMapLayer(lid)
        try:
            QgsProject.instance().layersAdded.disconnect(self._refresh_layer_combo)
            QgsProject.instance().layersRemoved.disconnect(self._refresh_layer_combo)
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def _has_survey_area(self, silent=False):
        if self._survey_polygon is None or self._survey_polygon_crs is None:
            if not silent:
                QMessageBox.information(
                    self, 'No Survey Area',
                    'Draw a polygon on the map or select a polygon layer first.'
                )
            return False
        return True

    def _generate_waypoints(self):
        """
        Returns (waypoints, shot_spacing_m) or None on failure.
        waypoints is a list of (lon, lat) turn points only.
        """
        drone = self.droneModelCombo.currentText()
        if drone not in DRONE_SPECS:
            return None
        shot_spacing_m = max(
            self.speedSpin.value() * self.photoIntervalSpin.value(), 0.5
        )
        try:
            waypoints, shot_spacing_m = generate_flight_grid(
                polygon_geom=self._survey_polygon,
                polygon_crs=self._survey_polygon_crs,
                altitude_m=self.altitudeSpin.value(),
                shot_spacing_m=shot_spacing_m,
                side_overlap=self.sideOverlapSpin.value() / 100.0,
                direction_deg=self.directionSpin.value(),
                margin_m=self.marginSpin.value(),
                drone_specs=DRONE_SPECS[drone],
            )
        except ValueError as exc:
            QMessageBox.warning(self, 'Cannot Generate Grid', str(exc))
            return None
        return waypoints, shot_spacing_m
