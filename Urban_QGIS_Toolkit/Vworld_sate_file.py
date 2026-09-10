from qgis.core import QgsRasterLayer, QgsProject
from qgis.PyQt.QtWidgets import QMessageBox


def load_vworld_satellite(dock_widget):
    vworld_key = ""
    if hasattr(dock_widget, 'input_API') and dock_widget.input_API:
        vworld_key = dock_widget.input_API.text().strip()

    rlayer = None

    if vworld_key:
        uri = (
            "crs=EPSG:3857&dpiMode=7&format=image/jpeg&layers=Satellite"
            "&styles=default&tileMatrixSet=GoogleMapsCompatible"
            f"&url=https://api.vworld.kr/req/wmts/1.0.0/{vworld_key}/WMTSCapabilities.xml"
        )
        rlayer = QgsRasterLayer(uri, "브이월드 지도[Satellite]", "wms")
        if not rlayer.isValid():
            print("[WARN] 인증키로 위성 레이어를 불러오지 못해 무료 타일로 대체합니다.")
            rlayer = None

    if rlayer is None:
        tile_url = "https://xdworld.vworld.kr/2d/Satellite/service/{z}/{x}/{y}.jpeg"
        uri = f"type=xyz&url={tile_url}&zmax=18&zmin=0"
        rlayer = QgsRasterLayer(uri, "VWorld Satellite", "wms")

    if not rlayer.isValid():
        QMessageBox.warning(dock_widget, "경고", "브이월드 위성 레이어를 불러올 수 없습니다.")
        print("[ERROR] 브이월드 위성 레이어가 유효하지 않습니다.")
        return

    QgsProject.instance().addMapLayer(rlayer, False)

    root = QgsProject.instance().layerTreeRoot()
    root.insertLayer(-1, rlayer)

    print("[OK] 브이월드 위성지도가 추가되었습니다.")
