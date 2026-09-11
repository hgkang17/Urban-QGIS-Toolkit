import os
import inspect
import re
import sys
import subprocess
import glob

from qgis.PyQt import uic, QtWidgets, QtGui, QtCore
from qgis.PyQt.QtWidgets import (QAction, QDockWidget, QVBoxLayout, QLabel,
                                 QWidget, QTabWidget, QScrollArea, QMessageBox, QFileDialog, QStyleFactory)
from qgis.PyQt.QtGui import (QStandardItemModel, QStandardItem, QIcon,
                             QColor, QPalette, QFontDatabase)
from qgis.PyQt.QtCore import (QVariant, pyqtSignal, QSettings, QTranslator,
                              QCoreApplication, Qt, QFileInfo, QThread, QTimer, QObject)

from qgis.PyQt.QtCore import QVariant, pyqtSignal, QSettings, QTranslator, QCoreApplication, Qt, QFileInfo, QThread, QTimer
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox, QLineEdit, QToolButton

from qgis.PyQt.QtCore import QCoreApplication, QObject, pyqtSignal, QSize
from qgis.core import *
from .resources import *

from .mnum_symbol import mnum_symbol
from .area_cal import area_cal
from .vworld_login import vworld_backend_login, vworld_backend_search
from .line_Width import change_line_width
from .eum_search_file import function_search_eum
from .kakao_search_file import kakao_search_function
from .utils import check_playwright_installed
from .eum_kakao_point_file import function_point_eum, function_point_kakao
from .PNU_file import PNU_cal
from .eum_kaka_qgis_search_file import show_Shading_on_map
from .Kras_api_file import show_map_Vworld_2Dapi
from .WFS_api_file import (
    show_all_Vworld_WFS_native,
    show_map_Vworld_WFS_native,
    show_map_Vworld_WFS,
)
from .dict_DB import tree_structure, group_data, wfs_tree_structure
from .Vworld_sate_file import load_vworld_satellite
from .zoom_file import activate_drag_zoom
from .SymBol_CopyPaste_file import copy_symbol, paste_symbol
from .Symbol_tools_file import clear_symbol, clear_symbol_fill_this, clear_symbol_outline_this, fill_symbol_del,outline_symbol_del, open_symbol_color_dialog, set_white_outline, set_red_dashdotdot_outline
from .select_layer_file import isolate_selected_layers, restore_previous_visibility, move_selected_to_top
from .JPG_export_file import export_canvas_to_jpg
from .Simple_search_file import (
    install_address_autocomplete,
    open_simple_search,
)
from .labe_file import label_buffer
from .update_check import check_for_update
from .tree_search_filter import RecursiveFilterProxyModel


cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]
def run_installer_background(qgis_path, qgis_version, commands, startupinfo):
    try:
        proc = subprocess.Popen(
            f'cmd /c "{commands}"',
            shell=True,
            cwd=qgis_path,
            startupinfo=startupinfo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = proc.communicate()

        if proc.returncode == 0:
            print(f"\n[OK] QGIS {qgis_version} 환경에서 Playwright 패키지 설치가 완전히 완료되었습니다! 이제 기능을 사용하실 수 있습니다.")
        else:
            print(f"\n[ERROR] QGIS {qgis_version} 환경 설치 중 문제가 발생했습니다. (종료 코드: {proc.returncode})")
            if stderr:
                print(f"[ERROR] 에러 내용: {stderr.decode('cp949', errors='ignore')}")

    except Exception as e:
        print(f"\n[ERROR] 백그라운드 감시 중 예외 발생: {e}")

class GuiDockWidget(QDockWidget):
    closingPlugin = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface

        ui_file_path = os.path.join(cmd_folder, 'khgv3.ui')
        uic.loadUi(ui_file_path, self)

        self.vworld_browser = None

        search_icon_path = os.path.join(cmd_folder, 'icons', 'search.svg')
        search_icon = QIcon(search_icon_path)
        action_button_style = """ 
            QToolButton {border: none; background: transparent; border-radius: 3px;}
            QToolButton:hover {background-color: rgba(42, 120, 214, 40);}
            QToolButton:pressed {background-color: rgba(42, 120, 214, 90);}
        """
        def make_line_edit_button(line_edit, icon):
            button = QToolButton(line_edit)
            button.setIcon(icon)
            button.setIconSize(QSize(16, 16))
            button.setFixedSize(20, 20)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(action_button_style)

            button_layout = QtWidgets.QHBoxLayout(line_edit)
            button_layout.setContentsMargins(0, 0, 2, 0)
            button_layout.setSpacing(0)
            button_layout.addStretch(1)
            button_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
            line_edit.setTextMargins(0, 0, 24, 0)
            return button

        self.btn_zoom.clicked.connect(lambda: activate_drag_zoom(self.iface))
        self.btn_jpg_export.clicked.connect(lambda: export_canvas_to_jpg(self.iface, self))
        self.btn_select_layer.clicked.connect(lambda: isolate_selected_layers(self.iface, self))
        self.btn_select_layer_up.clicked.connect(lambda: move_selected_to_top(self.iface, self))
        self.btn_Vworld_satellite.clicked.connect(lambda: load_vworld_satellite(self))

        self.undo_visibility_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence(Qt.Key.Key_Backspace), self.iface.mainWindow())
        self.undo_visibility_shortcut.activated.connect(lambda: restore_previous_visibility(self.iface, self))

        self.btn_Symbol_Color.clicked.connect(lambda: open_symbol_color_dialog(self.iface, self))
        self.btn_SymBol_copy.clicked.connect(lambda: copy_symbol(self.iface, self))
        self.btn_SymBol_paste.clicked.connect(lambda: paste_symbol(self.iface, self))
        self.btn_Symbol_Clear_fill_this.clicked.connect(lambda: clear_symbol_fill_this(self.iface, self))
        self.btn_Symbol_Clear_outline_this.clicked.connect(lambda: clear_symbol_outline_this(self.iface, self))
        self.btn_white_line.clicked.connect(lambda: set_white_outline(self.iface, self))
        self.btn_red2point_line.clicked.connect(lambda: set_red_dashdotdot_outline(self.iface, self))
        self.btn_Symbol_Clear.clicked.connect(lambda: clear_symbol(self.iface, self))
        self.btn_Symbol_fill_del.clicked.connect(lambda: fill_symbol_del(self.iface, self))
        self.btn_Symbol_outline_del.clicked.connect(lambda: outline_symbol_del(self.iface, self))
        self.btn_label_buffer.clicked.connect(lambda: label_buffer(self.iface, self))
        self.btn_line.clicked.connect(lambda: change_line_width(self.iface, self))
        self.input_line_width.returnPressed.connect(lambda: self.btn_line.click())
        self.input_line_width_btn = make_line_edit_button(self.input_line_width,QgsApplication.getThemeIcon('mIconSuccess.svg'))
        self.input_line_width_btn.clicked.connect(lambda: self.btn_line.click())

        self.btn_MNUM_SymBol.clicked.connect(lambda: mnum_symbol(self.iface, self))
        self.btn_area_cal.clicked.connect(lambda: area_cal(self.iface, self))
        self.btn_PNU.clicked.connect(lambda: PNU_cal(self.iface, self))

        self.progressBar.setValue(0)
        self.label_percent.hide()
        self.progressBar.setTextVisible(False)

        progress_parent = self.progressBar.parentWidget()
        progress_parent_layout = progress_parent.layout()
        progress_index = progress_parent_layout.indexOf(self.progressBar)
        progress_parent_layout.removeWidget(self.progressBar)

        self.progress_row = QWidget(progress_parent)
        self.progress_row.setFixedHeight(15)
        progress_row_layout = QtWidgets.QHBoxLayout(self.progress_row)
        progress_row_layout.setContentsMargins(0, 0, 0, 0)
        progress_row_layout.setSpacing(6)

        self.progressBar.setParent(self.progress_row)
        self.progressBar.setMinimumWidth(0)
        self.progressBar.setMaximumWidth(16777215)
        self.progressBar.setFixedHeight(13)

        self.progress_percent_label = QLabel(self.progress_row)
        self.progress_percent_label.setObjectName("progress_percent_overlay")
        self.progress_percent_label.setFixedWidth(35)
        self.progress_percent_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.progress_percent_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.progress_percent_label.setStyleSheet(
            'background: transparent; color: rgb(85, 93, 109); '
            'font-family: "Noto Sans KR"; font-size: 9pt; font-weight: 레귤러; '
            'padding-bottom: 2px;'
        )
        self.progress_percent_label.setText("0%")
        progress_row_layout.addWidget(self.progressBar, 1)
        progress_row_layout.addWidget(self.progress_percent_label, 0)
        progress_parent_layout.insertWidget(progress_index, self.progress_row)


        self.btn_Simple_search.clicked.connect(lambda: open_simple_search(self.iface, self))

        status_font = QtGui.QFont("Noto Sans KR", 9)
        for status_label in (self.eum_kakao_status, self.Vworld_status):
            status_label.setFixedSize(190, 15)
            status_label.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed
            )
            status_label.setFont(status_font)
            status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        pin_icon_path = os.path.join(cmd_folder, 'icons', 'pin.svg')

        self.search_btn_kakao = make_line_edit_button(self.input_search_kakao, search_icon)
        self.search_btn_kakao.clicked.connect(lambda: kakao_search_function(self) if check_playwright_installed(self.iface) else None)
        self.search_btn_kakao.clicked.connect(lambda: show_Shading_on_map(self.iface, self) if check_playwright_installed(self.iface) else None)
        self.input_search_kakao.returnPressed.connect(self.search_btn_kakao.click)
        self.btn_point_kakao.clicked.connect(lambda: function_point_kakao(self.iface, self))
        self.btn_point_kakao.setIcon(QIcon(pin_icon_path))

        self.search_btn_eum = make_line_edit_button(self.input_search_eum, search_icon)
        self.search_btn_eum.clicked.connect(lambda: function_search_eum(self) if check_playwright_installed(self.iface) else None)
        self.search_btn_eum.clicked.connect(lambda: show_Shading_on_map(self.iface, self) if check_playwright_installed(self.iface) else None)
        self.input_search_eum.returnPressed.connect(self.search_btn_eum.click)
        self.btn_point_eum.clicked.connect(lambda: function_point_eum(self.iface, self))
        self.btn_point_eum.setIcon(QIcon(pin_icon_path))


        self.setTabOrder(self.input_id, self.input_pw)
        self.setTabOrder(self.input_pw, self.btn_login)

        self.btn_login.clicked.connect(lambda: vworld_backend_login(self) if check_playwright_installed(self.iface) else None)
        self.input_pw.returnPressed.connect(lambda: self.btn_login.click())

        self.search_btn_vworld = make_line_edit_button(self.input_search_vworld, search_icon)
        self.search_btn_vworld.clicked.connect(lambda: vworld_backend_search(self) if check_playwright_installed(self.iface) else None)
        self.input_search_vworld.returnPressed.connect(self.search_btn_vworld.click)


        settings = QgsSettings()
        save_api = settings.value("khg_plugin/save_api_checked", False, type=bool)
        save_id = settings.value("khg_plugin/save_id_checked", False, type=bool)
        save_pw = settings.value("khg_plugin/save_pw_checked", False, type=bool)

        self.cb_save_api.setChecked(save_api)
        self.input_API.setText(settings.value("khg_plugin/vworld_api_key", ""))

        self.cb_save_ID.setChecked(save_id)
        self.input_id.setText(settings.value("khg_plugin/vworld_id", ""))

        self.cb_save_PW.setChecked(save_pw)
        self.input_pw.setText(settings.value("khg_plugin/vworld_password", ""))

        api_key_getter = lambda: self.input_API.text() if hasattr(self, 'input_API') else ""
        install_address_autocomplete(self.input_search_kakao, api_key_getter)
        install_address_autocomplete(self.input_search_eum, api_key_getter)

        check_icon_path = os.path.join(cmd_folder, 'icons', 'check_white.svg').replace('\\', '/')
        for save_checkbox in (self.cb_save_api, self.cb_Temporary_api, self.cb_save_ID, self.cb_save_PW):
            save_checkbox.setStyleSheet(
                save_checkbox.styleSheet() + f"QCheckBox::indicator:checked {{ image: url({check_icon_path}); }}"
            )
        self._checkbox_label_targets = {}
        for label_name, checkbox in ((self.label_api, self.cb_save_api),(self.label_Temporary, self.cb_Temporary_api)):
            self._checkbox_label_targets[label_name] = checkbox
            label_name.setCursor(Qt.CursorShape.PointingHandCursor)
            label_name.installEventFilter(self)

        self.progressBar.valueChanged.connect(self._update_progress_percent)

        self.btn_clear_log.clicked.connect(self.log.clear)
        self.log_stream = LogStream()
        self.log_stream.textWritten.connect(self._append_log_line)
        sys.stdout = self.log_stream
        sys.stderr = self.log_stream

        self.treeView.doubleClicked.connect(self.on_tree_item_clicked)

        self.model = QStandardItemModel()
        self.tree_filter_model = RecursiveFilterProxyModel(self)
        self.tree_filter_model.setSourceModel(self.model)
        self.treeView.setModel(self.tree_filter_model)
        self.treeView.setHeaderHidden(True)
        self.setup_tree_data()
        self._tree_expanded = False
        self.input_tree_search.setClearButtonEnabled(True)
        self.input_tree_search.textChanged.connect(self._on_tree_search_changed)
        self.btn_tree_toggle_all.clicked.connect(self._on_tree_toggle_all_clicked)
        self.treeView.expanded.connect(self._on_tree_item_expanded)
        self.treeView.collapseAll()

    def eventFilter(self, watched, event):
            checkbox = getattr(self, "_checkbox_label_targets", {}).get(watched)
            if (event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton):
                checkbox.toggle()
                return True
            return super().eventFilter(watched, event)

    def setup_tree_data(self):
        root = QStandardItem(QgsApplication.getThemeIcon("mActionSelectAll.svg"), "브이월드 2D데이터 API (불러온 시점 고정데이터)")
        root.setData("vworld_2d", Qt.ItemDataRole.UserRole)
        root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.model.appendRow(root)

        middle_root = QStandardItem(QgsApplication.getThemeIcon("mActionAddBasicCircle.svg"), "도시관리계획도(2D API)")
        middle_root.setData("UrbanManagementPlan_2d", Qt.ItemDataRole.UserRole)
        middle_root.setFlags(middle_root.flags() & ~Qt.ItemFlag.ItemIsEditable)
        root.appendRow(middle_root)

        for middle_name, API_2D in tree_structure.items():
            middle_root = QStandardItem(QgsApplication.getThemeIcon("mActionFileOpen.svg"), middle_name)
            middle_root.setFlags(middle_root.flags() & ~Qt.ItemFlag.ItemIsEditable)
            root.appendRow(middle_root)

            for API_2D_name in API_2D:
                middle_child = QStandardItem(QgsApplication.getThemeIcon("mActionAddBasicCircle.svg"), API_2D_name)
                middle_child.setFlags(middle_child.flags() & ~Qt.ItemFlag.ItemIsEditable)
                middle_root.appendRow(middle_child)

        root2 = QStandardItem(QgsApplication.getThemeIcon("mActionSelectAll.svg"), "브이월드 WFS API (화면 이동시 자동반영)")
        root2.setData("vworld_wfs", Qt.ItemDataRole.UserRole)
        root2.setFlags(root2.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.model.appendRow(root2)

        middle_root = QStandardItem(QgsApplication.getThemeIcon("mActionAddBasicCircle.svg"),"도시관리계획도(WFS)",)
        middle_root.setData("UrbanManagementPlan_wfs", Qt.ItemDataRole.UserRole)
        middle_root.setFlags(middle_root.flags() & ~Qt.ItemFlag.ItemIsEditable)
        root2.appendRow(middle_root)

        for middle_name, API_wfs in wfs_tree_structure.items():
            middle_root = QStandardItem(QgsApplication.getThemeIcon("mActionFileOpen.svg"), middle_name)
            middle_root.setFlags(middle_root.flags() & ~Qt.ItemFlag.ItemIsEditable)
            root2.appendRow(middle_root)

            for API_wfs_name in API_wfs:
                middle_child = QStandardItem(QgsApplication.getThemeIcon("mActionAddBasicCircle.svg"), API_wfs_name)
                middle_child.setFlags(middle_child.flags() & ~Qt.ItemFlag.ItemIsEditable)
                middle_root.appendRow(middle_child)

    def _on_tree_toggle_all_clicked(self):
        self._tree_expanded = not self._tree_expanded
        if self._tree_expanded:
            self.treeView.expandAll()
            self.btn_tree_toggle_all.setText("접기")
        else:
            self.treeView.collapseAll()
            self.btn_tree_toggle_all.setText("펼치기")

    def _on_tree_item_expanded(self, index):
        if not index.parent().isValid():
            self._expand_tree_descendants(index)
    def _expand_tree_descendants(self, parent_index):
        for row in range(self.tree_filter_model.rowCount(parent_index)):
            child_index = self.tree_filter_model.index(row, 0, parent_index)
            self.treeView.expand(child_index)
            self._expand_tree_descendants(child_index)

    def _on_tree_search_changed(self, text):
        self.tree_filter_model.setSearchText(text)
        if text.strip():
            self.treeView.expandAll()
        elif self._tree_expanded:
            self.treeView.expandAll()
        else:
            self.treeView.collapseAll()


    def on_tree_item_clicked(self, index):
        source_index = self.tree_filter_model.mapToSource(index)
        item = self.model.itemFromIndex(source_index)
        root = QgsProject.instance().layerTreeRoot()

        if item.parent() is None:
            return


        top_ancestor = item
        while top_ancestor.parent() is not None:
            top_ancestor = top_ancestor.parent()
        tree_type = top_ancestor.data(Qt.ItemDataRole.UserRole)

        if tree_type == "vworld_wfs":
            if item.data(Qt.ItemDataRole.UserRole) == "UrbanManagementPlan_wfs":
                show_all_Vworld_WFS_native(self.iface, self)
                return
            if item.hasChildren():
                return

            def get_or_create_group(parent, name):
                group = parent.findGroup(name)
                if not group:
                    group = parent.insertGroup(0, name)
                return group

            target_group_name = item.parent().text() if item.parent() else None

            if self.cb_Temporary_api.isChecked():
                def add_layer_to_group(layer):
                    if layer and target_group_name:
                        group = get_or_create_group(root, target_group_name)
                        group.addLayer(layer)
                show_map_Vworld_WFS(self.iface, item.text(), self, add_to_API=False, on_done=add_layer_to_group)
            else:
                layer = show_map_Vworld_WFS_native(self.iface, item.text(), self, add_to_API=False)
                if layer and target_group_name:
                    group = get_or_create_group(root, target_group_name)
                    group.addLayer(layer)
            return

        is_urban_plan_2d = item.data(Qt.ItemDataRole.UserRole) == "UrbanManagementPlan_2d"
        if is_urban_plan_2d:

            def get_or_create_group(parent, name):
                group = parent.findGroup(name)
                if not group:
                    group = parent.insertGroup(0, name)
                return group

            group_top = get_or_create_group(root, "도시관리계획도(API)")
            group_zoning = get_or_create_group(group_top, "용도지역")
            group_District = get_or_create_group(group_top, "용도지구")
            group_zone = get_or_create_group(group_top, "구역")
            group_facility = get_or_create_group(group_top, "도시계획시설")

            category_groups = [
                ("도시계획시설", group_facility),
                ("구역", group_zone),
                ("용도지역", group_zoning),
                ("용도지구", group_District),
            ]

            for data_key, group in category_groups:
                for layer_name in group_data[data_key]:
                    layer = show_map_Vworld_2Dapi(self.iface, layer_name, self, show_warning=False, add_to_API=False)
                    if layer:
                        group.addLayer(layer)
                    QtWidgets.QApplication.processEvents()

        elif item.hasChildren():
            return
        else:
            def get_or_create_group(parent, name):
                group = parent.findGroup(name)
                if not group:
                    if name == "도시관리계획도(API)":
                        group = parent.insertGroup(0, name)
                    else:
                        group = parent.insertGroup(0, name)
                return group

            group_top = get_or_create_group(root, "도시관리계획도(API)")

            standalone_categories = ("토지이용", "산업단지", "기타")

            target_group_name = item.parent().text() if item.parent() else None

            layer = show_map_Vworld_2Dapi(self.iface, item.text(), self, add_to_API=False)
            if layer:
               if target_group_name :
                    if target_group_name in standalone_categories:
                        grou_name = get_or_create_group(root, target_group_name)
                    else:
                        grou_name = get_or_create_group(group_top, target_group_name)
                    grou_name.addLayer(layer)


    def closeEvent(self, event):

        if hasattr(self, 'input_API') and self.cb_save_api:
            settings = QgsSettings()
            is_checked = self.cb_save_api.isChecked()

            settings.setValue("khg_plugin/save_api_checked", is_checked)

            if is_checked:
                settings.setValue("khg_plugin/vworld_api_key", self.input_API.text())
            else:
                settings.remove("khg_plugin/vworld_api_key")
                self.input_API.setText("")

            save_id = bool(self.cb_save_ID and self.cb_save_ID.isChecked())
            save_pw = bool(self.cb_save_PW and self.cb_save_PW.isChecked())
            settings.setValue("khg_plugin/save_id_checked", save_id)
            settings.setValue("khg_plugin/save_pw_checked", save_pw)

            if save_id:
                settings.setValue("khg_plugin/vworld_id", self.input_id.text())
            else:
                settings.remove("khg_plugin/vworld_id")
                self.input_id.setText("")

            if save_pw:
                settings.setValue(
                    "khg_plugin/vworld_password", self.input_pw.text()
                )
            else:
                settings.remove("khg_plugin/vworld_password")
                self.input_pw.setText("")

        self.closingPlugin.emit()
        self.setMinimumSize(300, 0)
        event.accept()


    def _update_progress_percent(self, value):
        maximum = self.progressBar.maximum()
        percent = int(value / maximum * 100) if maximum else 0
        self.progress_percent_label.setText(f"{percent}%")
        self._position_progress_percent()

    def _position_progress_percent(self):
        if hasattr(self, 'progress_percent_label'):
            self.progress_percent_label.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_progress_percent()

    def showEvent(self, event):
        super().showEvent(event)
        self.setMinimumSize(380, 0)
        self._position_progress_percent()
        self._minsize_release_timer = QTimer(self)
        self._minsize_release_timer.setSingleShot(True)
        self._minsize_release_timer.timeout.connect(lambda: self.setMinimumSize(0, 0))
        self._minsize_release_timer.start(2000)

    def _append_log_line(self, text):
        scrollbar = self.log.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 4

        cursor = self.log.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)

        block_format = QtGui.QTextBlockFormat()
        block_format.setLeftMargin(30)
        block_format.setTextIndent(-27)
        if self.log.document().isEmpty():
            cursor.setBlockFormat(block_format)
        else:
            cursor.insertBlock(block_format)

        char_format = QtGui.QTextCharFormat()
        check_text = text[4:] if text.startswith(">>> ") else text
        if check_text.startswith('[WARN]'):
            char_format.setForeground(QColor(255, 170, 60))
            text = text.replace('[WARN]', '', 1).strip()
        elif check_text.startswith('[ERROR]'):
            char_format.setForeground(QColor(255, 90, 90))
            text = text.replace('[ERROR]', '', 1).strip()
        elif check_text.startswith('[OK]'):
            char_format.setForeground(QColor(0, 255, 0))
            text = text.replace('[OK]', '', 1).strip()
        else:
            char_format.setForeground(QColor(255, 255, 255))

        cursor.insertText(text, char_format)

        if was_at_bottom:
            self.log.setTextCursor(cursor)
            self.log.ensureCursorVisible()


class kAutoLoaderPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.pluginIsActive = False
        self.dockwidget = None


    def initGui(self):
        icon = os.path.join(cmd_folder, 'logo.png')
        self.action = QAction(QIcon(icon), '자동화', self.iface.mainWindow())
        self.iface.addToolBarIcon(self.action)
        self.action.triggered.connect(self.run)
        self.update_reply = check_for_update(self.iface, cmd_folder)

    def run(self):
        if not self.pluginIsActive:
            self.pluginIsActive = True

            if self.dockwidget is None:
                self.dockwidget = GuiDockWidget(self.iface, self.iface.mainWindow())

                self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dockwidget)

            self.dockwidget.show()

            self.dockwidget.closingPlugin.connect(self.onClosePlugin)

    def onClosePlugin(self):
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)
        self.pluginIsActive = False

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        del self.action

        if hasattr(self, 'dockwidget') and self.dockwidget:
            try:
                self.dockwidget.close()
                self.iface.removeDockWidget(self.dockwidget)
                self.dockwidget.deleteLater()
            except Exception as e:
                print(f"[ERROR] dockwidget 제거 중 오류: {e}")
            self.dockwidget = None

        try:
            existing_dock = self.iface.mainWindow().findChild(QDockWidget, "GuiDockWidget")
            if existing_dock:
                existing_dock.close()
                self.iface.removeDockWidget(existing_dock)
                existing_dock.deleteLater()
                print("기존에 남아있던 잔상 GuiDockWidget 창을 강제 종료했습니다.")
        except Exception as e:
            print(f"[ERROR] 잔상 위젯 탐색 중 오류: {e}")

        if (self.dockwidget and hasattr(self.dockwidget, "undo_visibility_shortcut")):
            self.dockwidget.undo_visibility_shortcut.setEnabled(False)
            self.dockwidget.undo_visibility_shortcut.deleteLater()

        self.pluginIsActive = True
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


import textwrap

class LogStream(QObject):
    textWritten = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._buffer = ""

    def write(self, text):
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self.textWritten.emit(">>> " + line.strip())

    def flush(self):
        pass
