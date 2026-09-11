
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtWidgets import QDialog, QInputDialog, QMessageBox
from qgis.core import (
    Qgis,
    QgsPalLayerSettings,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)


def label_buffer(iface, dock_widget):
    selected_layers = [
        layer
        for layer in iface.layerTreeView().selectedLayers()
        if isinstance(layer, QgsVectorLayer)
    ]

    if not selected_layers:
        QMessageBox.warning(dock_widget, "레이어 선택", "라벨을 적용할 벡터 레이어를 선택해주세요.")
        return

    if len(selected_layers) > 1:
        QMessageBox.warning(dock_widget, "레이어 선택", "벡터 레이어를 하나만 선택해주세요.")
        return

    layer = selected_layers[0]
    field_names = [field.name() for field in layer.fields()]

    if not field_names:
        QMessageBox.warning(dock_widget, "필드 없음", "선택한 레이어에 라벨로 사용할 필드가 없습니다.")
        return

    field_dialog = QInputDialog(dock_widget)
    field_dialog.setWindowTitle("라벨 필드 선택")
    field_dialog.setLabelText(f"'{layer.name()}' 레이어의 라벨 필드를 선택하세요.")
    field_dialog.setComboBoxItems(field_names)
    field_dialog.setComboBoxEditable(False)
    field_dialog.setMinimumWidth(360)
    field_dialog.setStyleSheet("""
        QInputDialog {
            background-color: rgb(42, 120, 214);
            font-family: "Noto Sans KR";
            font-size: 9pt;
        }
        QInputDialog QLabel {
            color: rgb(255, 255, 255);
            background: transparent;
            font-family: "Noto Sans KR";
            font-weight: regular;
        }
        QInputDialog QComboBox {
            color: rgb(0, 0, 0);
            background-color: rgb(255, 255, 255);
            border: 1px solid rgb(180, 220, 250);
            border-radius: 4px;
            padding: 5px 8px;
            min-height: 20px;
            font-family: "Noto Sans KR";
        }
        QInputDialog QComboBox:hover,
        QInputDialog QComboBox:focus {
            border: 1px solid rgb(13, 27, 61);
        }
        QInputDialog QComboBox QAbstractItemView {
            color: rgb(0, 0, 0);
            background-color: rgb(255, 255, 255);
            border: 1px solid rgb(180, 220, 250);
            selection-color: rgb(255, 255, 255);
            selection-background-color: rgb(13, 27, 61);
            outline: none;
            font-family: "Noto Sans KR";
        }
        QInputDialog QPushButton {
            color: rgb(255, 255, 255);
            background-color: rgb(13, 27, 61);
            border: none;
            border-radius: 4px;
            padding: 6px 14px;
            min-width: 64px;
            font-family: "Noto Sans KR";
            font-weight: bold;
        }
        QInputDialog QPushButton:hover {
            background-color: rgb(27, 48, 91);
        }
        QInputDialog QPushButton:pressed {
            background-color: rgb(7, 16, 38);
        }
    """)

    if field_dialog.exec() != QDialog.DialogCode.Accepted:
        return

    field_name = field_dialog.textValue()
    if not field_name:
        return

    text_format = QgsTextFormat()
    font = QFont("Noto Sans KR")
    font.setBold(True)
    text_format.setFont(font)
    text_format.setSize(10)
    text_format.setColor(QColor(30, 30, 30))

    buffer_settings = QgsTextBufferSettings()
    buffer_settings.setEnabled(True)
    buffer_settings.setSize(1.0)
    buffer_settings.setColor(QColor(255, 255, 255))
    buffer_settings.setOpacity(1.0)
    buffer_settings.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    text_format.setBuffer(buffer_settings)

    label_settings = QgsPalLayerSettings()
    label_settings.enabled = True
    label_settings.fieldName = field_name
    label_settings.setFormat(text_format)

    geometry_type = layer.geometryType()
    if geometry_type == QgsWkbTypes.PointGeometry:
        label_settings.placement = Qgis.LabelPlacement.AroundPoint
    elif geometry_type == QgsWkbTypes.LineGeometry:
        label_settings.placement = Qgis.LabelPlacement.Line
    else:
        label_settings.placement = Qgis.LabelPlacement.OverPoint

    layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()

    iface.layerTreeView().refreshLayerSymbology(layer.id())
