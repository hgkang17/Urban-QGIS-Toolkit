import os
from qgis.core import QgsMapSettings, QgsMapRendererCustomPainterJob
from qgis.PyQt.QtGui import QImage, QPainter
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QMessageBox, QApplication, QProgressDialog


def _get_unique_path(folder, base_name, ext):
    path = os.path.join(folder, f"{base_name}.{ext}")
    if not os.path.exists(path):
        return path

    index = 1
    while True:
        path = os.path.join(folder, f"{base_name} ({index}).{ext}")
        if not os.path.exists(path):
            return path
        index += 1


def export_canvas_to_jpg(iface, dock_widget):
    canvas = iface.mapCanvas()
    dpi = 200

    screen_dpi = canvas.mapSettings().outputDpi()
    scale = dpi / screen_dpi

    output_size = QSize(
        int(canvas.width() * scale),
        int(canvas.height() * scale)
    )

    settings = QgsMapSettings()
    settings.setLayers(canvas.layers())
    settings.setBackgroundColor(canvas.canvasColor())
    settings.setOutputSize(output_size)
    settings.setExtent(canvas.extent())
    settings.setOutputDpi(dpi)
    settings.setDestinationCrs(canvas.mapSettings().destinationCrs())

    image = QImage(output_size, QImage.Format.Format_RGB32)
    image.setDotsPerMeterX(round(dpi * 39.3701))
    image.setDotsPerMeterY(round(dpi * 39.3701))
    image.fill(canvas.canvasColor())

    progress = QProgressDialog("이미지 추출중입니다...", None, 0, 0, dock_widget)
    progress.setWindowTitle("알림")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.show()
    QApplication.processEvents()

    painter = QPainter(image)
    job = QgsMapRendererCustomPainterJob(settings, painter)
    job.start()
    job.waitForFinished()
    painter.end()

    progress.close()
    progress.deleteLater()
    QApplication.processEvents()

    desktop_folder = os.path.join(os.path.expanduser("~"), "Desktop")
    save_path = _get_unique_path(desktop_folder, "qgis_imege", "jpg")

    if not image.save(save_path, "jpg"):
        QMessageBox.warning(dock_widget, "경고", "이미지를 저장하지 못했습니다.")
        return

    print(f"[OK] 지도 화면이 저장되었습니다: {save_path}")
    QMessageBox.information(dock_widget, "완료", f"저장 완료:\n{save_path}")
