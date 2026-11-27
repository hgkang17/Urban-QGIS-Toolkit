
import json
import math
import os
import re
import urllib.parse
import urllib.request
import zipfile

from osgeo import gdal, ogr, osr
from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.analysis import QgsGridFileWriter, QgsInterpolator, QgsTinInterpolator
from qgis.core import (
    Qgis,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsFeatureRequest,
    QgsFieldProxyModel,
    QgsFillSymbol,
    QgsGeometry,
    QgsLineSymbol,
    QgsMapLayerProxyModel,
    QgsPalLayerSettings,
    QgsProject,
    QgsRasterBandStats,
    QgsRasterLayer,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsStyle,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

from .utils import check_playwright_installed
from .vworld_login import _get_download_directory, vworld_download_named_file

gdal.UseExceptions()


PROVINCES = (
    ("서울특별시", "서울"),
    ("부산광역시", "부산"),
    ("대구광역시", "대구"),
    ("인천광역시", "인천"),
    ("광주광역시", "광주"),
    ("대전광역시", "대전"),
    ("울산광역시", "울산"),
    ("세종특별자치시", "세종"),
    ("경기도", "경기"),
    ("강원특별자치도", "강원"),
    ("충청북도", "충북"),
    ("충청남도", "충남"),
    ("전북특별자치도", "전북"),
    ("전라남도", "전남"),
    ("경상북도", "경북"),
    ("경상남도", "경남"),
    ("제주특별자치도", "제주"),
)

PROVINCE_ALIASES = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "세종시": "세종",
    "경기도": "경기",
    "강원도": "강원",
    "강원특별자치도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전라북도": "전북",
    "전북특별자치도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주도": "제주",
    "제주특별자치도": "제주",
}

DISTRICTS = {
    "서울": "강남구,강동구,강북구,강서구,관악구,광진구,구로구,금천구,노원구,도봉구,동대문구,동작구,마포구,서대문구,서초구,성동구,성북구,송파구,양천구,영등포구,용산구,은평구,종로구,중구,중랑구".split(","),
    "부산": "강서구,금정구,기장군,남구,동구,동래구,부산진구,북구,사상구,사하구,서구,수영구,연제구,영도구,중구,해운대구".split(","),
    "대구": "남구,달서구,달성군,동구,북구,서구,수성구,중구,군위군".split(","),
    "인천": "강화군,계양구,남동구,동구,미추홀구,부평구,서구,연수구,옹진군,중구".split(","),
    "광주": "광산구,남구,동구,북구,서구".split(","),
    "대전": "대덕구,동구,서구,유성구,중구".split(","),
    "울산": "남구,동구,북구,울주군,중구".split(","),
    "세종": ["세종시"],
    "경기": "가평군,고양시 덕양구,고양시 일산동구,고양시 일산서구,과천시,광명시,광주시,구리시,군포시,김포시,남양주시,동두천시,부천시 소사구,부천시 오정구,부천시 원미구,성남시 분당구,성남시 수정구,성남시 중원구,수원시 권선구,수원시 영통구,수원시 장안구,수원시 팔달구,시흥시,안산시 단원구,안산시 상록구,안성시,안양시 동안구,안양시 만안구,양주시,양평군,여주시,연천군,오산시,용인시 기흥구,용인시 수지구,용인시 처인구,의왕시,의정부시,이천시,파주시,평택시,포천시,하남시,화성시".split(","),
    "강원": "강릉시,고성군,동해시,삼척시,속초시,양구군,양양군,영월군,원주시,인제군,정선군,철원군,춘천시,태백시,평창군,홍천군,화천군,횡성군".split(","),
    "충북": "괴산군,단양군,보은군,영동군,옥천군,음성군,제천시,증평군,진천군,청주시 상당구,청주시 서원구,청주시 청원구,청주시 흥덕구,충주시".split(","),
    "충남": "계룡시,공주시,금산군,논산시,당진시,보령시,부여군,서산시,서천군,아산시,예산군,천안시 동남구,천안시 서북구,청양군,태안군,홍성군".split(","),
    "전북": "고창군,군산시,김제시,남원시,무주군,부안군,순창군,완주군,익산시,임실군,장수군,전주시 덕진구,전주시 완산구,정읍시,진안군".split(","),
    "전남": "강진군,고흥군,곡성군,광양시,구례군,나주시,담양군,목포시,무안군,보성군,순천시,신안군,여수시,영광군,영암군,완도군,장성군,장흥군,진도군,함평군,해남군,화순군".split(","),
    "경북": "경산시,경주시,고령군,구미시,김천시,문경시,봉화군,상주시,성주군,안동시,영덕군,영양군,영주시,영천시,예천군,울릉군,울진군,의성군,청도군,청송군,칠곡군,포항시 남구,포항시 북구".split(","),
    "경남": "거제시,거창군,고성군,김해시,남해군,밀양시,사천시,산청군,양산시,의령군,진주시,창녕군,창원시 마산합포구,창원시 마산회원구,창원시 성산구,창원시 의창구,창원시 진해구,통영시,하동군,함안군,함양군,합천군".split(","),
    "제주": ["서귀포시", "제주시"],
}

ELEVATION_FIELD_NAMES = (
    "등고수치",
    "cont",
    "contour",
    "elev",
    "elevation",
    "height",
    "z_value",
    "zvalue",
    "altitude",
    "value",
    "표고",
    "수치",
)


