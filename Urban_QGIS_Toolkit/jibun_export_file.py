
import os
import re
import tempfile

from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.core import (
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsExpression,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsFieldProxyModel,
    QgsMapLayerProxyModel,
    QgsProcessing,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProject,
    QgsRendererCategory,
    QgsSymbol,
    QgsVectorLayer,
    QgsVectorLayerJoinInfo,
    QgsWkbTypes,
)

from .elevation_analysis_file import setup_elevation_analysis
from .jibun_export_algorithm import JibunLabelDxfAlgorithm
from .Kras_api_file import show_map_Vworld_2Dapi
from .owner_classification_file import (
    aggregate_possession_records,
    build_pnu_queries,
    classify_owner_value,
    fetch_possession_records,
    normalize_pnu,
)


class DockProcessingFeedback(QgsProcessingFeedback):

    def __init__(self, progress_bar, status_label):
        super().__init__()
        self.progress_bar = progress_bar
        self.status_label = status_label

    def setProgress(self, progress):
        super().setProgress(progress)
        value = int(progress)
        self.progress_bar.setValue(value)
        self.status_label.setText(f"필지 계산 중... {value}%")
        QtWidgets.QApplication.processEvents()

    def pushInfo(self, info):
        super().pushInfo(info)
        print(f"[지번 내보내기] {info}")

    def reportError(self, error, fatalError=False):
        super().reportError(error, fatalError)
        print(f"[지번 내보내기 오류] {error}")


