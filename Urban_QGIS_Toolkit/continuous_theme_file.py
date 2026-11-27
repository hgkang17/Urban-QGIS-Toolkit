
import os
import re
import threading

from qgis.core import QgsProject, QgsSettings, QgsVectorLayer
from qgis.PyQt import QtCore, QtGui, QtWidgets

from .elevation_analysis_file import DISTRICTS, ElevationAnalysisController
from .mnum_symbol import apply_mnum_symbol_to_layer, has_mnum_field
from .utils import check_playwright_installed
from .vworld_login import vworld_download_matching_file


PROVINCES = (
    ("서울특별시", ("서울특별시", "서울"), ("서울",), ("서울",), "서울"),
    ("부산광역시", ("부산광역시", "부산"), ("부산",), ("부산",), "부산"),
    ("대구광역시", ("대구광역시", "대구"), ("대구",), ("대구",), "대구"),
    ("인천광역시", ("인천광역시", "인천"), ("인천",), ("인천",), "인천"),
    ("광주광역시", ("광주광역시", "광주"), ("전남광주통합특별시", "광주"), ("전남광주", "광주"), "광주"),
    ("대전광역시", ("대전광역시", "대전"), ("대전",), ("대전",), "대전"),
    ("울산광역시", ("울산광역시", "울산"), ("울산",), ("울산",), "울산"),
    ("세종특별자치시", ("세종특별자치시", "세종"), ("세종",), ("세종",), "세종"),
    ("경기도", ("경기도", "경기"), ("경기",), ("경기",), "경기"),
    ("강원특별자치도", ("강원특별자치도", "강원도", "강원"), ("강원특별자치도", "강원"), ("강원특별자치도", "강원"), "강원"),
    ("충청북도", ("충청북도", "충북"), ("충북",), ("충북",), "충북"),
    ("충청남도", ("충청남도", "충남"), ("충남",), ("충남",), "충남"),
    ("전북특별자치도", ("전북특별자치도", "전라북도", "전북"), ("전북특별자치도", "전북"), ("전북특별자치도", "전북"), "전북"),
    ("전라남도", ("전라남도", "전남"), ("전남광주통합특별시", "전남"), ("전남광주", "전남"), "전남"),
    ("경상북도", ("경상북도", "경북"), ("경북",), ("경북",), "경북"),
    ("경상남도", ("경상남도", "경남"), ("경남",), ("경남",), "경남"),
    ("제주특별자치도", ("제주특별자치도", "제주"), ("제주",), ("제주",), "제주"),
)

