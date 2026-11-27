
from math import log

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.PyQt.QtGui import QFont, QFontMetricsF
from qgis.core import (
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterField,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterDefinition,
    QgsProject,
    QgsWkbTypes,
)

FONT_NAME = "굴림"
DXF_FONT_FILE = "txt"
READABLE_ROTATION = True
LAYER_MAIN = "JIBUN"
STYLE_NAME = "JIBUN"
CODEPAGE = "ANSI_949"
PY_CODEC = "cp949"


def dxf_escape(text):
    out = []
    for ch in text.replace("\r", " ").replace("\n", " "):
        try:
            ch.encode(PY_CODEC)
            out.append(ch)
        except UnicodeEncodeError:
            out.append("\\U+%04X" % ord(ch) if ord(ch) <= 0xFFFF else "?")
    return "".join(out)


def dxf_rotation(qgis_rotation):
    angle = (-qgis_rotation) % 360.0
    if READABLE_ROTATION and 90.0 < angle <= 270.0:
        angle = (angle - 180.0) % 360.0
    return angle


def write_dxf(path, records):
    lines = []

    def g(code, value):
        lines.append("%3d" % code)
        lines.append(str(value))

    g(0, "SECTION"); g(2, "HEADER")
    g(9, "$ACADVER"); g(1, "AC1009")
    g(9, "$DWGCODEPAGE"); g(3, CODEPAGE)
    g(0, "ENDSEC")

    g(0, "SECTION"); g(2, "TABLES")
    g(0, "TABLE"); g(2, "LTYPE"); g(70, 1)
    g(0, "LTYPE"); g(2, "CONTINUOUS"); g(70, 0); g(3, "Solid line"); g(72, 65); g(73, 0); g(40, "0.0")
    g(0, "ENDTAB")
    g(0, "TABLE"); g(2, "LAYER"); g(70, 2)
    for name, color in (("0", 7), (LAYER_MAIN, 7)):
        g(0, "LAYER"); g(2, name); g(70, 0); g(62, color); g(6, "CONTINUOUS")
    g(0, "ENDTAB")
    g(0, "TABLE"); g(2, "STYLE"); g(70, 2)
    g(0, "STYLE"); g(2, "STANDARD"); g(70, 0); g(40, "0.0"); g(41, "1.0"); g(50, "0.0")
    g(71, 0); g(42, "0.2"); g(3, "txt"); g(4, "")
    g(0, "STYLE"); g(2, STYLE_NAME); g(70, 0); g(40, "0.0"); g(41, "1.0"); g(50, "0.0")
    g(71, 0); g(42, "0.2"); g(3, DXF_FONT_FILE); g(4, "")
    g(0, "ENDTAB")
    g(0, "ENDSEC")

    g(0, "SECTION"); g(2, "ENTITIES")
    for x, y, h, rot, text in records:
        g(0, "TEXT")
        g(8, LAYER_MAIN)
        g(7, STYLE_NAME)
        g(10, "%.4f" % x); g(20, "%.4f" % y); g(30, "0.0")
        g(40, "%.4f" % h)
        g(1, dxf_escape(text))
        g(50, "%.4f" % rot)
        g(41, "1.0")
        g(72, 1)
        g(11, "%.4f" % x); g(21, "%.4f" % y); g(31, "0.0")
        g(73, 2)
    g(0, "ENDSEC")
    g(0, "EOF")

    with open(path, "w", encoding=PY_CODEC, newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")


def count_text_entities(path):
    with open(path, "r", encoding=PY_CODEC, newline="") as f:
        raw = f.read().splitlines()
    count = 0
    for i in range(0, len(raw) - 1, 2):
        if raw[i].strip() == "0" and raw[i + 1].strip() == "TEXT":
            count += 1
    return count


class JibunLabelDxfAlgorithm(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    FIELD = "FIELD"
    WIDTH_PAD = "WIDTH_PAD"
    FLOOR_HEIGHT = "FLOOR_HEIGHT"
    POLE_TOLERANCE_MIN = "POLE_TOLERANCE_MIN"
    POLE_TOLERANCE_RATIO = "POLE_TOLERANCE_RATIO"
    BINARY_STEPS = "BINARY_STEPS"
    DXF_HEIGHT_FACTOR = "DXF_HEIGHT_FACTOR"
    FALLBACK_HEIGHT = "FALLBACK_HEIGHT"
    OUTPUT_DXF = "OUTPUT_DXF"
    OUTPUT_POINTS = "OUTPUT_POINTS"

    def tr(self, string):
        return QCoreApplication.translate("JibunLabelDxfAlgorithm", string)

    def createInstance(self):
        return JibunLabelDxfAlgorithm()

    def name(self):
        return "jibun_label_dxf"

    def displayName(self):
        return self.tr("지적도 지번 내보내기")

    def group(self):
        return self.tr("지적도")

    def groupId(self):
        return "cadastral_tools"

    def shortHelpString(self):
        return self.tr(
            "지적도 필지별 지번을 SHP 포인트 레이어 및 DXF 파일로 추출합니다."
            " 라벨 크기는 면적에 비례하여 자동 조절되며, 위치는 중심점/이격점/크기 축소 순으로 결정됩니다."
            " 고급 파라미터를 통해 관련 수치를 직접 설정할 수 있습니다. 글자 크기는 DXF 텍스트 높이 배율로 조정하세요(SHP와 동일 크기:0.754)."
            " QGIS 라벨 엔진을 거치지 않고 DXF TEXT를 직접 생성하여 라벨 누락을 방지합니다."
            " DXF 글꼴스타일 호환을 위하여 기본 폰트는 txt.shx로 지정되오니 캐드 실행 후 글꼴(권장: 굴림)을 변경하시기 바랍니다."
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT, self.tr("지적도 레이어 선택"),
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterField(
                self.FIELD, self.tr("지번 필드 선택"),
                defaultValue="JIBUN", parentLayerParameterName=self.INPUT,
                type=QgsProcessingParameterField.String
            )
        )
        advanced_params = [
            QgsProcessingParameterNumber(
                self.WIDTH_PAD, self.tr("글꼴 가로폭 계수"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=1.20, minValue=0.5, maxValue=5.0
            ),
            QgsProcessingParameterNumber(
                self.FLOOR_HEIGHT, self.tr("폰트 크기 최솟값(축소 전)"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.2, minValue=0.0
            ),
            QgsProcessingParameterNumber(
                self.POLE_TOLERANCE_MIN, self.tr("이격점 오차 허용 최솟값"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.01, minValue=0.0001
            ),
            QgsProcessingParameterNumber(
                self.POLE_TOLERANCE_RATIO, self.tr("이격점 오차 허용 비율"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.01, minValue=0.0001
            ),
            QgsProcessingParameterNumber(
                self.BINARY_STEPS, self.tr("축소 이진탐색 반복 횟수"),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=10, minValue=1, maxValue=30
            ),
            QgsProcessingParameterNumber(
                self.DXF_HEIGHT_FACTOR, self.tr("DXF 텍스트 높이 배율"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.75, minValue=0.01
            ),
            QgsProcessingParameterNumber(
                self.FALLBACK_HEIGHT, self.tr("폰트 크기 0일 때 대체값"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.2, minValue=0.01
            ),
        ]
        for param in advanced_params:
            param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(param)
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_DXF, self.tr("DXF 파일 저장"),
                self.tr("DXF files (*.dxf)")
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_POINTS, self.tr("SHP 포인트 레이어 저장"),
                QgsProcessing.TypeVectorPoint, optional=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.INPUT, context)
        if source is None:
            raise QgsProcessingException(self.invalidSourceError(parameters, self.INPUT))
        if source.sourceCrs().isGeographic():
            raise QgsProcessingException(self.tr("미터 등 지도 단위를 쓰는 투영좌표계여야 합니다."))

        field_name = self.parameterAsString(parameters, self.FIELD, context)
        width_pad = self.parameterAsDouble(parameters, self.WIDTH_PAD, context)
        floor_height = self.parameterAsDouble(parameters, self.FLOOR_HEIGHT, context)
        pole_tol_min = self.parameterAsDouble(parameters, self.POLE_TOLERANCE_MIN, context)
        pole_tol_ratio = self.parameterAsDouble(parameters, self.POLE_TOLERANCE_RATIO, context)
        binary_steps = self.parameterAsInt(parameters, self.BINARY_STEPS, context)
        dxf_height_factor = self.parameterAsDouble(parameters, self.DXF_HEIGHT_FACTOR, context)
        fallback_height = self.parameterAsDouble(parameters, self.FALLBACK_HEIGHT, context)
        output_path = self.parameterAsFileOutput(parameters, self.OUTPUT_DXF, context)
        if not output_path.lower().endswith(".dxf"):
            output_path += ".dxf"

        out_fields = QgsFields()
        out_fields.append(QgsField("SRC_FID", QVariant.LongLong))
        out_fields.append(QgsField("JIBUN", QVariant.String, len=254))
        out_fields.append(QgsField("TEXT_H", QVariant.Double, len=20, prec=6))
        out_fields.append(QgsField("ROT_QGIS", QVariant.Double, len=12, prec=4))
        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT_POINTS, context,
            out_fields, QgsWkbTypes.Point, source.sourceCrs()
        )

        font = QFont(FONT_NAME)
        font.setPointSizeF(100.0)
        metrics = QFontMetricsF(font)
        font_h = max(metrics.height(), 1.0)

        rot_expr = QgsExpression("(main_angle($geometry) + 90) % 180")
        rot_ctx = QgsExpressionContext()
        rot_ctx.appendScope(QgsExpressionContextUtils.globalScope())
        rot_ctx.appendScope(QgsExpressionContextUtils.projectScope(QgsProject.instance()))
        rot_expr.prepare(rot_ctx)
        rot_feature = QgsFeature()

        def label_rotation(geometry):
            rot_feature.setGeometry(geometry)
            rot_ctx.setFeature(rot_feature)
            value = rot_expr.evaluate(rot_ctx)
            if rot_expr.hasEvalError():
                return 0.0
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def requested_height(area):
            if area <= 0:
                return 0.0
            return max(floor_height, (log(area, 2) ** 3) * 0.006)

        def make_rect(center, text_h, text_ratio, rotation):
            text_w = text_h * text_ratio
            x0, x1 = center.x() - text_w / 2.0, center.x() + text_w / 2.0
            y0, y1 = center.y() - text_h / 2.0, center.y() + text_h / 2.0
            rect = QgsGeometry.fromPolygonXY([[
                QgsPointXY(x0, y0), QgsPointXY(x1, y0),
                QgsPointXY(x1, y1), QgsPointXY(x0, y1), QgsPointXY(x0, y0)
            ]])
            rect.rotate(rotation, center)
            return rect

        def fits(polygon, center, h, text_ratio, rotation):
            return h > 0 and polygon.contains(make_rect(center, h, text_ratio, rotation))

        def pole_point(part):
            tolerance = max(pole_tol_min, (part.area() ** 0.5) * pole_tol_ratio)
            result = part.poleOfInaccessibility(tolerance)
            point_geometry = result[0] if isinstance(result, tuple) else result
            p = point_geometry.asPoint()
            return QgsPointXY(p.x(), p.y())

        def largest_safe_height(part, center, requested_h, ratio, rotation, floor=0.0):
            low, high = floor, requested_h
            for _ in range(binary_steps):
                middle = (low + high) / 2.0
                if fits(part, center, middle, ratio, rotation):
                    low = middle
                else:
                    high = middle
            return low

        def polygon_parts(geometry):
            parts = geometry.asGeometryCollection() if geometry.isMultipart() else [geometry]
            return [p for p in parts if p.type() == QgsWkbTypes.PolygonGeometry and not p.isEmpty()]

        total = source.featureCount()
        records = []
        skipped = 0
        processed = 0

        for feature in source.getFeatures():
            if feedback.isCanceled():
                break
            processed += 1
            geom = feature.geometry()
            text = "".join(str(feature[field_name] or "").split())
            output_point = None
            final_h = 0.0
            rotation = 0.0
            valid = None
            has_content = bool(text) and not geom.isNull() and not geom.isEmpty()

            if has_content:
                valid = QgsGeometry(geom)
                if not valid.isGeosValid():
                    valid = valid.makeValid()

                if not valid.isEmpty():
                    parts = polygon_parts(valid)
                    initial_h = requested_height(valid.area())
                    ratio = max(1.0, metrics.horizontalAdvance(text) / font_h) * width_pad
                    rotation = label_rotation(valid)

                    centroid = valid.centroid().asPoint()
                    centroid_pt = QgsPointXY(centroid.x(), centroid.y())
                    if fits(valid, centroid_pt, initial_h, ratio, rotation):
                        output_point = centroid_pt
                        final_h = initial_h

                    if output_point is None:
                        pole_candidates = []
                        for part in parts:
                            pole = pole_point(part)
                            if fits(part, pole, initial_h, ratio, rotation):
                                pole_candidates.append((part.area(), pole))
                        if pole_candidates:
                            _, output_point = max(pole_candidates, key=lambda item: item[0])
                            final_h = initial_h

                    if output_point is None:
                        shrunk_candidates = []
                        centroid_h = largest_safe_height(valid, centroid_pt, initial_h, ratio, rotation)
                        if centroid_h > 0:
                            shrunk_candidates.append((centroid_h, centroid_pt))
                        for part in parts:
                            pole = pole_point(part)
                            h = largest_safe_height(part, pole, initial_h, ratio, rotation)
                            if h > 0:
                                shrunk_candidates.append((h, pole))
                        if shrunk_candidates:
                            final_h, output_point = max(shrunk_candidates, key=lambda item: item[0])

                if output_point is None:
                    surface_source = valid if (valid is not None and not valid.isEmpty()) else geom
                    if not surface_source.isNull() and not surface_source.isEmpty():
                        fallback = surface_source.pointOnSurface().asPoint()
                        output_point = QgsPointXY(fallback.x(), fallback.y())

            if sink is not None:
                out_feature = QgsFeature(out_fields)
                out_feature.setGeometry(
                    QgsGeometry.fromPointXY(output_point if output_point else QgsPointXY(0, 0))
                )
                out_feature.setAttributes([feature.id(), text, final_h, rotation])
                sink.addFeature(out_feature, QgsFeatureSink.FastInsert)

            if output_point is None:
                skipped += 1
            else:
                dxf_h = final_h if final_h > 0 else fallback_height
                records.append((
                    output_point.x(), output_point.y(),
                    dxf_h * dxf_height_factor, dxf_rotation(rotation), text
                ))

            if total:
                feedback.setProgress(int(processed / total * 100))

        write_dxf(output_path, records)
        written = count_text_entities(output_path)

        feedback.pushInfo("저장: {}".format(output_path))
        feedback.pushInfo(
            "입력 필지 {}개 = DXF TEXT {}개 + 제외(빈 지번/빈 도형) {}개".format(
                processed, written, skipped
            )
        )
        feedback.pushInfo(
            "좌표계: {} (경계선 DXF도 같은 좌표계로 내보내야 겹칩니다)".format(
                source.sourceCrs().authid()
            )
        )
        if written != len(records) or written + skipped != processed:
            feedback.reportError("경고: 개수가 일치하지 않습니다. 결과를 확인하세요.", fatalError=False)
        else:
            feedback.pushInfo("개수 검토: 누락 0개")

        results = {self.OUTPUT_DXF: output_path}
        if dest_id is not None:
            results[self.OUTPUT_POINTS] = dest_id
        return results