class JibunExportTabController(QtCore.QObject):

    JIMOK_ORDER = (
        "전", "답", "과", "목", "임", "광", "염", "대", "장", "학",
        "차", "주", "창", "도", "철", "제", "천", "구", "유", "양",
        "수", "공", "체", "원", "종", "사", "묘", "잡",
    )
    JIMOK_COLORS = (
        "#FFFB7B",
        "#C9FF53",
        "#FF8080",
        "#C8A060",
        "#0A9600",
        "#C04000",
        "#A0A0FF",
        "#FFBBF0",
        "#A500FF",
        "#00BAFF",
        "#646464",
        "#FF7C35",
        "#EA50FF",
        "#B1B1B1",
        "#505080",
        "#8C6E46",
        "#00FFFA",
        "#5BAAFF",
        "#FFDC7D",
        "#0064C8",
        "#40E0A0",
        "#6EE65A",
        "#B7DBEA",
        "#E06090",
        "#FF00D2",
        "#A05AA0",
        "#606030",
        "#FFFF7D",
    )
    JIMOK_COLOR_BY_VALUE = dict(zip(JIMOK_ORDER, JIMOK_COLORS))
    JIMOK_FULL_NAMES = (
        "전", "답", "과수원", "목장용지", "임야", "광천지", "염전", "대",
        "공장용지", "학교용지", "주차장", "주유소용지", "창고용지", "도로",
        "철도용지", "제방", "하천", "구거", "유지", "양어장", "수도용지",
        "공원", "체육용지", "유원지", "종교용지", "사적지", "묘지", "잡종지",
    )
    JIMOK_FULL_NAME_BY_CODE = dict(zip(JIMOK_ORDER, JIMOK_FULL_NAMES))
    JIMOK_CODE_BY_FULL_NAME = dict(zip(JIMOK_FULL_NAMES, JIMOK_ORDER))
    JIMOK_NAME_FIELD = "지목"
    JIBUN_FIELD_CANDIDATES = ("jibun", "지번")
    JIMOK_FIELD_CANDIDATES = ("jimok", "지목", "jimok_nm", "지목명")
    PNU_FIELD_CANDIDATES = ("pnu", "고유번호", "필지고유번호")
    OWNER_FIELD_CANDIDATES = (
        "소유_소유대분류",
        "소유_소유구분",
        "소유대분류",
        "소유자",
        "소유자구분",
        "소유자구분명",
        "소유구분",
        "소유구분명",
        "소유",
        "posesn_se_code_nm",
        "posesnSeCodeNm",
    )
    OWNER_COLORS = {
        "사유지": "#FF8000",
        "국유지": "#7DFFFF",
        "공유지": "#00FF00",
        "미분류": "#A5A5A5",
        "조회없음": "#E6E6E6",
    }

    def __init__(self, iface, dock_widget, plugin_dir):
        super().__init__(dock_widget)
        self.iface = iface
        self.dock_widget = dock_widget
        self.plugin_dir = plugin_dir
        self._bind_ui()
        self._connect_signals()
        self._on_layer_changed(self.layer_combo.currentLayer())

    def _bind_ui(self):
        dock = self.dock_widget
        self.tab = dock.tab_spatial_tools
        self.load_cadastral_button = dock.btn_jibun_load_cadastral
        self.layer_combo = dock.combo_jibun_layer
        self.detect_layer_button = dock.btn_jibun_detect_layer
        self.jibun_tool_tabs = dock.tabs_jibun_tools

        self.field_combo = dock.combo_jibun_field
        self.dxf_path = dock.input_jibun_dxf_path
        self.dxf_browse = dock.btn_jibun_dxf_browse
        self.save_points = dock.cb_jibun_save_points
        self.point_path = dock.input_jibun_point_path
        self.point_browse = dock.btn_jibun_point_browse
        self.point_path_row = dock.widget_jibun_point_row
        self.advanced_toggle = dock.btn_jibun_advanced
        self.advanced_widget = dock.widget_jibun_advanced
        self.width_pad = dock.spin_jibun_width_pad
        self.floor_height = dock.spin_jibun_floor_height
        self.pole_tolerance_min = dock.spin_jibun_pole_tolerance_min
        self.pole_tolerance_ratio = dock.spin_jibun_pole_tolerance_ratio
        self.binary_steps = dock.spin_jibun_binary_steps
        self.dxf_height_factor = dock.spin_jibun_dxf_height_factor
        self.fallback_height = dock.spin_jibun_fallback_height
        self.run_button = dock.btn_jibun_export
        self.source_label_button = dock.btn_jibun_label_source

        self.jimok_field_combo = dock.combo_jimok_field
        self.jimok_source_label = dock.label_jimok_source
        self.jimok_style_button = dock.btn_jimok_categorize

        self.owner_field_combo = dock.combo_owner_field
        self.pnu_field_combo = dock.combo_owner_pnu_field
        self.owner_source_label = dock.label_owner_source
        self.owner_style_button = dock.btn_owner_categorize

        self.progress = dock.progress_jibun_export
        self.status = dock.label_jibun_status

        self.layer_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.layer_combo.setShowCrs(True)
        self.field_combo.setFilters(QgsFieldProxyModel.String)
        for combo in (
            self.jimok_field_combo,
            self.owner_field_combo,
            self.pnu_field_combo,
        ):
            combo.setAllowEmptyFieldName(True)

        folder_icon = QgsApplication.getThemeIcon("mActionFileOpen.svg")
        for browse_button in (self.dxf_browse, self.point_browse):
            browse_button.setIcon(folder_icon)

        self.field_detect_buttons = {
            "jibun": dock.btn_detect_jibun_field,
            "jimok": dock.btn_detect_jimok_field,
            "pnu": dock.btn_detect_pnu_field,
            "owner": dock.btn_detect_owner_field,
        }
        refresh_icon = QgsApplication.getThemeIcon("mActionRefresh.svg")
        self.detect_layer_button.setIcon(refresh_icon)
        for detect_button in self.field_detect_buttons.values():
            detect_button.setIcon(refresh_icon)

        self.advanced_widget.setVisible(False)

        self.elevation_controller = setup_elevation_analysis(self.iface, dock)

    def _connect_signals(self):
        self.load_cadastral_button.clicked.connect(self.load_vworld_cadastral)
        self.detect_layer_button.clicked.connect(self.detect_cadastral_layer)
        for role, detect_button in self.field_detect_buttons.items():
            detect_button.clicked.connect(
                lambda _checked=False, role=role: self.detect_single_field(role)
            )
        self.layer_combo.layerChanged.connect(self._on_layer_changed)
        self.dxf_browse.clicked.connect(self._choose_dxf_path)
        self.point_browse.clicked.connect(self._choose_point_path)
        self.save_points.toggled.connect(self.point_path_row.setEnabled)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        self.run_button.clicked.connect(self.run_export)
        self.source_label_button.clicked.connect(self.apply_labels_to_source)
        self.jimok_style_button.clicked.connect(self.apply_jimok_categorization)
        self.owner_style_button.clicked.connect(self.apply_owner_categorization)
        for combo in (
            self.field_combo,
            self.jimok_field_combo,
            self.owner_field_combo,
            self.pnu_field_combo,
        ):
            combo.fieldChanged.connect(self._refresh_classification_source_labels)

    CADASTRAL_2D_NAME = "연속지적도"
    CADASTRAL_GROUP_NAME = "토지이용"

    def load_vworld_cadastral(self):
        self.load_cadastral_button.setEnabled(False)
        self.status.setStyleSheet("color: rgb(85, 93, 109);")
        self.status.setText("VWorld 연속지적도를 불러오는 중...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        QtWidgets.QApplication.processEvents()
        try:
            layer = show_map_Vworld_2Dapi(
                self.iface,
                self.CADASTRAL_2D_NAME,
                self.dock_widget,
                add_to_API=False,
            )
        except Exception as error:
            self._show_error(f"연속지적도를 불러오지 못했습니다: {error}")
            return None
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.load_cadastral_button.setEnabled(True)

        if layer is None:
            self.status.setText("연속지적도를 불러오지 않았습니다.")
            return None

        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup(self.CADASTRAL_GROUP_NAME)
        if group is None:
            group = root.insertGroup(0, self.CADASTRAL_GROUP_NAME)
        group.addLayer(layer)

        self.layer_combo.setLayer(layer)
        self.status.setStyleSheet("color: rgb(22, 125, 72);")
        self.status.setText(
            f"연속지적도 {layer.featureCount():,}필지를 불러와 지적도 레이어로 선택했습니다."
        )
        return layer

    FIELD_SAMPLE_SIZE = 100
    JIBUN_VALUE_PATTERN = re.compile(r"^(산\s*)?\d+(-\d+)?\s*[가-힣]$")
    HANGUL_PATTERN = re.compile(r"[가-힣]")

    def _detect_fields(self, layer):
        detected = {
            "jibun": self._find_field_name(layer, self.JIBUN_FIELD_CANDIDATES),
            "jimok": self._find_field_name(layer, self.JIMOK_FIELD_CANDIDATES),
            "pnu": self._find_field_name(layer, self.PNU_FIELD_CANDIDATES),
            "owner": self._find_field_name(layer, self.OWNER_FIELD_CANDIDATES),
        }
        if all(detected.values()):
            return detected

        used = {name for name in detected.values() if name}
        samples = self._sample_field_values(layer, used)
        for role in ("pnu", "jibun", "jimok", "owner"):
            if detected[role]:
                continue
            field_name = self._best_field_by_values(role, samples, used)
            if field_name:
                detected[role] = field_name
                used.add(field_name)
        return detected

    def _sample_field_values(self, layer, exclude_names):
        fields = [
            field for field in layer.fields() if field.name() not in exclude_names
        ]
        samples = {field.name(): [] for field in fields}
        if not fields:
            return {}
        request = QgsFeatureRequest()
        request.setLimit(self.FIELD_SAMPLE_SIZE)
        for feature in layer.getFeatures(request):
            for field in fields:
                raw_value = feature[field.name()]
                if raw_value is None:
                    continue
                text = str(raw_value).strip()
                if text and text != "NULL":
                    samples[field.name()].append(text)
        return {
            field.name(): (field.isNumeric(), samples[field.name()])
            for field in fields
            if samples[field.name()]
        }

    def _best_field_by_values(self, role, samples, used):
        thresholds = {"pnu": 0.8, "jibun": 0.7, "jimok": 0.8, "owner": 0.6}
        best_name, best_ratio = None, 0.0
        for field_name, (is_numeric, values) in samples.items():
            if field_name in used:
                continue
            if role != "pnu" and is_numeric:
                continue
            matched = sum(1 for value in values if self._value_fits_role(role, value))
            ratio = matched / len(values)
            if ratio >= thresholds[role] and ratio > best_ratio:
                best_name, best_ratio = field_name, ratio
        return best_name

    def _value_fits_role(self, role, value):
        if role == "pnu":
            return bool(normalize_pnu(value))
        if role == "jibun":
            return bool(self.JIBUN_VALUE_PATTERN.match(value))
        if role == "jimok":
            return value in self.JIMOK_FULL_NAME_BY_CODE or value in self.JIMOK_CODE_BY_FULL_NAME
        if role == "owner":
            return bool(self.HANGUL_PATTERN.search(value)) and classify_owner_value(value) != "미분류"
        return False

    CADASTRAL_LAYER_KEYWORDS = ("지적도", "지적", "연속지적도", "cont_ldreg")
    FIELD_ROLE_LABELS = {"jibun": "지번", "jimok": "지목", "pnu": "PNU", "owner": "소유자"}

    def _cadastral_layers(self):
        layers = []
        for tree_layer in QgsProject.instance().layerTreeRoot().findLayers():
            layer = tree_layer.layer()
            if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
                continue
            if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
                continue
            name = layer.name().casefold()
            if any(keyword in name for keyword in self.CADASTRAL_LAYER_KEYWORDS):
                layers.append(layer)
        return layers

    def detect_cadastral_layer(self):
        layers = self._cadastral_layers()
        if not layers:
            self._warn(
                "이름에 지적도·지적·연속지적도·CONT_LDREG가 들어간 폴리곤 레이어가 없습니다. "
                "위 버튼으로 VWorld 연속지적도를 불러오세요."
            )
            return None

        current = self.layer_combo.currentLayer()
        if current in layers:
            chosen = layers[(layers.index(current) + 1) % len(layers)]
        else:
            chosen = layers[0]
        if chosen is current:
            self._on_layer_changed(chosen)
        else:
            self.layer_combo.setLayer(chosen)

        position = layers.index(chosen) + 1
        self.status.setStyleSheet("color: rgb(22, 125, 72);")
        self.status.setText(
            f"지적도 레이어 자동감지 {position}/{len(layers)}: '{chosen.name()}'"
        )
        return chosen

    def _field_role_combos(self):
        return {
            "jibun": self.field_combo,
            "jimok": self.jimok_field_combo,
            "pnu": self.pnu_field_combo,
            "owner": self.owner_field_combo,
        }

    def _field_role_candidates(self, role):
        return {
            "jibun": self.JIBUN_FIELD_CANDIDATES,
            "jimok": self.JIMOK_FIELD_CANDIDATES,
            "pnu": self.PNU_FIELD_CANDIDATES,
            "owner": self.OWNER_FIELD_CANDIDATES,
        }[role]

    def detect_single_field(self, role):
        label = self.FIELD_ROLE_LABELS[role]
        layer = self.layer_combo.currentLayer()
        if layer is None:
            self._warn("먼저 지적도 레이어를 선택하세요.")
            return None

        combos = self._field_role_combos()
        used = {
            combo.currentField()
            for other_role, combo in combos.items()
            if other_role != role and combo.currentField()
        }
        field_name = self._find_field_name(layer, self._field_role_candidates(role))
        if field_name in used:
            field_name = None
        if field_name is None:
            samples = self._sample_field_values(layer, used)
            field_name = self._best_field_by_values(role, samples, used)

        combo = combos[role]
        if field_name:
            combo.setField(field_name)
            self.status.setStyleSheet("color: rgb(22, 125, 72);")
            self.status.setText(f"{label} 필드 자동감지: {field_name}")
        else:
            if role != "jibun":
                combo.setField("")
            self.status.setStyleSheet("color: rgb(85, 93, 109);")
            self.status.setText(f"{label} 필드를 못 찾았습니다. 직접 선택하세요.")
        return field_name

    def _on_layer_changed(self, layer):
        self.field_combo.setLayer(layer)
        self.jimok_field_combo.setLayer(layer)
        self.owner_field_combo.setLayer(layer)
        self.pnu_field_combo.setLayer(layer)
        if layer is None:
            self._update_classification_source_labels(layer)
            return
        detected = self._detect_fields(layer)
        if detected["jibun"]:
            self.field_combo.setField(detected["jibun"])
        self.jimok_field_combo.setField(detected["jimok"] or "")
        self.owner_field_combo.setField(detected["owner"] or "")
        self.pnu_field_combo.setField(detected["pnu"] or "")
        self._update_classification_source_labels(layer)
        self._suggest_output_paths(layer)

    def _refresh_classification_source_labels(self, *_args):
        self._update_classification_source_labels(self.layer_combo.currentLayer())

    def _update_classification_source_labels(self, layer):
        if layer is None:
            self.jimok_source_label.setText("사용할 레이어를 선택하세요.")
            self.owner_source_label.setText("사용할 레이어를 선택하세요.")
            return

        jimok_field = self.jimok_field_combo.currentField()
        jibun_field = self.field_combo.currentField()
        if jimok_field:
            self.jimok_source_label.setText(f"사용 필드: {jimok_field}")
        elif jibun_field:
            self.jimok_source_label.setText(
                f"지목 필드 없음 · 사용 기준: {jibun_field}의 오른쪽 한 글자"
            )
        else:
            self.jimok_source_label.setText("지목 필드 또는 지번 필드를 선택하세요.")

        owner_field = self.owner_field_combo.currentField()
        pnu_field = self.pnu_field_combo.currentField()
        if owner_field:
            self.owner_source_label.setText(
                f"사용 필드: {owner_field} · API 호출 안 함"
            )
        elif pnu_field:
            self.owner_source_label.setText(
                f"소유자 필드 없음 · {pnu_field}로 VWorld API 조회"
            )
        else:
            self.owner_source_label.setText("소유자 필드 또는 PNU 필드를 선택하세요.")

    @staticmethod
    def _find_field_name(layer, preferred_names):
        fields_by_lower_name = {
            field.name().casefold(): field.name() for field in layer.fields()
        }
        for preferred_name in preferred_names:
            matched_name = fields_by_lower_name.get(preferred_name.casefold())
            if matched_name:
                return matched_name
        return None

    def _suggest_output_paths(self, layer):
        source_path = layer.source().split("|")[0]
        if os.path.isfile(source_path):
            folder = os.path.dirname(source_path)
        else:
            folder = QgsProject.instance().homePath()
            if not folder:
                folder = os.path.join(os.path.expanduser("~"), "Desktop")

        base_name = self._safe_filename(layer.name())
        self.dxf_path.setText(os.path.join(folder, f"{base_name}_지번.dxf"))
        self.point_path.setText(os.path.join(folder, f"{base_name}_지번.shp"))

    @staticmethod
    def _safe_filename(name):
        invalid_characters = '<>:"/\\|?*'
        safe_name = "".join(
            "_" if character in invalid_characters else character
            for character in name.strip()
        )
        return safe_name.rstrip(". ") or "지적도"

    def _choose_dxf_path(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.dock_widget,
            "DXF 저장 위치",
            self.dxf_path.text().strip(),
            "DXF 파일 (*.dxf)",
        )
        if path:
            self.dxf_path.setText(self._with_extension(path, ".dxf"))

    def _choose_point_path(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.dock_widget,
            "포인트 SHP 저장 위치",
            self.point_path.text().strip(),
            "ESRI Shapefile (*.shp)",
        )
        if path:
            self.point_path.setText(self._with_extension(path, ".shp"))

    def _toggle_advanced(self, checked):
        self.advanced_toggle.setArrowType(
            QtCore.Qt.ArrowType.DownArrow
            if checked
            else QtCore.Qt.ArrowType.RightArrow
        )
        self.advanced_widget.setVisible(checked)

    @staticmethod
    def _with_extension(path, extension):
        return path if path.lower().endswith(extension) else path + extension

    def _confirm_overwrite(self, paths):
        existing = [path for path in paths if path and os.path.exists(path)]
        if not existing:
            return True
        answer = QtWidgets.QMessageBox.question(
            self.dock_widget,
            "기존 파일 확인",
            "다음 파일이 이미 있습니다. 덮어쓸까요?\n\n" + "\n".join(existing),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        return answer == QtWidgets.QMessageBox.StandardButton.Yes

    def run_export(self):
        layer = self.layer_combo.currentLayer()
        field_name = self.field_combo.currentField()
        raw_dxf_path = self.dxf_path.text().strip()
        raw_point_path = self.point_path.text().strip()

        if layer is None:
            self._warn("지적도 폴리곤 레이어를 선택하세요.")
            return
        if not field_name:
            self._warn("지번이 들어 있는 문자 필드를 선택하세요.")
            return
        if not raw_dxf_path:
            self._warn("DXF 저장 경로를 선택하세요.")
            return
        if self.save_points.isChecked() and not raw_point_path:
            self._warn("포인트 SHP 저장 경로를 선택하세요.")
            return

        dxf_path = self._with_extension(raw_dxf_path, ".dxf")
        point_path = (
            self._with_extension(raw_point_path, ".shp")
            if self.save_points.isChecked()
            else ""
        )
        if not self._confirm_overwrite([dxf_path, point_path]):
            return

        self.dxf_path.setText(dxf_path)
        if point_path:
            self.point_path.setText(point_path)
        self.run_button.setEnabled(False)
        self.progress.setValue(0)
        self.status.setStyleSheet("color: rgb(85, 93, 109);")
        self.status.setText("필지 계산을 시작합니다...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)

        feedback = DockProcessingFeedback(self.progress, self.status)
        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        parameters = {
            JibunLabelDxfAlgorithm.INPUT: layer,
            JibunLabelDxfAlgorithm.FIELD: field_name,
            JibunLabelDxfAlgorithm.WIDTH_PAD: self.width_pad.value(),
            JibunLabelDxfAlgorithm.FLOOR_HEIGHT: self.floor_height.value(),
            JibunLabelDxfAlgorithm.POLE_TOLERANCE_MIN: self.pole_tolerance_min.value(),
            JibunLabelDxfAlgorithm.POLE_TOLERANCE_RATIO: self.pole_tolerance_ratio.value(),
            JibunLabelDxfAlgorithm.BINARY_STEPS: self.binary_steps.value(),
            JibunLabelDxfAlgorithm.DXF_HEIGHT_FACTOR: self.dxf_height_factor.value(),
            JibunLabelDxfAlgorithm.FALLBACK_HEIGHT: self.fallback_height.value(),
            JibunLabelDxfAlgorithm.OUTPUT_DXF: dxf_path,
            JibunLabelDxfAlgorithm.OUTPUT_POINTS: point_path or None,
        }

        try:
            algorithm = JibunLabelDxfAlgorithm()
            results, success = algorithm.run(
                parameters,
                context,
                feedback,
                {},
                False,
            )
            if not success or results is None:
                raise QgsProcessingException("처리 결과를 받지 못했습니다.")
            if point_path:
                self._write_utf8_cpg(point_path)
                self._load_point_layer(point_path)

            self.progress.setValue(100)
            self.status.setStyleSheet("color: rgb(22, 125, 72);")
            self.status.setText(
                f"완료: DXF{'와 포인트 SHP' if point_path else ''} 저장"
            )
            point_message = f"\n포인트 SHP: {point_path}" if point_path else ""
            QtWidgets.QMessageBox.information(
                self.dock_widget,
                "완료",
                f"지번 내보내기가 완료되었습니다.\n\nDXF: {dxf_path}{point_message}",
            )
        except QgsProcessingException as error:
            self._show_error(str(error))
        except Exception as error:
            self._show_error(f"예상하지 못한 오류: {error}")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.run_button.setEnabled(True)

    def apply_jimok_categorization(self):
        layer = self.layer_combo.currentLayer()
        if layer is None:
            self._warn("지목별로 분류할 지적도 폴리곤 레이어를 선택하세요.")
            return None

        source_field = self.jimok_field_combo.currentField() or None
        derived_from_jibun = source_field is None
        if derived_from_jibun:
            source_field = self.field_combo.currentField() or None
        if source_field is None:
            self._warn(
                "지목 필드를 선택하거나, 내보내기 탭에서 지번 필드를 선택하세요."
            )
            return None

        written_from_jibun = False
        unknown_count = 0
        if derived_from_jibun:
            write_result = self._write_jimok_name_field(layer, source_field)
            if write_result is not None:
                jibun_field = source_field
                source_field, unknown_count = write_result
                derived_from_jibun = False
                written_from_jibun = True
                self.jimok_field_combo.setField(source_field)

        unique_values = set()
        for feature in layer.getFeatures():
            raw_value = feature[source_field]
            normalized_value = "" if raw_value is None else str(raw_value).strip()
            if derived_from_jibun:
                normalized_value = normalized_value[-1:] if normalized_value else ""
            unique_values.add(normalized_value)

        non_empty_values = {value for value in unique_values if value}
        if not non_empty_values:
            self._warn(f"'{source_field}' 필드에서 분류할 지목 값을 찾지 못했습니다.")
            return None

        order_index = {
            value: index for index, value in enumerate(self.JIMOK_ORDER)
        }

        def jimok_code(value):
            if value in order_index:
                return value
            return self.JIMOK_CODE_BY_FULL_NAME.get(value)

        def category_sort_key(value):
            code = jimok_code(value)
            if code is not None:
                return (0, order_index[code], value)
            if value:
                return (1, 0, value)
            return (2, 0, value)

        categories = []
        for value in sorted(unique_values, key=category_sort_key):
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            if symbol is None:
                self._warn("선택 레이어의 도형 유형에 맞는 기본 심볼을 만들지 못했습니다.")
                return None

            code = jimok_code(value)
            color_text = self.JIMOK_COLOR_BY_VALUE.get(code) if code else None
            if color_text:
                color = QtGui.QColor(color_text)
            elif value:
                hue = sum(
                    (index + 1) * ord(character)
                    for index, character in enumerate(value)
                ) % 360
                color = QtGui.QColor.fromHsv(hue, 135, 230)
            else:
                color = QtGui.QColor("#E6E6E6")
            symbol.setColor(color)
            symbol.setOpacity(1.0)
            legend_label = self.JIMOK_FULL_NAME_BY_CODE.get(value, value)
            categories.append(
                QgsRendererCategory(value, symbol, legend_label or "빈칸/미확인")
            )

        quoted_field = QgsExpression.quotedColumnRef(source_field)
        trimmed_expression = f"coalesce(trim({quoted_field}), '')"
        class_expression = (
            f"right({trimmed_expression}, 1)"
            if derived_from_jibun
            else trimmed_expression
        )
        renderer = QgsCategorizedSymbolRenderer(class_expression, categories)
        layer.setRenderer(renderer)
        layer.setCustomProperty("k_auto/jimok_source_field", source_field)
        if written_from_jibun:
            source_mode = "jibun_full_name_field"
        elif derived_from_jibun:
            source_mode = "jibun_right_1"
        else:
            source_mode = "jimok_field"
        layer.setCustomProperty("k_auto/jimok_source_mode", source_mode)
        layer.triggerRepaint()

        if written_from_jibun:
            source_description = (
                f"{jibun_field} 끝 글자 → '{source_field}' 필드 생성"
            )
            if unknown_count:
                source_description += f" (지목 부호 아님 {unknown_count:,}건은 빈칸)"
        elif derived_from_jibun:
            source_description = f"{source_field} 양쪽 공백 제거 후 오른쪽 한 글자"
        else:
            source_description = f"{source_field} 양쪽 공백 제거"

        if self.iface is not None:
            self.iface.layerTreeView().refreshLayerSymbology(layer.id())
            self.iface.mapCanvas().refresh()
            self.iface.messageBar().pushSuccess(
                "K_Auto",
                f"'{layer.name()}'을 지목별로 분류했습니다. ({source_description})",
            )

        self.status.setStyleSheet("color: rgb(22, 125, 72);")
        self.status.setText(
            f"지목 분류 완료: {source_description} · {len(non_empty_values)}종"
        )
        print(
            f"[지목 분류] '{layer.name()}' · {source_description} · "
            f"{len(non_empty_values)}종"
        )
        return renderer

    def _write_jimok_name_field(self, layer, jibun_field):
        field_name = self.JIMOK_NAME_FIELD
        was_editing = layer.isEditable()
        if not was_editing and not layer.startEditing():
            self.status.setStyleSheet("color: rgb(85, 93, 109);")
            self.status.setText(
                "이 레이어는 편집할 수 없어 지목 필드 없이 지번 끝 글자로만 분류합니다."
            )
            return None

        field_index = layer.fields().indexFromName(field_name)
        if field_index < 0:
            if not layer.addAttribute(
                QgsField(field_name, QtCore.QMetaType.Type.QString, len=20)
            ):
                if not was_editing:
                    layer.rollBack()
                self.status.setStyleSheet("color: rgb(85, 93, 109);")
                self.status.setText(
                    "지목 필드를 추가할 수 없어 지번 끝 글자로만 분류합니다."
                )
                return None
            field_index = layer.fields().indexFromName(field_name)

        jibun_index = layer.fields().indexFromName(jibun_field)
        request = QgsFeatureRequest()
        request.setSubsetOfAttributes([jibun_index])
        unknown_count = 0
        for feature in layer.getFeatures(request):
            raw_value = feature[jibun_index]
            text = "" if raw_value is None else str(raw_value).strip()
            full_name = self.JIMOK_FULL_NAME_BY_CODE.get(text[-1:])
            if full_name is None:
                unknown_count += 1
            layer.changeAttributeValue(feature.id(), field_index, full_name)

        if not was_editing and not layer.commitChanges():
            errors = " / ".join(layer.commitErrors())
            layer.rollBack()
            self.status.setStyleSheet("color: rgb(85, 93, 109);")
            self.status.setText(
                f"지목 필드를 저장하지 못해 지번 끝 글자로만 분류합니다. {errors}"
            )
            return None
        return field_name, unknown_count

    def apply_owner_categorization(self):
        layer = self.layer_combo.currentLayer()
        if layer is None:
            self._warn("소유자 구분을 조회할 지적도 폴리곤 레이어를 선택하세요.")
            return None

        owner_field = self.owner_field_combo.currentField()
        if owner_field:
            renderer = self._apply_existing_owner_field_categorization(
                layer,
                owner_field,
            )
            if renderer is not None:
                return renderer
            self.status.setStyleSheet("color: rgb(85, 93, 109);")
            self.status.setText(
                f"'{owner_field}' 값에서 소유 유형을 찾지 못해 VWorld API를 조회합니다."
            )
            QtWidgets.QApplication.processEvents()

        pnu_field = self.pnu_field_combo.currentField() or None
        if pnu_field is None:
            self._warn("소유자 필드가 없으면 PNU 필드를 선택해야 VWorld API를 조회할 수 있습니다.")
            return None

        api_key_widget = getattr(self.dock_widget, "input_API", None)
        api_key = api_key_widget.text().strip() if api_key_widget is not None else ""
        if not api_key:
            self._warn("Vworld API 호출 탭에 API 인증키를 입력해 주세요.")
            return None

        target_pnus = set()
        invalid_count = 0
        for feature in layer.getFeatures():
            pnu = normalize_pnu(feature[pnu_field])
            if pnu:
                target_pnus.add(pnu)
            else:
                invalid_count += 1
        if not target_pnus:
            self._warn(f"'{pnu_field}' 필드에서 유효한 19자리 PNU를 찾지 못했습니다.")
            return None

        pnu_queries = build_pnu_queries(target_pnus)
        self.owner_style_button.setEnabled(False)
        self.progress.setValue(0)
        self.status.setStyleSheet("color: rgb(85, 93, 109);")
        self.status.setText(
            f"VWorld 소유정보 조회 준비 중... PNU {len(target_pnus):,}개"
        )
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)

        def update_progress(query_index, query_total, page_number, page_total, record_count):
            completed_ratio = (
                (query_index - 1) + page_number / max(page_total, 1)
            ) / max(query_total, 1)
            self.progress.setValue(min(90, max(1, int(completed_ratio * 90))))
            self.status.setText(
                f"소유정보 조회 중... {query_index}/{query_total}묶음 · "
                f"{page_number}/{page_total}페이지 · 응답 {record_count:,}건"
            )
            QtWidgets.QApplication.processEvents()

        try:
            records = fetch_possession_records(
                api_key,
                pnu_queries,
                progress_callback=update_progress,
            )
            aggregated = aggregate_possession_records(records, target_pnus)
            join_layer = self._create_owner_join_layer(
                layer,
                pnu_field,
                target_pnus,
                aggregated,
            )
            matched_count = len(aggregated)
            self.owner_field_combo.setField("소유_소유대분류")
            self.progress.setValue(100)
            self.status.setStyleSheet("color: rgb(22, 125, 72);")
            self.status.setText(
                f"소유자 분류 완료: {matched_count:,}/{len(target_pnus):,}필지 조회"
            )
            if invalid_count:
                self.status.setText(
                    self.status.text() + f" · 잘못된 PNU {invalid_count:,}건 제외"
                )
            if self.iface is not None:
                self.iface.mapCanvas().refresh()
                self.iface.messageBar().pushSuccess(
                    "K_Auto",
                    f"'{layer.name()}' 소유자 구분 {matched_count:,}필지를 적용했습니다.",
                )
            print(
                f"[소유자 분류] '{layer.name()}' · PNU {len(target_pnus):,}개 · "
                f"조회 성공 {matched_count:,}개 · API 응답 {len(records):,}건"
            )
            return join_layer
        except Exception as error:
            self._show_error(str(error))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.owner_style_button.setEnabled(True)
        return None

    def _apply_existing_owner_field_categorization(self, layer, owner_field):
        values_to_categories = {}
        for feature in layer.getFeatures():
            raw_value = feature[owner_field]
            value = "" if raw_value is None else str(raw_value).strip()
            values_to_categories[value] = classify_owner_value(value)

        recognized_categories = {
            category
            for category in values_to_categories.values()
            if category != "미분류"
        }
        if not recognized_categories:
            return None

        category_values = set(values_to_categories.values())
        categories = []
        category_order = {
            "사유지": 0,
            "국유지": 1,
            "공유지": 2,
            "미분류": 3,
        }
        for category_value in sorted(
            category_values,
            key=lambda value: (category_order.get(value, 9), value),
        ):
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            if symbol is None:
                raise QgsProcessingException("소유자 구분 심볼을 만들지 못했습니다.")
            symbol.setColor(QtGui.QColor(self.OWNER_COLORS[category_value]))
            symbol.setOpacity(1.0)
            categories.append(
                QgsRendererCategory(category_value, symbol, category_value)
            )

        quoted_field = QgsExpression.quotedColumnRef(owner_field)
        when_parts = []
        for source_value, category_value in sorted(values_to_categories.items()):
            when_parts.append(
                "WHEN trim(to_string({field})) = {source} THEN {category}".format(
                    field=quoted_field,
                    source=QgsExpression.quotedValue(source_value),
                    category=QgsExpression.quotedValue(category_value),
                )
            )
        class_expression = (
            "CASE " + " ".join(when_parts) + " ELSE '미분류' END"
        )
        renderer = QgsCategorizedSymbolRenderer(class_expression, categories)
        layer.setRenderer(renderer)
        layer.setCustomProperty("k_auto/owner_source_field", owner_field)
        layer.setCustomProperty("k_auto/owner_source_mode", "existing_field")
        layer.triggerRepaint()

        if self.iface is not None:
            self.iface.layerTreeView().refreshLayerSymbology(layer.id())
            self.iface.mapCanvas().refresh()
            self.iface.messageBar().pushSuccess(
                "K_Auto",
                f"'{layer.name()}'을 {owner_field} 필드 기준으로 분류했습니다.",
            )

        self.progress.setValue(100)
        self.status.setStyleSheet("color: rgb(22, 125, 72);")
        self.status.setText(
            f"소유자 분류 완료: {owner_field} 필드 사용 · API 호출 안 함"
        )
        print(
            f"[소유자 분류] '{layer.name()}' · {owner_field} 필드 · API 호출 없음"
        )
        return renderer

    def _create_owner_join_layer(
        self,
        source_layer,
        pnu_field,
        target_pnus,
        aggregated,
    ):
        project = QgsProject.instance()
        previous_join_id = str(
            source_layer.customProperty("k_auto/owner_join_layer_id", "") or ""
        )
        if previous_join_id:
            source_layer.removeJoin(previous_join_id)
            if project.mapLayer(previous_join_id) is not None:
                project.removeMapLayer(previous_join_id)

        join_layer = QgsVectorLayer(
            "None",
            f"{source_layer.name()}_소유자구분 조회",
            "memory",
        )
        if not join_layer.isValid():
            raise QgsProcessingException("소유자 구분 메모리 테이블을 만들지 못했습니다.")
        join_layer.setCustomProperty("skipMemoryLayersCheck", 1)
        join_layer.setCustomProperty("k_auto/owner_join_for", source_layer.id())
        provider = join_layer.dataProvider()
        provider.addAttributes(
            [
                QgsField("PNU", QtCore.QMetaType.Type.QString),
                QgsField("소유구분코드", QtCore.QMetaType.Type.QString),
                QgsField("소유구분", QtCore.QMetaType.Type.QString),
                QgsField("소유대분류", QtCore.QMetaType.Type.QString),
                QgsField("기준연월", QtCore.QMetaType.Type.QString),
                QgsField("자료기준일", QtCore.QMetaType.Type.QString),
                QgsField("조회건수", QtCore.QMetaType.Type.Int),
            ]
        )
        join_layer.updateFields()

        owner_values = set()
        join_features = []
        for pnu in sorted(target_pnus):
            row = aggregated.get(pnu)
            if row is None:
                row = {
                    "PNU": pnu,
                    "소유구분코드": "",
                    "소유구분": "조회없음",
                    "소유대분류": "조회없음",
                    "기준연월": "",
                    "자료기준일": "",
                    "조회건수": 0,
                }
            owner_value = row.get("소유대분류") or "조회없음"
            owner_values.add(owner_value)
            feature = QgsFeature(join_layer.fields())
            feature.setAttributes(
                [
                    row["PNU"],
                    row["소유구분코드"],
                    row["소유구분"],
                    owner_value,
                    row["기준연월"],
                    row["자료기준일"],
                    row["조회건수"],
                ]
            )
            join_features.append(feature)
        if not provider.addFeatures(join_features):
            raise QgsProcessingException("소유자 구분 조회 결과를 메모리 테이블에 쓰지 못했습니다.")

        project.addMapLayer(join_layer, False)
        join_info = QgsVectorLayerJoinInfo()
        join_info.setJoinLayer(join_layer)
        join_info.setJoinFieldName("PNU")
        join_info.setTargetFieldName(pnu_field)
        join_info.setPrefix("소유_")
        join_info.setUsingMemoryCache(True)
        if not source_layer.addJoin(join_info):
            project.removeMapLayer(join_layer.id())
            raise QgsProcessingException("소유자 구분 결과를 원본 레이어에 조인하지 못했습니다.")
        source_layer.updateFields()

        categories = []
        for owner_value in sorted(owner_values, key=lambda value: (value == "조회없음", value)):
            symbol = QgsSymbol.defaultSymbol(source_layer.geometryType())
            if symbol is None:
                raise QgsProcessingException("소유자 구분 심볼을 만들지 못했습니다.")
            if owner_value in self.OWNER_COLORS:
                color = QtGui.QColor(self.OWNER_COLORS[owner_value])
            else:
                hue = sum(
                    (index + 1) * ord(character)
                    for index, character in enumerate(owner_value)
                ) % 360
                color = QtGui.QColor.fromHsv(hue, 145, 225)
            symbol.setColor(color)
            symbol.setOpacity(1.0)
            categories.append(
                QgsRendererCategory(owner_value, symbol, owner_value)
            )

        owner_field_name = "소유_소유대분류"
        class_expression = (
            f"coalesce({QgsExpression.quotedColumnRef(owner_field_name)}, '조회없음')"
        )
        source_layer.setRenderer(
            QgsCategorizedSymbolRenderer(class_expression, categories)
        )
        source_layer.setCustomProperty("k_auto/owner_join_layer_id", join_layer.id())
        source_layer.setCustomProperty("k_auto/owner_pnu_field", pnu_field)
        source_layer.triggerRepaint()
        if self.iface is not None:
            self.iface.layerTreeView().refreshLayerSymbology(source_layer.id())
        return join_layer

    def apply_labels_to_source(self):
        layer = self.layer_combo.currentLayer()
        field_name = self.field_combo.currentField()
        if layer is None:
            self._warn("지적도 폴리곤 레이어를 선택하세요.")
            return
        if not field_name:
            self._warn("지번이 들어 있는 문자 필드를 선택하세요.")
            return
        if layer.crs().isGeographic():
            self._warn(
                "라벨 크기 계산에는 미터 등 지도 단위를 쓰는 투영좌표계가 필요합니다."
            )
            return

        temporary_dxf = tempfile.NamedTemporaryFile(
            prefix="k_auto_jibun_", suffix=".dxf", delete=False
        )
        temporary_dxf_path = temporary_dxf.name
        temporary_dxf.close()

        self.source_label_button.setEnabled(False)
        self.progress.setValue(0)
        self.status.setStyleSheet("color: rgb(85, 93, 109);")
        self.status.setText("원본 알고리즘으로 라벨 위치를 계산합니다...")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)

        feedback = DockProcessingFeedback(self.progress, self.status)
        context = QgsProcessingContext()
        context.setProject(QgsProject.instance())
        algorithm = JibunLabelDxfAlgorithm()
        parameters = {
            algorithm.INPUT: layer,
            algorithm.FIELD: field_name,
            algorithm.WIDTH_PAD: self.width_pad.value(),
            algorithm.FLOOR_HEIGHT: self.floor_height.value(),
            algorithm.POLE_TOLERANCE_MIN: self.pole_tolerance_min.value(),
            algorithm.POLE_TOLERANCE_RATIO: self.pole_tolerance_ratio.value(),
            algorithm.BINARY_STEPS: self.binary_steps.value(),
            algorithm.DXF_HEIGHT_FACTOR: self.dxf_height_factor.value(),
            algorithm.FALLBACK_HEIGHT: self.fallback_height.value(),
            algorithm.OUTPUT_DXF: temporary_dxf_path,
            algorithm.OUTPUT_POINTS: QgsProcessing.TEMPORARY_OUTPUT,
        }

        try:
            results, success = algorithm.run(
                parameters,
                context,
                feedback,
                {},
                False,
            )
            if not success or results is None:
                raise QgsProcessingException("라벨 위치 계산 결과를 받지 못했습니다.")

            destination_id = results.get(algorithm.OUTPUT_POINTS)
            label_layer = context.takeResultLayer(destination_id)
            if label_layer is None or not label_layer.isValid():
                raise QgsProcessingException("임시 지번 라벨 레이어를 만들지 못했습니다.")

            self._apply_point_label_overlay(layer, label_layer)
            self.progress.setValue(100)
            self.status.setStyleSheet("color: rgb(22, 125, 72);")
            self.status.setText("원본 지적도 위에 지번 포인트 라벨을 표시했습니다.")
            if self.iface is not None:
                self.iface.mapCanvas().refresh()
                self.iface.messageBar().pushSuccess(
                    "K_Auto",
                    f"'{layer.name()}' 위에 지번 포인트 라벨을 표시했습니다.",
                )
            print(
                f"[지번 라벨] '{layer.name()}' 위에 포인트 라벨 레이어 적용"
            )
            return label_layer
        except QgsProcessingException as error:
            self._show_error(str(error))
        except Exception as error:
            self._show_error(f"예상하지 못한 오류: {error}")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.source_label_button.setEnabled(True)
            if os.path.exists(temporary_dxf_path):
                os.remove(temporary_dxf_path)
        return None

    def _apply_point_label_overlay(self, source_layer, label_layer):
        project = QgsProject.instance()
        source_layer_id = source_layer.id()
        for existing_layer in list(project.mapLayers().values()):
            if existing_layer.customProperty("k_auto/jibun_source_layer_id") == source_layer_id:
                project.removeMapLayer(existing_layer.id())

        source_layer.setLabelsEnabled(False)
        source_layer.triggerRepaint()

        label_layer.setName(f"{source_layer.name()}_지번 라벨")
        label_layer.setCustomProperty("k_auto/jibun_source_layer_id", source_layer_id)
        label_layer.setCustomProperty("skipMemoryLayersCheck", 1)
        style_path = os.path.join(self.plugin_dir, "jibun_label_style.qml")
        if not os.path.exists(style_path):
            raise QgsProcessingException("지번 포인트 라벨 스타일 파일을 찾지 못했습니다.")
        style_message, style_ok = label_layer.loadNamedStyle(style_path)
        if not style_ok:
            raise QgsProcessingException(
                f"지번 포인트 라벨 스타일을 적용하지 못했습니다: {style_message}"
            )
        label_layer.setLabelsEnabled(True)
        project.addMapLayer(label_layer, True)
        label_layer.triggerRepaint()

    def _load_point_layer(self, point_path):
        layer_name = os.path.splitext(os.path.basename(point_path))[0]
        point_layer = QgsVectorLayer(point_path, layer_name, "ogr")
        if not point_layer.isValid():
            raise QgsProcessingException(
                "포인트 SHP는 저장했지만 QGIS에서 다시 불러오지 못했습니다."
            )

        point_layer.setProviderEncoding("UTF-8")

        style_path = os.path.join(self.plugin_dir, "jibun_label_style.qml")
        if os.path.exists(style_path):
            style_message, style_ok = point_layer.loadNamedStyle(style_path)
            if style_ok:
                point_layer.triggerRepaint()
            else:
                print(f"[지번 내보내기] 스타일 적용 실패: {style_message}")
        else:
            print("[지번 내보내기] 스타일 파일이 없어 기본 스타일로 불러왔습니다.")
        QgsProject.instance().addMapLayer(point_layer)

    @staticmethod
    def _write_utf8_cpg(point_path):
        cpg_path = os.path.splitext(point_path)[0] + ".cpg"
        with open(cpg_path, "w", encoding="ascii", newline="") as cpg_file:
            cpg_file.write("UTF-8")

    def _warn(self, message):
        QtWidgets.QMessageBox.warning(self.dock_widget, "입력 확인", message)

    def _show_error(self, message):
        self.status.setStyleSheet("color: rgb(180, 45, 45);")
        self.status.setText(f"실패: {message}")
        print(f"[지번 내보내기 오류] {message}")
        QtWidgets.QMessageBox.critical(
            self.dock_widget,
            "지번 내보내기 실패",
            f"{message}\n\n입력 레이어의 좌표계와 저장 경로를 확인하세요.",
        )


def setup_spatial_tools_tab(iface, dock_widget, plugin_dir):
    return JibunExportTabController(iface, dock_widget, plugin_dir)