CATALOG = (
    ("01. 용도지역", (
        ("01. 도시지역", (("UQ111", 30300),)),
        ("02. 관리지역", (("UQ112", 30291),)),
        ("03. 농림지역", (("UQ113", 30297),)),
        ("04. 자연환경보호지역", (("UQ114", 30310),)),
    )),
    ("02. 용도지구", (
        ("01. 경관지구", (("UQ121", 30287),)),
        ("02. 고도지구", (("UQ123", 30288),)),
        ("03. 방화지구", (("UQ124", 30305),)),
        ("04. 방재지구", (("UQ125", 30304),)),
        ("05. 보호지구", (("UQ126", 30307),)),
        ("06. 취락지구", (("UQ128", 30311),)),
        ("07. 개발진흥지구", (("UQ129", 30286),)),
        ("08. 특정용도제한지구", (("UQ130", 30312),)),
        ("09. 복합용도지구", (("UQ132", 30453),)),
    )),
    ("03. 구역", (
        ("01. 국토계획", (("UQ141", 30293),)),
        ("02. 도시개발", (("UD901", 30333),)),
        ("03. 공공주택", (("UD620", 30272),)),
        ("04. 산업단지", (("UH101", 30358),)),
        ("05. 물류단지", (("UH511", 30344),)),
        ("06. 정비구역", (("UD602", 30335),)),
        ("07. 지역개발", (("UB950", 30423),)),
        ("08. 택지개발", (("UD301", 30435),)),
        ("09. 지역특구", ()),
        ("10. 수도권정비권역", (("UB101", 30420),)),
    )),
    ("04. 도시계획시설", (
        ("01. 교통시설", (("UQ161", 30292),)),
        ("02. 공간시설", (("UQ162", 30289),)),
        ("03. 유통공급시설", (("UQ163", 30309),)),
        ("04. 공공문화체육시설", (("UQ164", 30290),)),
        ("05. 방재시설", (("UQ165", 30303),)),
        ("06. 보건위생시설", (("UQ166", 30306),)),
        ("07. 환경기초시설", (("UQ167", 30313),)),
    )),
    ("05. 토지이용규제", (
        ("01. 생태자연도", ()),
        ("02. 국토환경성평가지도", ()),
        ("03. 농지", (("UE101", 30325),)),
        ("04. 산지", (("UF801", 30362), ("UF811", 30361))),
        ("05. 학교환경위생", (("UO101", 30442),)),
        ("06. 도로 용도구역", (("UI101", 30331),)),
        ("07. 하천구역", (("UJ201", 30441), ("UJ301", 30369))),
        ("08. 수변구역", (("UM730", 30443), ("UM731", 30314), ("UM732", 30320), ("UM733", 30387))),
        ("09. 문화재", (
            ("UO301", 30342), ("ZH002", 30265), ("ZI002", 30260), ("ZO002", 30266),
            ("ZN002", 30268), ("ZE002", 30279), ("ZC002", 30326), ("ZF002", 30329), ("ZB002", 30349),
        )),
        ("10. 산림", (("UF151", 30355), ("UF141", 30356))),
        ("11. 농어촌 농업", (("UE301", 30321), ("UE000", 30323))),
        ("12. 초지", (("UF401", 30430),)),
        ("13. 사방지", (("UF301", 30350),)),
        ("14. 온천", (("UJ401", 30388),)),
        ("15. 비행", (("UI701", 30444), ("UI702", 30275))),
        ("16. 자연재해", (("UP201", 30396), ("UP401", 30315))),
        ("17. 폐기물 환경", (("UM501", 30439),)),
    )),
)

CADASTRAL_CATEGORY = "06. 연속지적도"
CADASTRAL_DATASETS = {"5174": 30564, "5186": 30563}

ORDINANCE_PROVINCE = {
    "ZH002": "경기", "ZI002": "강원", "ZO002": "경남", "ZN002": "경북",
    "ZE002": "광주", "ZC002": "대구", "ZF002": "대전", "ZB002": "부산",
}

SETTINGS_ROOT_KEY = "khg_plugin/continuous_theme_root"


def theme_filename_regex(code, crs, tokens):
    token_pattern = "|".join(re.escape(token) for token in tokens)
    crs_part = "_5174" if crs == "5174" else ""
    return rf"LSMD_CONT_{re.escape(code)}{crs_part}_(?:{token_pattern})\.zip"


def cadastral_filename_regex(crs, tokens, district):
    token_pattern = "|".join(re.escape(token) for token in tokens)
    district_part = re.escape(re.sub(r"\s+", "_", district.strip()))
    crs_part = "_5174" if crs == "5174" else ""
    return rf"LSMD_CONT_LDREG{crs_part}_(?:{token_pattern})_{district_part}\.zip"


def labeled_filename(filename, base_date, label=""):
    stem, extension = os.path.splitext(filename)
    digits = re.findall(r"\d+", base_date or "")
    date_text = ".".join([digits[0][-2:]] + digits[1:]) if len(digits) >= 2 else ""
    if label:
        stem += f"({label})"
    if date_text:
        stem += f"({date_text})"
    return stem + extension


def local_version_regex(vworld_regex, label):
    assert vworld_regex.endswith(r"\.zip")
    base = vworld_regex[: -len(r"\.zip")]
    label_part = re.escape(f"({label})") if label else ""
    return base + label_part + r"\((\d{2}\.\d{2}(?:\.\d{2})?)\)(?:\.zip)?"


def date_key(date_text):
    return tuple(int(part) for part in re.findall(r"\d+", date_text or ""))


def short_date(base_date):
    digits = re.findall(r"\d+", base_date or "")
    return ".".join([digits[0][-2:]] + digits[1:]) if len(digits) >= 2 else ""


def local_versions(folder, version_regex):
    if not os.path.isdir(folder):
        return []
    pattern = re.compile(version_regex)
    found = {}
    for name in os.listdir(folder):
        match = pattern.fullmatch(name)
        if not match:
            continue
        date_text = match.group(1)
        stem = name[:-4] if name.lower().endswith(".zip") else name
        found.setdefault(date_text, os.path.join(folder, stem + ".zip"))
    return sorted(
        ((date_key(text), text, path) for text, path in found.items()),
        reverse=True,
    )