class ElevationAnalysisController(QtCore.QObject):

    def __init__(self, iface, dock_widget):
        super().__init__(dock_widget)
        self.iface = iface
        self.dock_widget = dock_widget
        self._boundary_geometry_json = None
        self._boundary_location_key = None
        self._setting_center_location = False
        self._bind_group()

    def _bind_group(self):
        dock = self.dock_widget
        self.province_combo = dock.combo_elevation_province
        self.district_combo = dock.combo_elevation_district
        self.center_location_button = dock.btn_elevation_center_location
        self.current_crs_label = dock.label_elevation_current_crs
        self.output_crs_combo = dock.combo_elevation_output_crs
        self.clip_boundary_checkbox = dock.cb_elevation_clip_boundary
        self.pixel_size = dock.spin_elevation_pixel_size
        self.contour_interval = dock.spin_elevation_contour_interval
        self.progress = dock.progress_elevation_analysis
        self.status = dock.label_elevation_status
        self.run_button = dock.btn_elevation_analysis
        self.contour_layer_combo = dock.combo_elevation_contour_layer
        self.contour_field_combo = dock.combo_elevation_contour_field
        self.slope_checkbox = dock.cb_elevation_slope

        self.contour_layer_combo.setFilters(QgsMapLayerProxyModel.LineLayer)
        try:
            self.contour_layer_combo.setAllowEmptyLayer(True, "미선택 시 VWorld 자동 다운로드")
        except TypeError:
            self.contour_layer_combo.setAllowEmptyLayer(True)
        self.contour_layer_combo.setLayer(None)
        self.contour_field_combo.setFilters(QgsFieldProxyModel.Numeric)
        self.contour_layer_combo.layerChanged.connect(self._on_contour_layer_changed)
        self._on_contour_layer_changed(None)

        self.province_combo.clear()
        for display_name, file_token in PROVINCES:
            self.province_combo.addItem(display_name, file_token)
        self.output_crs_combo.clear()
        self.output_crs_combo.addItem(
            "GRS80 중부원점 (EPSG:5186)", "EPSG:5186"
        )
        self.output_crs_combo.addItem(
            "Bessel 수정 중부원점 (EPSG:5174)", "EPSG:5174"
        )
        self.district_combo.lineEdit().setPlaceholderText("예: 안동시 / 청주시 흥덕구")

        self.center_location_button.clicked.connect(self.select_canvas_center_location)
        self.province_combo.currentIndexChanged.connect(self._populate_districts)
        self.province_combo.currentIndexChanged.connect(self._clear_boundary_if_manual_change)
        self.district_combo.currentTextChanged.connect(self._clear_boundary_if_manual_change)
        self._populate_districts()

        project = QgsProject.instance()
        project.crsChanged.connect(self._update_current_crs_label)
        self._update_current_crs_label()

        self.run_button.clicked.connect(self.run)

        self.dock_widget.elevation_status = self.status
        self.dock_widget.elevation_run_button = self.run_button

    def _on_contour_layer_changed(self, layer):
        self.contour_field_combo.setLayer(layer)
        using_layer = layer is not None
        self.contour_field_combo.setEnabled(using_layer)
        self.province_combo.setEnabled(not using_layer)
        self.district_combo.setEnabled(not using_layer)
        if using_layer:
            field_name = self._elevation_field_name_from_qgis(layer)
            if field_name:
                self.contour_field_combo.setField(field_name)
            self.status.setText(
                f"'{layer.name()}' 등고선으로 분석합니다. (다운로드·로그인 불필요)"
            )
        else:
            self.status.setText(
                "등고선 레이어 미선택: 시도·시군구의 VWorld 수치지형도를 내려받습니다."
            )
        self.status.setStyleSheet("color: rgb(85, 93, 109);")

    @staticmethod
    def _elevation_field_name_from_qgis(layer):
        numeric_fields = [field.name() for field in layer.fields() if field.isNumeric()]
        normalized_fields = {
            re.sub(r"[^0-9a-z가-힣]", "", name.lower()): name for name in numeric_fields
        }
        for candidate in ELEVATION_FIELD_NAMES:
            key = re.sub(r"[^0-9a-z가-힣]", "", candidate.lower())
            if key in normalized_fields:
                return normalized_fields[key]
        if len(numeric_fields) == 1:
            return numeric_fields[0]
        return None

    def _update_current_crs_label(self, *_args):
        current_crs = QgsProject.instance().crs()
        if not current_crs.isValid():
            self.current_crs_label.setText("미설정")
            return
        authid = current_crs.authid() or "사용자 정의 CRS"
        description = current_crs.description().strip()
        text = authid
        if description and description.casefold() != authid.casefold():
            text = f"{authid} · {description}"
        self.current_crs_label.setText(text)

    def _populate_districts(self):
        province_token = self.province_combo.currentData()
        current_text = self.district_combo.currentText().strip()
        self.district_combo.blockSignals(True)
        self.district_combo.clear()
        self.district_combo.addItems(DISTRICTS.get(province_token, []))
        if current_text in DISTRICTS.get(province_token, []):
            self.district_combo.setCurrentText(current_text)
        self.district_combo.blockSignals(False)

    def _clear_boundary_if_manual_change(self, *_args):
        if self._setting_center_location:
            return
        self._boundary_geometry_json = None
        self._boundary_location_key = None

    @staticmethod
    def _request_vworld_json(url):
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:
            raise RuntimeError("VWorld 위치 API 요청에 실패했습니다.") from error

    def select_canvas_center_location(self):
        api_key = ""
        if hasattr(self.dock_widget, "input_API"):
            api_key = self.dock_widget.input_API.text().strip()
        if not api_key:
            QtWidgets.QMessageBox.warning(
                self.dock_widget,
                "VWorld API 키 필요",
                "VWorld API 호출 탭에서 API 키를 입력해 주세요.",
            )
            return

        try:
            self.center_location_button.setEnabled(False)
            self._set_status(0, "지도 화면 중심의 행정구역을 확인하는 중...")

            canvas = self.iface.mapCanvas()
            center = canvas.center()
            source_crs = canvas.mapSettings().destinationCrs()
            wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
            if source_crs != wgs84:
                transform = QgsCoordinateTransform(source_crs, wgs84, QgsProject.instance())
                center = transform.transform(center)
            lon = center.x()
            lat = center.y()

            address_params = {
                "service": "address",
                "request": "getaddress",
                "crs": "epsg:4326",
                "point": f"{lon},{lat}",
                "format": "json",
                "type": "parcel",
                "key": api_key,
            }
            address_url = (
                "https://api.vworld.kr/req/address?"
                + urllib.parse.urlencode(address_params)
            )
            address_data = self._request_vworld_json(address_url)
            response = address_data.get("response", {})
            if response.get("status") != "OK":
                error_text = response.get("error", {}).get(
                    "text", "화면 중심에서 주소를 찾지 못했습니다."
                )
                raise RuntimeError(error_text)

            address_results = response.get("result") or []
            if not address_results:
                raise RuntimeError("화면 중심에서 주소를 찾지 못했습니다.")
            address_result = address_results[0]
            structure = address_result.get("structure") or {}
            address_text = address_result.get("text", "")
            province_name = str(structure.get("level1") or "").strip()
            district_name = str(structure.get("level2") or "").strip()
            province_token = PROVINCE_ALIASES.get(province_name)
            if not province_token:
                raise RuntimeError(f"지원하지 않는 시도입니다: {province_name or address_text}")

            district_candidates = DISTRICTS.get(province_token, [])
            if province_token == "세종":
                district_name = "세종시"
            elif district_name not in district_candidates:
                matches = [
                    candidate
                    for candidate in district_candidates
                    if candidate in address_text
                    or all(part in address_text for part in candidate.split())
                ]
                district_name = max(matches, key=len) if matches else district_name
            if district_name not in district_candidates:
                raise RuntimeError(
                    f"VWorld 수치지형도 파일 단위와 일치하는 시군구를 찾지 못했습니다: "
                    f"{district_name or address_text}"
                )

            boundary_geometry = None
            for data_name in ("LT_C_ADSIGG_INFO", "LT_C_ADSIGG"):
                boundary_params = {
                    "service": "data",
                    "request": "GetFeature",
                    "format": "json",
                    "size": "10",
                    "data": data_name,
                    "geomFilter": f"POINT({lon} {lat})",
                    "crs": "EPSG:4326",
                    "key": api_key,
                    "domain": "localhost",
                }
                boundary_url = (
                    "https://api.vworld.kr/req/data?"
                    + urllib.parse.urlencode(boundary_params)
                )
                boundary_data = self._request_vworld_json(boundary_url)
                boundary_response = boundary_data.get("response", {})
                if boundary_response.get("status") != "OK":
                    continue
                features = (
                    boundary_response.get("result", {})
                    .get("featureCollection", {})
                    .get("features", [])
                )
                if features and features[0].get("geometry"):
                    boundary_geometry = features[0]["geometry"]
                    break
            if boundary_geometry is None:
                raise RuntimeError("화면 중심의 VWorld 시군구 행정경계를 찾지 못했습니다.")

            province_index = self.province_combo.findData(province_token)
            if province_index < 0:
                raise RuntimeError(f"시도 목록에서 찾지 못했습니다: {province_name}")
            self._setting_center_location = True
            try:
                self.province_combo.setCurrentIndex(province_index)
                self.district_combo.setCurrentText(district_name)
            finally:
                self._setting_center_location = False

            self._boundary_geometry_json = boundary_geometry
            self._boundary_location_key = (province_token, district_name)
            self.status.setText(
                f"자동선택 완료: {province_name} {district_name} · 행정경계 준비됨"
            )
            self.status.setStyleSheet("color: rgb(22, 125, 72);")
            self.iface.messageBar().pushSuccess(
                "K_Auto", f"화면 중심 위치: {province_name} {district_name}"
            )
        except Exception as error:
            self._boundary_geometry_json = None
            self._boundary_location_key = None
            self.status.setText(f"위치 자동선택 실패: {error}")
            self.status.setStyleSheet("color: rgb(180, 45, 45);")
            QtWidgets.QMessageBox.warning(
                self.dock_widget, "위치 자동선택 실패", str(error)
            )
        finally:
            self.center_location_button.setEnabled(True)

    def run(self):
        province_token = self.province_combo.currentData()
        district_text = self.district_combo.currentText().strip()
        contour_layer = self.contour_layer_combo.currentLayer()
        using_layer = contour_layer is not None
        if province_token == "세종" and not using_layer:
            district_text = "세종시"
            self.district_combo.setCurrentText(district_text)
        if not using_layer:
            if not district_text:
                QtWidgets.QMessageBox.warning(
                    self.dock_widget,
                    "시군구 확인",
                    "분석할 시군구를 입력해 주세요. 구가 있는 도시는 '청주시 흥덕구'처럼 입력합니다.",
                )
                return
            if not check_playwright_installed(self.iface):
                return

        target_crs_authid = self.output_crs_combo.currentData() or "EPSG:5186"
        make_slope = self.slope_checkbox.isChecked()
        boundary_geometry_json = None
        if self.clip_boundary_checkbox.isChecked():
            selected_key = (province_token, district_text)
            if (
                self._boundary_geometry_json is None
                or self._boundary_location_key != selected_key
            ):
                QtWidgets.QMessageBox.warning(
                    self.dock_widget,
                    "시군구 경계 필요",
                    "먼저 '화면 중심 자동선택' 버튼을 눌러 현재 시군구의 행정경계를 가져와 주세요.",
                )
                return
            boundary_geometry_json = self._boundary_geometry_json

        if using_layer:
            self._run_with_contour_layer(
                contour_layer,
                target_crs_authid,
                boundary_geometry_json,
                make_slope,
            )
            return

        filename = self._vworld_filename(province_token, district_text)
        analysis_name = os.path.splitext(filename)[0].replace("2MAP5000_SHP_", "")
        output_directory = os.path.join(
            _get_download_directory(),
            "K_Auto_표고분석",
            analysis_name,
        )
        os.makedirs(output_directory, exist_ok=True)

        self.run_button.setEnabled(False)
        self.progress.setValue(5)
        self.status.setText(f"백그라운드에서 {filename} 찾는 중...")
        self.status.setStyleSheet("color: rgb(85, 93, 109);")
        QtWidgets.QApplication.processEvents()

        started = vworld_download_named_file(
            self.dock_widget,
            filename,
            output_directory,
            lambda zip_path: self._process_download(
                zip_path,
                analysis_name,
                float(self.pixel_size.value()),
                float(self.contour_interval.value()),
                target_crs_authid,
                boundary_geometry_json,
                make_slope,
            ),
        )
        if not started:
            self.run_button.setEnabled(True)

    def _run_with_contour_layer(
        self,
        contour_layer,
        target_crs_authid,
        boundary_geometry_json,
        make_slope,
    ):
        field_name = self.contour_field_combo.currentField()
        if not field_name:
            QtWidgets.QMessageBox.warning(
                self.dock_widget,
                "등고 필드 확인",
                "등고선의 표고(높이) 숫자 필드를 '등고 필드'에서 선택해 주세요.",
            )
            return
        if not contour_layer.crs().isValid():
            QtWidgets.QMessageBox.warning(
                self.dock_widget,
                "좌표계 확인",
                "등고선 레이어의 좌표계가 정해져 있지 않습니다. 레이어 좌표계를 먼저 지정해 주세요.",
            )
            return

        analysis_name = re.sub(r'[\\/:*?"<>|\s]+', "_", contour_layer.name()).strip("_")
        analysis_name = analysis_name or "등고선"
        output_directory = os.path.join(
            _get_download_directory(),
            "K_Auto_표고분석",
            analysis_name,
        )
        os.makedirs(output_directory, exist_ok=True)
        self.run_button.setEnabled(False)
        try:
            self._remove_result_group(analysis_name)
            boundary_geometry = None
            boundary_path = None
            if boundary_geometry_json is not None:
                boundary_path = os.path.join(
                    output_directory, f"{analysis_name}_시군구경계.gpkg"
                )
                self._set_status(15, "시군구 행정경계를 결과 좌표계로 변환 중...")
                boundary_geometry = self._write_boundary_geometry(
                    boundary_geometry_json,
                    target_crs_authid,
                    boundary_path,
                )
            source_gpkg = os.path.join(output_directory, f"{analysis_name}_원본등고선.gpkg")
            self._set_status(
                30, f"'{contour_layer.name()}' 등고선을 {target_crs_authid}로 정리 중..."
            )
            self._export_layer_contours(
                contour_layer,
                field_name,
                source_gpkg,
                target_crs_authid,
                boundary_geometry,
            )
        except Exception as error:
            self._show_failure(error)
            self.run_button.setEnabled(True)
            return

        self._build_elevation_outputs(
            output_directory,
            analysis_name,
            source_gpkg,
            boundary_path,
            float(self.pixel_size.value()),
            float(self.contour_interval.value()),
            target_crs_authid,
            make_slope,
        )

    @staticmethod
    def _export_layer_contours(
        layer,
        field_name,
        output_path,
        target_crs_authid="EPSG:5186",
        boundary_geometry=None,
    ):
        if os.path.exists(output_path):
            ogr.GetDriverByName("GPKG").DeleteDataSource(output_path)
        output_srs = ElevationAnalysisController._spatial_reference(target_crs_authid)
        data_source = ogr.GetDriverByName("GPKG").CreateDataSource(output_path)
        if data_source is None:
            raise RuntimeError("등고선 GeoPackage를 만들지 못했습니다.")
        feature_count = 0
        try:
            output_layer = data_source.CreateLayer(
                "source_contours",
                srs=output_srs,
                geom_type=ogr.wkbUnknown,
            )
            output_layer.CreateField(ogr.FieldDefn("ELEV", ogr.OFTReal))
            target_crs = QgsCoordinateReferenceSystem(target_crs_authid)
            transform = None
            if layer.crs() != target_crs:
                transform = QgsCoordinateTransform(
                    layer.crs(), target_crs, QgsProject.instance()
                )
            request = QgsFeatureRequest()
            request.setSubsetOfAttributes([field_name], layer.fields())
            for feature in layer.getFeatures(request):
                try:
                    elevation = float(feature[field_name])
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(elevation):
                    continue
                geometry = QgsGeometry(feature.geometry())
                if geometry.isEmpty():
                    continue
                if transform is not None:
                    geometry.transform(transform)
                ogr_geometry = ogr.CreateGeometryFromWkb(bytes(geometry.asWkb()))
                if ogr_geometry is None:
                    continue
                if boundary_geometry is not None:
                    ogr_geometry = ogr_geometry.Intersection(boundary_geometry)
                    if ogr_geometry is None or ogr_geometry.IsEmpty():
                        continue
                output_feature = ogr.Feature(output_layer.GetLayerDefn())
                output_feature.SetGeometry(ogr_geometry)
                output_feature.SetField("ELEV", elevation)
                if output_layer.CreateFeature(output_feature) != ogr.OGRERR_NONE:
                    raise RuntimeError("등고선 피처를 GeoPackage에 쓰지 못했습니다.")
                feature_count += 1
        finally:
            data_source = None
        if feature_count == 0:
            raise RuntimeError(
                "분석할 등고선이 없습니다. 등고 필드 값과 (자르기 사용 시) 행정경계 범위를 확인하세요."
            )
        return feature_count

    @staticmethod
    def _vworld_filename(province_token, district_text):
        if province_token == "세종":
            return "2MAP5000_SHP_세종시.zip"
        normalized = re.sub(r"[\s_/\\]+", "_", district_text.strip())
        normalized = normalized.strip("_")
        return f"2MAP5000_SHP_{province_token}_{normalized}.zip"

    def _process_download(
        self,
        zip_path,
        analysis_name,
        requested_pixel_size,
        interval,
        target_crs_authid,
        boundary_geometry_json,
        make_slope=True,
    ):
        try:
            self._set_status(20, "ZIP 안전 검사 및 압축 해제 중...")
            output_directory = os.path.dirname(zip_path)
            extracted_directory = os.path.join(output_directory, "수치지형도_SHP")
            self._extract_zip_safely(zip_path, extracted_directory)

            self._set_status(35, "등고선(F0010000) 레이어 찾는 중...")
            contour_paths = self._find_contour_shapefiles(extracted_directory)
            if not contour_paths:
                raise RuntimeError("압축 파일에서 등고선 F0010000 SHP를 찾지 못했습니다.")

            self._remove_result_group(analysis_name)
            boundary_path = None
            boundary_geometry = None
            if boundary_geometry_json is not None:
                boundary_path = os.path.join(
                    output_directory, f"{analysis_name}_시군구경계.gpkg"
                )
                self._set_status(40, "시군구 행정경계를 결과 좌표계로 변환 중...")
                boundary_geometry = self._write_boundary_geometry(
                    boundary_geometry_json,
                    target_crs_authid,
                    boundary_path,
                )

            source_gpkg = os.path.join(output_directory, f"{analysis_name}_원본등고선.gpkg")
            self._set_status(45, f"등고선 {len(contour_paths)}개 도엽 병합 중...")
            self._merge_contours(
                contour_paths,
                source_gpkg,
                target_crs_authid,
                boundary_geometry,
            )

        except Exception as error:
            self._show_failure(error)
            self.run_button.setEnabled(True)
            return

        self._build_elevation_outputs(
            output_directory,
            analysis_name,
            source_gpkg,
            boundary_path,
            requested_pixel_size,
            interval,
            target_crs_authid,
            make_slope,
        )

    def _build_elevation_outputs(
        self,
        output_directory,
        analysis_name,
        source_gpkg,
        boundary_path,
        requested_pixel_size,
        interval,
        target_crs_authid,
        make_slope,
    ):
        try:
            contour_layer = QgsVectorLayer(source_gpkg, f"{analysis_name}_원본 등고선", "ogr")
            if not contour_layer.isValid():
                raise RuntimeError("병합된 원본 등고선 레이어를 열지 못했습니다.")
            boundary_layer = None
            if boundary_path is not None:
                boundary_layer = QgsVectorLayer(
                    boundary_path,
                    f"{analysis_name}_시군구 경계",
                    "ogr",
                )
                if not boundary_layer.isValid():
                    raise RuntimeError("시군구 행정경계 레이어를 열지 못했습니다.")

            extent = (
                boundary_layer.extent()
                if boundary_layer is not None
                else contour_layer.extent()
            )
            auto_pixel_size = math.sqrt(
                max(extent.width() * extent.height(), 1.0) / 40000000.0
            )
            pixel_size = max(requested_pixel_size, auto_pixel_size)
            columns = max(1, int(math.ceil(extent.width() / pixel_size)))
            rows = max(1, int(math.ceil(extent.height() / pixel_size)))

            tin_path = os.path.join(output_directory, f"{analysis_name}_TIN표고.tif")
            tin_interpolation_path = (
                os.path.join(output_directory, f"{analysis_name}_TIN표고_경계자르기전.tif")
                if boundary_path is not None
                else tin_path
            )
            self._set_status(
                55,
                f"TIN 보간 중... (픽셀 {pixel_size:.1f}m, {columns:,}×{rows:,})",
            )
            self._create_tin(
                contour_layer,
                tin_interpolation_path,
                extent,
                columns,
                rows,
            )
            if boundary_path is not None:
                self._set_status(70, "TIN 표고를 시군구 행정경계로 자르는 중...")
                self._clip_raster_to_boundary(
                    tin_interpolation_path,
                    boundary_path,
                    tin_path,
                )
                try:
                    os.remove(tin_interpolation_path)
                except OSError:
                    pass

            contour_50m_path = os.path.join(
                output_directory, f"{analysis_name}_{interval:g}m등고선.gpkg"
            )
            self._set_status(78, f"{interval:g}m 간격 등고선 생성 중...")
            self._create_contours(tin_path, contour_50m_path, interval)

            slope_layer = None
            if make_slope:
                slope_path = os.path.join(output_directory, f"{analysis_name}_경사도.tif")
                self._set_status(86, "TIN 표고로 경사도(°) 계산 중...")
                self._create_slope(tin_path, slope_path)
                slope_layer = QgsRasterLayer(slope_path, f"{analysis_name}_경사도(°)")
                if not slope_layer.isValid():
                    raise RuntimeError("생성된 경사도 래스터를 열지 못했습니다.")

            tin_layer = QgsRasterLayer(tin_path, f"{analysis_name}_TIN 표고")
            interval_layer = QgsVectorLayer(
                contour_50m_path,
                f"{analysis_name}_{interval:g}m 등고선",
                "ogr",
            )
            if not tin_layer.isValid() or not interval_layer.isValid():
                raise RuntimeError("생성된 TIN 또는 등고선 레이어를 열지 못했습니다.")

            self._style_tin(tin_layer, interval)
            self._style_contours(interval_layer)
            self._style_source_contours(contour_layer)
            if slope_layer is not None:
                self._style_slope(slope_layer)
            if boundary_layer is not None:
                self._style_boundary(boundary_layer)
            self._add_result_group(
                analysis_name,
                tin_layer,
                contour_layer,
                interval_layer,
                boundary_layer,
                slope_layer,
            )

            self.progress.setValue(100)
            boundary_text = " · 시군구 경계 적용" if boundary_layer is not None else ""
            slope_text = " · 경사도" if slope_layer is not None else ""
            self.status.setText(
                f"완료: {target_crs_authid} · TIN 표고와 {interval:g}m 등고선"
                f"{slope_text}{boundary_text}"
            )
            self.status.setStyleSheet("color: rgb(22, 125, 72);")
            if self.iface is not None:
                self.iface.mapCanvas().refresh()
                self.iface.messageBar().pushSuccess(
                    "K_Auto", f"{analysis_name} 표고·경사 분석을 완료했습니다."
                )
        except Exception as error:
            self._show_failure(error)
        finally:
            self.run_button.setEnabled(True)

    def _show_failure(self, error):
        print(f"[ERROR] 표고·경사 분석 실패: {error}")
        self.status.setText(f"실패: {error}")
        self.status.setStyleSheet("color: rgb(180, 45, 45);")
        QtWidgets.QMessageBox.critical(
            self.dock_widget,
            "표고·경사 분석 실패",
            str(error),
        )

    def _set_status(self, progress, text):
        self.progress.setValue(progress)
        self.status.setText(text)
        QtWidgets.QApplication.processEvents()

    @staticmethod
    def _extract_zip_safely(zip_path, output_directory):
        os.makedirs(output_directory, exist_ok=True)
        output_root = os.path.abspath(output_directory)
        pending_archives = [(os.path.abspath(zip_path), output_root)]
        extracted_archives = set()

        while pending_archives:
            archive_path, target_directory = pending_archives.pop(0)
            if archive_path in extracted_archives:
                continue
            extracted_archives.add(archive_path)
            if len(extracted_archives) > 5000:
                raise RuntimeError("중첩 ZIP 개수가 비정상적으로 많아 압축 해제를 중단했습니다.")

            try:
                archive = zipfile.ZipFile(archive_path, metadata_encoding="cp949")
            except TypeError:
                archive = zipfile.ZipFile(archive_path)
            with archive:
                for member in archive.infolist():
                    member_path = os.path.abspath(
                        os.path.join(
                            target_directory,
                            member.filename.replace("/", os.sep),
                        )
                    )
                    if os.path.commonpath([output_root, member_path]) != output_root:
                        raise RuntimeError(
                            f"안전하지 않은 ZIP 경로가 포함되어 있습니다: {member.filename}"
                        )
                archive.extractall(target_directory)

            for current_root, _, filenames in os.walk(target_directory):
                for filename in filenames:
                    if not filename.lower().endswith(".zip"):
                        continue
                    nested_path = os.path.abspath(os.path.join(current_root, filename))
                    if nested_path in extracted_archives:
                        continue
                    nested_directory = os.path.join(
                        current_root,
                        os.path.splitext(filename)[0],
                    )
                    os.makedirs(nested_directory, exist_ok=True)
                    pending_archives.append((nested_path, nested_directory))

    @staticmethod
    def _find_contour_shapefiles(root_directory):
        primary = []
        fallback = []
        for current_root, _, filenames in os.walk(root_directory):
            for filename in filenames:
                if not filename.lower().endswith(".shp"):
                    continue
                path = os.path.join(current_root, filename)
                normalized_name = re.sub(r"[^a-z0-9]", "", filename.lower())
                if "f0010000" in normalized_name:
                    primary.append(path)
                elif "contour" in normalized_name or "ctour" in normalized_name:
                    fallback.append(path)
        return sorted(primary or fallback)

    @staticmethod
    def _elevation_field_name(ogr_layer):
        definition = ogr_layer.GetLayerDefn()
        numeric_fields = []
        for index in range(definition.GetFieldCount()):
            field = definition.GetFieldDefn(index)
            if field.GetType() not in (ogr.OFTInteger, ogr.OFTInteger64, ogr.OFTReal):
                continue
            numeric_fields.append(field.GetName())
        normalized_fields = {
            re.sub(r"[^0-9a-z가-힣]", "", name.lower()): name
            for name in numeric_fields
        }
        for candidate in ELEVATION_FIELD_NAMES:
            key = re.sub(r"[^0-9a-z가-힣]", "", candidate.lower())
            if key in normalized_fields:
                return normalized_fields[key]
        if len(numeric_fields) == 1:
            return numeric_fields[0]
        raise RuntimeError(
            "등고수치 필드를 찾지 못했습니다. 확인된 숫자 필드: "
            + ", ".join(numeric_fields)
        )

    @staticmethod
    def _spatial_reference(authid):
        try:
            epsg = int(str(authid).split(":")[-1])
        except (TypeError, ValueError) as error:
            raise RuntimeError(f"지원하지 않는 좌표계입니다: {authid}") from error
        spatial_reference = osr.SpatialReference()
        if spatial_reference.ImportFromEPSG(epsg) != 0:
            raise RuntimeError(f"좌표계를 불러오지 못했습니다: {authid}")
        if hasattr(spatial_reference, "SetAxisMappingStrategy"):
            spatial_reference.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        return spatial_reference

    @staticmethod
    def _write_boundary_geometry(geometry_json, target_crs_authid, output_path):
        geometry = ogr.CreateGeometryFromJson(json.dumps(geometry_json))
        if geometry is None or geometry.IsEmpty():
            raise RuntimeError("VWorld 시군구 경계 도형을 읽지 못했습니다.")

        source_srs = ElevationAnalysisController._spatial_reference("EPSG:4326")
        target_srs = ElevationAnalysisController._spatial_reference(target_crs_authid)
        geometry.AssignSpatialReference(source_srs)
        if not source_srs.IsSame(target_srs):
            transform = osr.CoordinateTransformation(source_srs, target_srs)
            if geometry.Transform(transform) != ogr.OGRERR_NONE:
                raise RuntimeError("시군구 경계 좌표 변환에 실패했습니다.")
        geometry.AssignSpatialReference(target_srs)

        if os.path.exists(output_path):
            ogr.GetDriverByName("GPKG").DeleteDataSource(output_path)
        data_source = ogr.GetDriverByName("GPKG").CreateDataSource(output_path)
        if data_source is None:
            raise RuntimeError("시군구 경계 GeoPackage를 만들지 못했습니다.")
        layer = data_source.CreateLayer(
            "boundary",
            srs=target_srs,
            geom_type=geometry.GetGeometryType(),
        )
        layer.CreateField(ogr.FieldDefn("NAME", ogr.OFTString))
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("NAME", "시군구 경계")
        feature.SetGeometry(geometry)
        if layer.CreateFeature(feature) != ogr.OGRERR_NONE:
            data_source = None
            raise RuntimeError("시군구 경계 피처를 저장하지 못했습니다.")
        result_geometry = geometry.Clone()
        data_source = None
        return result_geometry

    @staticmethod
    def _merge_contours(
        contour_paths,
        output_path,
        target_crs_authid="EPSG:5186",
        boundary_geometry=None,
    ):
        if os.path.exists(output_path):
            ogr.GetDriverByName("GPKG").DeleteDataSource(output_path)

        output_data_source = ogr.GetDriverByName("GPKG").CreateDataSource(output_path)
        if output_data_source is None:
            raise RuntimeError("원본 등고선 GeoPackage를 만들지 못했습니다.")

        output_layer = None
        output_srs = ElevationAnalysisController._spatial_reference(
            target_crs_authid
        )
        output_field = None
        feature_count = 0
        try:
            for contour_path in contour_paths:
                source_data_source = ogr.Open(contour_path)
                if source_data_source is None:
                    continue
                source_layer = source_data_source.GetLayer(0)
                field_name = ElevationAnalysisController._elevation_field_name(
                    source_layer
                )
                source_srs = source_layer.GetSpatialRef()
                if source_srs is None:
                    raise RuntimeError(
                        "원본 등고선의 좌표계를 확인할 수 없습니다: "
                        f"{os.path.basename(contour_path)}. 같은 이름의 .prj 파일이 "
                        "있는지 확인하세요."
                    )
                if hasattr(source_srs, "SetAxisMappingStrategy"):
                    source_srs.SetAxisMappingStrategy(
                        osr.OAMS_TRADITIONAL_GIS_ORDER
                    )

                if output_layer is None:
                    output_layer = output_data_source.CreateLayer(
                        "source_contours",
                        srs=output_srs,
                        geom_type=ogr.wkbUnknown,
                    )
                    output_layer.CreateField(ogr.FieldDefn("ELEV", ogr.OFTReal))
                    output_field = output_layer.GetLayerDefn().GetFieldIndex("ELEV")

                coordinate_transform = None
                if source_srs and output_srs and not source_srs.IsSame(output_srs):
                    coordinate_transform = osr.CoordinateTransformation(
                        source_srs, output_srs
                    )

                source_layer.ResetReading()
                for source_feature in source_layer:
                    geometry = source_feature.GetGeometryRef()
                    elevation = source_feature.GetField(field_name)
                    if geometry is None or elevation is None:
                        continue
                    output_feature = ogr.Feature(output_layer.GetLayerDefn())
                    output_geometry = geometry.Clone()
                    if coordinate_transform is not None:
                        if output_geometry.Transform(coordinate_transform) != ogr.OGRERR_NONE:
                            raise RuntimeError(
                                "등고선 좌표를 "
                                f"{target_crs_authid}로 변환하지 못했습니다: "
                                f"{os.path.basename(contour_path)}"
                            )
                    if boundary_geometry is not None:
                        output_geometry = output_geometry.Intersection(
                            boundary_geometry
                        )
                        if output_geometry is None or output_geometry.IsEmpty():
                            continue
                    output_feature.SetGeometry(output_geometry)
                    output_feature.SetField(output_field, float(elevation))
                    if output_layer.CreateFeature(output_feature) != ogr.OGRERR_NONE:
                        raise RuntimeError("등고선 피처를 병합 파일에 쓰지 못했습니다.")
                    feature_count += 1
                source_data_source = None
        finally:
            output_data_source = None

        if feature_count == 0:
            raise RuntimeError("등고선 피처가 한 건도 병합되지 않았습니다.")

    @staticmethod
    def _create_tin(contour_layer, output_path, extent, columns, rows):
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as error:
                raise RuntimeError(
                    f"기존 TIN 파일을 교체하지 못했습니다: {output_path}"
                ) from error
        layer_data = QgsInterpolator.LayerData()
        layer_data.source = contour_layer
        layer_data.valueSource = QgsInterpolator.ValueAttribute
        layer_data.interpolationAttribute = contour_layer.fields().indexFromName("ELEV")
        layer_data.sourceType = QgsInterpolator.SourceStructureLines
        interpolator = QgsTinInterpolator(
            [layer_data],
            QgsTinInterpolator.Linear,
        )
        writer = QgsGridFileWriter(interpolator, output_path, extent, columns, rows)
        result = writer.writeFile()
        if result != 0 or not os.path.isfile(output_path):
            raise RuntimeError(f"TIN 보간 래스터 생성에 실패했습니다. 오류 코드: {result}")

    @staticmethod
    def _clip_raster_to_boundary(input_path, boundary_path, output_path):
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as error:
                raise RuntimeError(
                    f"기존 경계 적용 TIN 파일을 교체하지 못했습니다: {output_path}"
                ) from error
        result = gdal.Warp(
            output_path,
            input_path,
            format="GTiff",
            cutlineDSName=boundary_path,
            cutlineLayer="boundary",
            cropToCutline=True,
            dstNodata=-9999.0,
            creationOptions=["COMPRESS=LZW", "TILED=YES"],
        )
        if result is None:
            raise RuntimeError("TIN 래스터를 시군구 경계로 자르지 못했습니다.")
        result = None

    @staticmethod
    def _create_contours(raster_path, output_path, interval):
        if os.path.exists(output_path):
            ogr.GetDriverByName("GPKG").DeleteDataSource(output_path)
        raster = gdal.Open(raster_path)
        if raster is None:
            raise RuntimeError("TIN 래스터를 GDAL로 열지 못했습니다.")
        band = raster.GetRasterBand(1)
        output = ogr.GetDriverByName("GPKG").CreateDataSource(output_path)
        spatial_reference = osr.SpatialReference()
        if raster.GetProjection():
            spatial_reference.ImportFromWkt(raster.GetProjection())
        contour_layer = output.CreateLayer(
            "contours_50m",
            srs=spatial_reference,
            geom_type=ogr.wkbLineString,
        )
        contour_layer.CreateField(ogr.FieldDefn("ELEV", ogr.OFTReal))
        elevation_field_index = contour_layer.GetLayerDefn().GetFieldIndex("ELEV")
        nodata = band.GetNoDataValue()
        result = gdal.ContourGenerate(
            band,
            float(interval),
            0.0,
            [],
            1 if nodata is not None else 0,
            float(nodata or 0.0),
            contour_layer,
            -1,
            elevation_field_index,
        )
        output = None
        raster = None
        if result != 0:
            raise RuntimeError(f"{interval:g}m 등고선 생성에 실패했습니다.")

    @staticmethod
    def _create_slope(dem_path, output_path):
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError as error:
                raise RuntimeError(
                    f"기존 경사도 파일을 교체하지 못했습니다: {output_path}"
                ) from error
        result = gdal.DEMProcessing(
            output_path,
            dem_path,
            "slope",
            format="GTiff",
            computeEdges=True,
            slopeFormat="degree",
            scale=1.0,
            creationOptions=["COMPRESS=LZW", "TILED=YES"],
        )
        if result is None or not os.path.isfile(output_path):
            raise RuntimeError("경사도 래스터 생성에 실패했습니다.")
        result = None

    SLOPE_CLASSES = (
        (5.0, "#1A9641", "0–5°"),
        (10.0, "#A6D96A", "5–10°"),
        (15.0, "#FFFFBF", "10–15°"),
        (20.0, "#FDAE61", "15–20°"),
        (25.0, "#F46D43", "20–25°"),
        (30.0, "#D7191C", "25–30°"),
        (90.0, "#7B0C0C", "30° 이상"),
    )

    @staticmethod
    def _style_slope(layer):
        items = [
            QgsColorRampShader.ColorRampItem(upper, QtGui.QColor(color), label)
            for upper, color, label in ElevationAnalysisController.SLOPE_CLASSES
        ]
        color_shader = QgsColorRampShader()
        color_shader.setColorRampType(QgsColorRampShader.Discrete)
        color_shader.setColorRampItemList(items)
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(color_shader)
        layer.setRenderer(
            QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, raster_shader)
        )
        layer.triggerRepaint()

    @staticmethod
    def _style_tin(layer, interval):
        provider = layer.dataProvider()
        statistics = provider.bandStatistics(
            1,
            QgsRasterBandStats.Min | QgsRasterBandStats.Max,
        )
        minimum = statistics.minimumValue
        maximum = statistics.maximumValue
        if not math.isfinite(minimum) or not math.isfinite(maximum):
            return

        lower = math.floor(minimum / interval) * interval
        upper = math.ceil(maximum / interval) * interval
        class_count = max(1, int(round((upper - lower) / interval)))
        color_ramp = QgsStyle.defaultStyle().colorRamp("Spectral")
        if color_ramp is None:
            color_ramp = QgsStyle.defaultStyle().colorRamp("Viridis")

        items = []
        for index in range(class_count):
            class_min = lower + index * interval
            class_max = class_min + interval
            position = index / max(class_count - 1, 1)
            color = color_ramp.color(position)
            items.append(
                QgsColorRampShader.ColorRampItem(
                    class_max,
                    color,
                    f"{class_min:g}–{class_max:g} m",
                )
            )
        color_shader = QgsColorRampShader()
        color_shader.setColorRampType(QgsColorRampShader.Discrete)
        color_shader.setColorRampItemList(items)
        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(color_shader)
        layer.setRenderer(
            QgsSingleBandPseudoColorRenderer(provider, 1, raster_shader)
        )
        layer.triggerRepaint()

    @staticmethod
    def _style_source_contours(layer):
        symbol = QgsLineSymbol.createSimple(
            {"color": "120,120,120,130", "width": "0.18"}
        )
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()

    @staticmethod
    def _style_contours(layer):
        symbol = QgsLineSymbol.createSimple(
            {"color": "70,45,25,255", "width": "0.45"}
        )
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))

        settings = QgsPalLayerSettings()
        settings.enabled = True
        settings.fieldName = "ELEV"
        settings.placement = Qgis.LabelPlacement.Curved
        text_format = QgsTextFormat()
        text_format.setFont(QtGui.QFont("굴림"))
        text_format.setSize(8)
        text_format.setColor(QtGui.QColor(70, 45, 25))
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(0.8)
        buffer.setColor(QtGui.QColor("white"))
        text_format.setBuffer(buffer)
        settings.setFormat(text_format)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()

    @staticmethod
    def _style_boundary(layer):
        symbol = QgsFillSymbol.createSimple(
            {
                "color": "255,255,255,0",
                "outline_color": "220,45,45,255",
                "outline_width": "0.7",
                "outline_style": "dash",
            }
        )
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()

    @staticmethod
    def _remove_result_group(analysis_name):
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        for group_name in (f"{analysis_name}_표고경사분석", f"{analysis_name}_표고분석"):
            old_group = root.findGroup(group_name)
            if old_group is None:
                continue
            old_layer_ids = [node.layerId() for node in old_group.findLayers()]
            if old_layer_ids:
                project.removeMapLayers(old_layer_ids)
            old_group = root.findGroup(group_name)
            if old_group is not None and old_group.parent() is not None:
                old_group.parent().removeChildNode(old_group)

    @staticmethod
    def _add_result_group(
        analysis_name,
        tin_layer,
        source_layer,
        interval_layer,
        boundary_layer=None,
        slope_layer=None,
    ):
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group_name = f"{analysis_name}_표고경사분석"
        ElevationAnalysisController._remove_result_group(analysis_name)
        group = root.insertGroup(0, group_name)

        result_layers = [interval_layer, source_layer]
        if slope_layer is not None:
            result_layers.append(slope_layer)
        result_layers.append(tin_layer)
        if boundary_layer is not None:
            result_layers.insert(0, boundary_layer)
        for layer in result_layers:
            project.addMapLayer(layer, False)
            group.addLayer(layer)
        source_node = group.findLayer(source_layer.id())
        if source_node is not None:
            source_node.setItemVisibilityChecked(False)
        if slope_layer is not None:
            tin_node = group.findLayer(tin_layer.id())
            if tin_node is not None:
                tin_node.setItemVisibilityChecked(False)


def setup_elevation_analysis(iface, dock_widget):
    return ElevationAnalysisController(iface, dock_widget)
