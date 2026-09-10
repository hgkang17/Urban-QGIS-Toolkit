from qgis.core import QgsRectangle, QgsWkbTypes, QgsPointXY
from qgis.gui import QgsMapTool, QgsRubberBand
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt


class DragZoomTool(QgsMapTool):
    def __init__(self, canvas, iface):
        super().__init__(canvas)
        self.canvas = canvas
        self.iface = iface
        self.rubber_band = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(QColor(255, 0, 0, 60))
        self.rubber_band.setWidth(1)
        self.start_point = None

    def canvasPressEvent(self, event):
        if self.start_point is None:
            self.start_point = event.mapPoint()
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        else:
            end_point = event.mapPoint()
            rect = QgsRectangle(self.start_point, end_point)
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

            if rect.width() > 0 and rect.height() > 0:
                self.canvas.setExtent(rect)
                self.canvas.refresh()

            self.start_point = None

    def canvasMoveEvent(self, event):
        if self.start_point is None:
            return
        current_point = event.mapPoint()
        rect = QgsRectangle(self.start_point, current_point)
        self._show_rect(rect)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.iface.actionPan().trigger()

    def deactivate(self):
        self.start_point = None
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        super().deactivate()

    def _show_rect(self, rect):
        points = [
            QgsPointXY(rect.xMinimum(), rect.yMinimum()),
            QgsPointXY(rect.xMinimum(), rect.yMaximum()),
            QgsPointXY(rect.xMaximum(), rect.yMaximum()),
            QgsPointXY(rect.xMaximum(), rect.yMinimum()),
        ]
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        for pt in points:
            self.rubber_band.addPoint(pt, False)
        self.rubber_band.addPoint(points[0], True)


def activate_drag_zoom(iface):
    canvas = iface.mapCanvas()
    tool = DragZoomTool(canvas, iface)
    canvas.setMapTool(tool)