def choose_version(versions, as_of=None):
    if as_of is None:
        return versions[0] if versions else None
    limit = date_key(as_of)
    for version in versions:
        if version[0] <= limit:
            return version
    return None


def prepare_shapefiles(zip_path):
    folder = os.path.splitext(zip_path)[0]
    new_stem = os.path.basename(folder)
    if not os.path.isdir(folder):
        if not os.path.isfile(zip_path):
            return []
        ElevationAnalysisController._extract_zip_safely(zip_path, folder)

    shapefiles = []
    for current_root, _, filenames in os.walk(folder):
        for filename in filenames:
            if filename.lower().endswith(".shp"):
                shapefiles.append(os.path.join(current_root, filename))
    shapefiles.sort()

    renamed = []
    for shp_path in shapefiles:
        directory = os.path.dirname(shp_path)
        old_stem = os.path.splitext(os.path.basename(shp_path))[0]
        if old_stem == new_stem or old_stem.startswith(new_stem + "_"):
            renamed.append(shp_path)
            continue
        target_stem = new_stem if len(shapefiles) == 1 else f"{new_stem}_{old_stem}"
        for sidecar in os.listdir(directory):
            sidecar_stem, sidecar_ext = os.path.splitext(sidecar)
            if sidecar_stem.casefold() == old_stem.casefold():
                os.replace(
                    os.path.join(directory, sidecar),
                    os.path.join(directory, target_stem + sidecar_ext.lower()),
                )
        renamed.append(os.path.join(directory, target_stem + ".shp"))
    return renamed


def run_without_freezing(function, *args):
    outcome = {}

    def work():
        try:
            outcome["value"] = function(*args)
        except Exception as error:
            outcome["error"] = error

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    while thread.is_alive():
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 50)
        thread.join(0.03)
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def resolve_child_folder(parent, default_name, create=True):
    number_match = re.match(r"^(\d+\.)", default_name)
    if number_match and os.path.isdir(parent):
        prefix = number_match.group(1)
        for name in sorted(os.listdir(parent)):
            path = os.path.join(parent, name)
            if os.path.isdir(path) and name.startswith(prefix):
                return path
    path = os.path.join(parent, default_name)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def resolve_province_folder(root, folder_names, create=True):
    for name in folder_names:
        path = os.path.join(root, f"●{name} 연속주제도")
        if os.path.isdir(path):
            return path
    path = os.path.join(root, f"●{folder_names[0]} 연속주제도")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


class ContinuousThemeController(QtCore.QObject):

    ROLE_JOB = QtCore.Qt.ItemDataRole.UserRole
    COLOR_HINT = "#555d6d"
    COLOR_OK = "#167d48"
    COLOR_UPDATE = "#c0392b"

    def __init__(self, iface, dock_widget):
        super().__init__(dock_widget)
        self.iface = iface
        self.dock_widget = dock_widget
        self._jobs = []
        self._results = []
        self._total = 0
        self._mode = None
        self._bind_ui()

    def _bind_ui(self):
        dock = self.dock_widget
        self.province_combo = dock.combo_theme_province
        self.crs_combo = dock.combo_theme_crs
        self.root_edit = dock.input_theme_root
        self.root_browse = dock.btn_theme_root_browse
        self.district_combo = dock.combo_theme_district
        self.tree = dock.tree_theme_items
        self.check_all_button = dock.btn_theme_check_all
        self.uncheck_all_button = dock.btn_theme_uncheck_all
        self.expand_button = dock.btn_theme_expand_all
        self.collapse_button = dock.btn_theme_collapse_all
        self.load_date_combo = dock.combo_theme_load_date
        self.load_checkbox = dock.cb_theme_load_qgis
        self.check_button = dock.btn_theme_check_update
        self.download_button = dock.btn_theme_download
        self.load_button = dock.btn_theme_load
        self.progress = dock.progress_theme
        self.status = dock.label_theme_status

        self.province_combo.clear()
        for province in PROVINCES:
            self.province_combo.addItem(province[0], province)
        self.province_combo.setCurrentIndex(max(0, self.province_combo.findText("경기도")))
        self.crs_combo.clear()
        self.crs_combo.addItem("Bessel 중부원점 (EPSG:5174)", "5174")
        self.crs_combo.addItem("GRS80 중부원점 (EPSG:5186)", "5186")

        self.root_edit.setText(QgsSettings().value(SETTINGS_ROOT_KEY, "", type=str))
        try:
            from qgis.core import QgsApplication
            self.root_browse.setIcon(QgsApplication.getThemeIcon("mActionFileOpen.svg"))
        except Exception:
            pass

        self._fill_tree()
        self._populate_districts()

        self.province_combo.currentIndexChanged.connect(self._on_region_changed)
        self.crs_combo.currentIndexChanged.connect(self._refresh_local)
        self.district_combo.currentTextChanged.connect(self._refresh_local)
        self.root_edit.editingFinished.connect(self._refresh_local)
        self.root_browse.clicked.connect(self._choose_root)
        self.check_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.uncheck_all_button.clicked.connect(lambda: self._set_all_checked(False))
        self.expand_button.clicked.connect(self.tree.expandAll)
        self.collapse_button.clicked.connect(self.tree.collapseAll)
        self.check_button.clicked.connect(self.check_updates)
        self.download_button.clicked.connect(self.start_download)
        self.load_button.clicked.connect(self.load_selected)
        self.tree.itemChanged.connect(self._on_item_changed)
        self._on_item_changed()
        self._refresh_local()

    def _fill_tree(self):
        checked = QtCore.Qt.CheckState.Checked
        unchecked = QtCore.Qt.CheckState.Unchecked
        flag_check = QtCore.Qt.ItemFlag.ItemIsUserCheckable
        flag_tristate = QtCore.Qt.ItemFlag.ItemIsAutoTristate
        self.tree.blockSignals(True)
        self.tree.clear()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        for category, items in CATALOG:
            top = QtWidgets.QTreeWidgetItem([category, ""])
            top.setFlags(top.flags() | flag_check | flag_tristate)
            self.tree.addTopLevelItem(top)
            for item_folder, datasets in items:
                child = QtWidgets.QTreeWidgetItem([item_folder, ""])
                child.setFlags(child.flags() | flag_check)
                child.setCheckState(0, checked)
                child.setData(0, self.ROLE_JOB, ("theme", category, item_folder, datasets))
                if datasets:
                    child.setToolTip(0, ", ".join(f"LSMD_CONT_{code}" for code, _ in datasets))
                else:
                    child.setToolTip(0, "VWorld 연속주제도에 없는 자료라 빈 폴더만 만듭니다.")
                top.addChild(child)
        cadastral = QtWidgets.QTreeWidgetItem([CADASTRAL_CATEGORY + " (시군구 선택)", ""])
        cadastral.setFlags(cadastral.flags() | flag_check)
        cadastral.setCheckState(0, unchecked)
        cadastral.setData(0, self.ROLE_JOB, ("cadastral", CADASTRAL_CATEGORY, None, ()))
        cadastral.setToolTip(0, "시군구 단위 자료라 위 시군구 칸에서 고른 지역만 받습니다.")
        self.tree.addTopLevelItem(cadastral)
        self.tree.expandToDepth(0)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.blockSignals(False)

    def _on_region_changed(self, *_args):
        self._populate_districts()
        self._refresh_local()

    def _populate_districts(self, *_args):
        province = self.province_combo.currentData()
        self.district_combo.blockSignals(True)
        self.district_combo.clear()
        if province:
            self.district_combo.addItems(DISTRICTS.get(province[4], []))
        self.district_combo.blockSignals(False)

    def _set_all_checked(self, checked):
        state = QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked
        for index in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(index).setCheckState(0, state)

    def _job_items(self, checked_only=True):
        items = []
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, self.ROLE_JOB) and (
                not checked_only or item.checkState(0) == QtCore.Qt.CheckState.Checked
            ):
                items.append(item)
            iterator += 1
        return items

    def _on_item_changed(self, *_args):
        jobs = self._job_items()
        cadastral_on = any(item.data(0, self.ROLE_JOB)[0] == "cadastral" for item in jobs)
        self.district_combo.setEnabled(cadastral_on)
        if not self._jobs:
            self.status.setStyleSheet(f"color: {self.COLOR_HINT};")
            self.status.setText(f"선택한 항목 {len(jobs)}개")

    def _choose_root(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self.dock_widget, "연속주제도 저장 폴더", self.root_edit.text().strip()
        )
        if path:
            self.root_edit.setText(os.path.normpath(path))
            self._refresh_local()

    def jobs_for_item(self, item, create=False):
        province = self.province_combo.currentData()
        crs = self.crs_combo.currentData() or "5174"
        root = self.root_edit.text().strip()
        _display, folder_names, theme_tokens, cadastral_tokens, district_key = province
        folder_label = folder_names[0]
        province_root = resolve_province_folder(root, folder_names, create=create)
        kind, category, item_folder, datasets = item.data(0, self.ROLE_JOB)
        category_folder = resolve_child_folder(
            province_root, f"{category}({folder_label})", create=create
        )
        jobs = []
        if kind == "cadastral":
            district = self.district_combo.currentText().strip()
            if not district:
                return []
            regex = cadastral_filename_regex(crs, cadastral_tokens, district)
            jobs.append({
                "label": f"연속지적도 {district}",
                "name_label": "연속지적도",
                "dataset_id": CADASTRAL_DATASETS[crs],
                "regex": regex,
                "version_regex": local_version_regex(regex, "연속지적도"),
                "folder": category_folder,
                "province_root": province_root,
                "category_folder": category_folder,
                "item": item,
            })
            return jobs
        item_name = item_folder.split(". ", 1)[-1]
        folder = resolve_child_folder(category_folder, item_folder, create=create)
        for code, dataset_id in datasets:
            owner = ORDINANCE_PROVINCE.get(code)
            if owner is not None and owner != district_key:
                continue
            regex = theme_filename_regex(code, crs, theme_tokens)
            jobs.append({
                "label": f"{item_name} {code}",
                "name_label": item_name,
                "dataset_id": dataset_id,
                "regex": regex,
                "version_regex": local_version_regex(regex, item_name),
                "folder": folder,
                "province_root": province_root,
                "category_folder": category_folder,
                "item": item,
            })
        return jobs

    def build_jobs(self, create=False):
        jobs = []
        for item in self._job_items():
            jobs.extend(self.jobs_for_item(item, create=create))
        return jobs

    def _refresh_local(self, *_args):
        if not self.root_edit.text().strip():
            return
        all_dates = set()
        for item in self._job_items(checked_only=False):
            if not item.data(0, self.ROLE_JOB)[3] and item.data(0, self.ROLE_JOB)[0] == "theme":
                self._set_item_state(item, "VWorld 자료 없음", "#9aa0a6")
                continue
            newest = None
            for job in self.jobs_for_item(item, create=False):
                versions = local_versions(job["folder"], job["version_regex"])
                all_dates.update(version[1] for version in versions)
                if versions and (newest is None or versions[0][0] > date_key(newest)):
                    newest = versions[0][1]
            self._set_item_state(item, f"로컬 {newest}" if newest else "로컬 없음", self.COLOR_HINT)

        current = self.load_date_combo.currentData()
        self.load_date_combo.blockSignals(True)
        self.load_date_combo.clear()
        self.load_date_combo.addItem("최신", None)
        for date_text in sorted(all_dates, key=date_key, reverse=True):
            self.load_date_combo.addItem(f"{date_text} 기준", date_text)
        index = self.load_date_combo.findData(current)
        self.load_date_combo.setCurrentIndex(index if index >= 0 else 0)
        self.load_date_combo.blockSignals(False)

    def _set_item_state(self, item, text, color):
        item.setText(1, text)
        item.setForeground(1, QtGui.QBrush(QtGui.QColor(color)))

    def _ready_for_vworld(self):
        root = self.root_edit.text().strip()
        if not root:
            self._choose_root()
            root = self.root_edit.text().strip()
            if not root:
                return False
        if not os.path.isdir(root):
            QtWidgets.QMessageBox.warning(self.dock_widget, "저장 폴더 확인", f"폴더가 없습니다:\n{root}")
            return False
        if not check_playwright_installed(self.iface):
            return False
        if not getattr(self.dock_widget, "vworld_context", None):
            QtWidgets.QMessageBox.warning(
                self.dock_widget,
                "브이월드 로그인 필요",
                "설정 탭에서 브이월드 로그인을 먼저 해 주세요.",
            )
            return False
        QgsSettings().setValue(SETTINGS_ROOT_KEY, root)
        return True

    def _set_busy(self, busy):
        for button in (self.check_button, self.download_button, self.load_button):
            button.setEnabled(not busy)

    def check_updates(self):
        self._start_queue("check")

    def start_download(self):
        self._start_queue("download")

    def _start_queue(self, mode):
        if self._jobs:
            return
        if not self._ready_for_vworld():
            return
        jobs = self.build_jobs(create=(mode == "download"))
        if not jobs:
            self._warn_status("받을 항목을 체크해 주세요. (연속지적도는 시군구도 골라야 합니다)")
            return
        self._mode = mode
        self._jobs = jobs
        self._results = []
        self._total = len(jobs)
        self._set_busy(True)
        self.progress.setValue(0)
        self._next_job()

    def _next_job(self):
        if not self._jobs:
            self._finish()
            return
        job = self._jobs[0]
        done = self._total - len(self._jobs)
        verb = "확인" if self._mode == "check" else "받는"
        self.status.setStyleSheet(f"color: {self.COLOR_HINT};")
        self.status.setText(f"{done + 1}/{self._total} · {job['label']} {verb} 중...")
        vworld_download_matching_file(
            self.dock_widget,
            job["dataset_id"],
            job["regex"],
            job["folder"],
            save_name_builder=lambda filename, base_date, label=job["name_label"]: (
                labeled_filename(filename, base_date, label)
            ),
            result_callback=self._on_job_result,
            check_only=(self._mode == "check"),
        )

    def _on_job_result(self, result):
        if not self._jobs:
            return
        job = self._jobs.pop(0)
        result = dict(result)
        result["job"] = job
        result["label"] = job["label"]
        if self._mode == "download" and result.get("status") in ("downloaded", "skipped"):
            try:
                run_without_freezing(prepare_shapefiles, result["path"])
            except Exception as error:
                result["status"] = "failed"
                result["error"] = f"압축 해제 실패: {error}"
        self._results.append(result)
        done = self._total - len(self._jobs)
        self.progress.setValue(int(done * 100 / max(self._total, 1)))
        QtCore.QTimer.singleShot(0, self._next_job)

    def _finish(self):
        mode = self._mode
        self._mode = None
        self._set_busy(False)
        self.progress.setValue(100)
        self._refresh_local()
        if mode == "check":
            summary = self._show_check_results()
        else:
            summary = self._download_summary()
            if self.load_checkbox.isChecked():
                loaded = self._load_items(
                    {id(result["job"]["item"]): result["job"]["item"] for result in self._results}.values(),
                    as_of=None,
                )
                summary += f" · QGIS 불러옴 {loaded}"
        failed = any(result.get("status") == "failed" for result in self._results)
        self.status.setStyleSheet(f"color: {self.COLOR_UPDATE if failed else self.COLOR_OK};")
        self.status.setText(summary)
        labels = {
            "downloaded": "받음", "skipped": "이미 최신", "available": "VWorld",
            "not_found": "자료 없음", "failed": "실패",
        }
        lines = [summary, ""]
        for result in self._results:
            line = f"[{labels.get(result.get('status'), '?')}] {result['label']}"
            if result.get("filename"):
                line += f" · {result['filename']} ({result.get('base_date', '')})"
            if result.get("error"):
                line += f" · {result['error']}"
            lines.append(line)
        print("[연속주제도]\n" + "\n".join(lines))
        if self.iface is not None:
            self.iface.messageBar().pushInfo("K_Auto 연속주제도", summary)
        self._total = 0

    def _download_summary(self):
        counts = {}
        for result in self._results:
            counts[result.get("status")] = counts.get(result.get("status"), 0) + 1
        return (
            f"다운로드 완료: 받음 {counts.get('downloaded', 0)} · 이미 최신 {counts.get('skipped', 0)} · "
            f"자료 없음 {counts.get('not_found', 0)} · 실패 {counts.get('failed', 0)}"
        )

    def _show_check_results(self):
        by_item = {}
        for result in self._results:
            by_item.setdefault(id(result["job"]["item"]), []).append(result)
        update_count = 0
        for results in by_item.values():
            item = results[0]["job"]["item"]
            local_newest = None
            remote_newest = None
            needs_update = False
            for result in results:
                job = result["job"]
                versions = local_versions(job["folder"], job["version_regex"])
                local = versions[0][1] if versions else None
                remote = short_date(result.get("base_date")) if result.get("status") == "available" else None
                if local and (local_newest is None or date_key(local) > date_key(local_newest)):
                    local_newest = local
                if remote and (remote_newest is None or date_key(remote) > date_key(remote_newest)):
                    remote_newest = remote
                if remote and (local is None or date_key(remote) > date_key(local)):
                    needs_update = True
            if remote_newest is None:
                self._set_item_state(item, f"로컬 {local_newest or '없음'} · VWorld 자료 없음", self.COLOR_HINT)
            elif needs_update:
                update_count += 1
                self._set_item_state(
                    item, f"로컬 {local_newest or '없음'} → VWorld {remote_newest} 갱신", self.COLOR_UPDATE
                )
            else:
                self._set_item_state(item, f"최신 {remote_newest}", self.COLOR_OK)
        return f"갱신 확인 완료: 갱신 있음 {update_count}개 항목 (빨간 글씨) · 다운로드를 누르면 새 기준일만 받습니다"

    def load_selected(self):
        if not self.root_edit.text().strip():
            self._choose_root()
        as_of = self.load_date_combo.currentData()
        loaded = self._load_items(self._job_items(), as_of=as_of)
        label = "최신" if as_of is None else f"{as_of} 기준"
        if loaded is None:
            return
        self.status.setStyleSheet(f"color: {self.COLOR_OK};")
        self.status.setText(f"불러오기({label}) 완료: {loaded}개 레이어 · 다운로드 없이 폴더 자료 사용")

    def _load_items(self, items, as_of=None):
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        opened = {
            os.path.normcase(os.path.abspath(layer.source().split("|")[0]))
            for layer in project.mapLayers().values()
        }
        loaded = 0
        missing = []
        for item in items:
            for job in self.jobs_for_item(item, create=False):
                version = choose_version(local_versions(job["folder"], job["version_regex"]), as_of)
                if version is None:
                    missing.append(job["label"])
                    continue
                try:
                    shp_paths = run_without_freezing(prepare_shapefiles, version[2])
                except Exception as error:
                    print(f"[연속주제도] 압축 해제 실패: {version[2]} · {error}")
                    continue
                for shp_path in shp_paths:
                    key = os.path.normcase(os.path.abspath(shp_path))
                    if key in opened:
                        continue
                    layer = QgsVectorLayer(
                        shp_path, os.path.splitext(os.path.basename(shp_path))[0], "ogr"
                    )
                    if not layer.isValid():
                        print(f"[연속주제도] 불러오기 실패: {shp_path}")
                        continue
                    top_name = os.path.basename(job["province_root"])
                    top_group = root.findGroup(top_name) or root.insertGroup(0, top_name)
                    category_name = os.path.basename(job["category_folder"])
                    category_group = (
                        top_group.findGroup(category_name) or top_group.addGroup(category_name)
                    )
                    project.addMapLayer(layer, False)
                    category_group.addLayer(layer)
                    opened.add(key)
                    loaded += 1
                    self._apply_style(layer)
        if missing:
            print("[연속주제도] 폴더에 해당 기준일 자료 없음: " + ", ".join(missing))
        return loaded

    def _apply_style(self, layer):
        if not has_mnum_field(layer):
            return False
        counter = [0]

        def keep_screen_alive():
            counter[0] += 1
            if counter[0] % 300 == 0:
                QtWidgets.QApplication.processEvents()

        self.status.setText(f"'{layer.name()}' 심볼 분류 중...")
        QtWidgets.QApplication.processEvents()
        try:
            return apply_mnum_symbol_to_layer(
                layer,
                iface=self.iface,
                dock_widget=self.dock_widget,
                rename_layer=False,
                on_feature=keep_screen_alive,
                message=lambda _text: None,
            )
        except Exception as error:
            print(f"[연속주제도] 심볼 분류 실패: {layer.name()} · {error}")
            return False

    def _warn_status(self, text):
        self.status.setStyleSheet(f"color: {self.COLOR_UPDATE};")
        self.status.setText(text)


def setup_continuous_theme_tab(iface, dock_widget):
    return ContinuousThemeController(iface, dock_widget)
