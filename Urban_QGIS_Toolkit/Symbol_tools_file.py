import random
from qgis.core import (
    QgsSymbol, QgsSingleSymbolRenderer, QgsLayerTreeGroup, QgsLayerTreeLayer,
    QgsVectorLayer, QgsRenderContext, QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer,
    QgsSimpleMarkerSymbolLayer, QgsFillSymbol, QgsMarkerSymbol, QgsLineSymbol,
    QgsSymbolLegendNode, QgsLayerTreeModelLegendNode
)
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtCore import Qt, QTimer, QItemSelectionModel
from qgis.PyQt.QtWidgets import (
    QCheckBox, QColorDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QWidget,
)
from .SymBol_CopyPaste_file import _get_selection


def _expand_to_layers(nodes):
    layers = []
    for node in nodes:
        if isinstance(node, QgsLayerTreeGroup):
            layers.extend(_expand_to_layers(node.children()))
        elif isinstance(node, QgsLayerTreeLayer):
            layer = node.layer()
            if isinstance(layer, QgsVectorLayer):
                layers.append(layer)
    return layers


def _apply_outline_only(symbol, color, width=None, line_style=None):
    while symbol.symbolLayerCount() > 1:
        symbol.deleteSymbolLayer(symbol.symbolLayerCount() - 1)

    layer = symbol.symbolLayer(0)

    if isinstance(symbol, QgsFillSymbol):
        if isinstance(layer, QgsSimpleFillSymbolLayer):
            layer.setBrushStyle(Qt.NoBrush)
            if color is not None:
                layer.setStrokeColor(color)
            if width is not None:
                layer.setStrokeWidth(width)
            if line_style is not None:
                layer.setStrokeStyle(line_style)
        else:
            new_layer = QgsSimpleFillSymbolLayer()
            new_layer.setBrushStyle(Qt.NoBrush)
            if color is not None:
                new_layer.setStrokeColor(color)
            if width is not None:
                new_layer.setStrokeWidth(width)
            if line_style is not None:
                new_layer.setStrokeStyle(line_style)
            symbol.changeSymbolLayer(0, new_layer)
    elif isinstance(symbol, QgsMarkerSymbol):
        if isinstance(layer, QgsSimpleMarkerSymbolLayer):
            layer.setBrushStyle(Qt.NoBrush)
            if color is not None:
                layer.setStrokeColor(color)
            if width is not None:
                layer.setStrokeWidth(width)
        else:
            new_layer = QgsSimpleMarkerSymbolLayer()
            new_layer.setBrushStyle(Qt.NoBrush)
            if color is not None:
                new_layer.setStrokeColor(color)
            if width is not None:
                new_layer.setStrokeWidth(width)
            symbol.changeSymbolLayer(0, new_layer)
    elif isinstance(symbol, QgsLineSymbol):
        if isinstance(layer, QgsSimpleLineSymbolLayer):
            if color is not None:
                layer.setColor(color)
            if width is not None:
                layer.setWidth(width)
            if line_style is not None:
                layer.setPenStyle(line_style)
        else:
            new_layer = QgsSimpleLineSymbolLayer()
            if color is not None:
                new_layer.setColor(color)
            if width is not None:
                new_layer.setWidth(width)
            if line_style is not None:
                new_layer.setPenStyle(line_style)
            symbol.changeSymbolLayer(0, new_layer)


def _apply_outline_to_selection(iface, color, width=None, line_style=None):
    nodes, legend_nodes = _get_selection(iface)
    touched_layers = {}
    selected_legend_items = _get_legend_selection_items(legend_nodes)

    for legend_node in legend_nodes:
        if not isinstance(legend_node, QgsSymbolLegendNode) or legend_node.symbol() is None:
            continue
        layer = legend_node.layerNode().layer()
        renderer = layer.renderer()
        rule_key = legend_node.data(QgsLayerTreeModelLegendNode.RuleKeyRole)
        symbol = legend_node.symbol().clone()
        _apply_outline_only(symbol, color, width, line_style)
        renderer.setLegendSymbolItem(rule_key, symbol)
        layer.setRenderer(renderer)
        touched_layers[layer.id()] = layer

    context = QgsRenderContext()
    for layer in _expand_to_layers(nodes):
        renderer = layer.renderer()
        for symbol in renderer.symbols(context):
            _apply_outline_only(symbol, color, width, line_style)
        layer.setRenderer(renderer)
        touched_layers[layer.id()] = layer

    _refresh_layers_and_restore_selection(iface, touched_layers, selected_legend_items)

    return touched_layers


def _remove_outline_only(symbol):
    if not isinstance(symbol, (QgsFillSymbol, QgsMarkerSymbol)):
        return False

    changed = False
    for index in range(symbol.symbolLayerCount()):
        symbol_layer = symbol.symbolLayer(index)
        if hasattr(symbol_layer, "setStrokeStyle"):
            symbol_layer.setStrokeStyle(Qt.NoPen)
            changed = True

    return changed


def _remove_outline_from_selection(iface):
    nodes, legend_nodes = _get_selection(iface)
    touched_layers = {}
    selected_legend_items = _get_legend_selection_items(legend_nodes)

    for legend_node in legend_nodes:
        if not isinstance(legend_node, QgsSymbolLegendNode) or legend_node.symbol() is None:
            continue

        layer = legend_node.layerNode().layer()
        renderer = layer.renderer()
        rule_key = legend_node.data(QgsLayerTreeModelLegendNode.RuleKeyRole)
        symbol = legend_node.symbol().clone()

        if _remove_outline_only(symbol):
            renderer.setLegendSymbolItem(rule_key, symbol)
            layer.setRenderer(renderer)
            touched_layers[layer.id()] = layer

    context = QgsRenderContext()
    for layer in _expand_to_layers(nodes):
        renderer = layer.renderer()
        changed = False

        for symbol in renderer.symbols(context):
            if _remove_outline_only(symbol):
                changed = True

        if changed:
            layer.setRenderer(renderer)
            touched_layers[layer.id()] = layer

    _refresh_layers_and_restore_selection(iface, touched_layers, selected_legend_items)

    return touched_layers


def outline_symbol_del(iface, dock_widget):
    nodes, legend_nodes = _get_selection(iface)
    if not nodes and not legend_nodes:
        QMessageBox.warning(dock_widget, "경고", "적용할 레이어(또는 심볼)를 선택해주세요.")
        return

    touched = _remove_outline_from_selection(iface)

    if not touched:
        QMessageBox.warning(dock_widget, "경고", "외곽선을 제거할 면 또는 점 심볼이 없습니다.")
        return


def fill_symbol_del(iface, dock_widget):
    nodes, legend_nodes = _get_selection(iface)
    if not nodes and not legend_nodes:
        QMessageBox.warning(dock_widget, "경고", "적용할 레이어(또는 심볼)를 선택해주세요.")
        return

    touched = _apply_outline_to_selection(iface, None)

    if not touched:
        QMessageBox.warning(dock_widget, "경고", "벡터 레이어에만 적용할 수 있습니다.")
        return


def set_white_outline(iface, dock_widget):
    nodes, legend_nodes = _get_selection(iface)
    if not nodes and not legend_nodes:
        QMessageBox.warning(dock_widget,"[WARN] 적용할 레이어(또는 심볼)를 선택해주세요.")
        return

    white = QColor(255, 255, 255)
    touched = _apply_outline_to_selection(iface, white)

    if not touched:
        print("[WARN] 벡터 레이어에만 적용할 수 있습니다.")
        return

    print(f"[OK] {len(touched)}개 레이어에 흰색 외곽선이 적용되었습니다.")


def _reset_layer_symbol(layer):
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    random_color = QColor.fromHsv(
                            random.randint(0, 359),
                            random.randint(130, 190),
                            random.randint(225, 250)
                        )
    symbol.setColor(random_color)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def _reset_legend_symbol(legend_node):
    layer = legend_node.layerNode().layer()
    renderer = layer.renderer()
    rule_key = legend_node.data(QgsLayerTreeModelLegendNode.RuleKeyRole)

    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    random_color = QColor.fromHsv(
        random.randint(0, 359),
        random.randint(130, 190),
        random.randint(225, 250)
    )
    symbol.setColor(random_color)

    renderer.setLegendSymbolItem(rule_key, symbol)
    layer.setRenderer(renderer)
    return layer


def _restore_legend_selection(iface, selected_items):
    view = iface.layerTreeView()
    tree_model = view.layerTreeModel()
    view_model = view.model()
    selection_model = view.selectionModel()
    last_index = None

    for layer_id, rule_key in selected_items:
        layer_node = tree_model.rootGroup().findLayer(layer_id)
        if layer_node is None:
            continue

        for legend_node in tree_model.layerLegendNodes(layer_node):
            current_key = legend_node.data(QgsLayerTreeModelLegendNode.RuleKeyRole)
            if current_key != rule_key:
                continue

            source_index = tree_model.legendNode2index(legend_node)
            target_index = (
                view_model.mapFromSource(source_index)
                if hasattr(view_model, "mapFromSource")
                else source_index
            )

            if target_index.isValid():
                selection_model.select(
                    target_index,
                    QItemSelectionModel.Select | QItemSelectionModel.Rows
                )
                last_index = target_index
            break

    if last_index is not None:
        selection_model.setCurrentIndex(last_index, QItemSelectionModel.NoUpdate)


def _get_legend_selection_items(legend_nodes):
    selected_items = []
    for legend_node in legend_nodes:
        if not isinstance(legend_node, QgsSymbolLegendNode) or legend_node.symbol() is None:
            continue
        selected_items.append((
            legend_node.layerNode().layer().id(),
            legend_node.data(QgsLayerTreeModelLegendNode.RuleKeyRole)
        ))
    return selected_items


def _refresh_layers_and_restore_selection(iface, touched_layers, selected_items=None):
    for layer in touched_layers.values():
        layer.triggerRepaint()
        iface.layerTreeView().refreshLayerSymbology(layer.id())

    if selected_items:
        QTimer.singleShot(
            0,
            lambda items=list(selected_items): _restore_legend_selection(iface, items)
        )


def _reset_symbol_fill_only(symbol):
    if not isinstance(symbol, (QgsFillSymbol, QgsMarkerSymbol)):
        return False

    random_color = QColor.fromHsv(
        random.randint(0, 359),
        random.randint(130, 190),
        random.randint(225, 250)
    )
    changed = False

    for index in range(symbol.symbolLayerCount()):
        symbol_layer = symbol.symbolLayer(index)
        if isinstance(symbol_layer, (QgsSimpleFillSymbolLayer, QgsSimpleMarkerSymbolLayer)):
            symbol_layer.setBrushStyle(Qt.SolidPattern)
            symbol_layer.setColor(random_color)
            changed = True

    return changed


def clear_symbol_fill_this(iface, dock_widget):
    nodes, legend_nodes = _get_selection(iface)
    if not nodes and not legend_nodes:
        QMessageBox.warning(dock_widget, "경고", "채우기를 초기화할 레이어(또는 심볼)를 선택해주세요.")
        return

    touched_layers = {}
    selected_legend_items = _get_legend_selection_items(legend_nodes)

    for legend_node in legend_nodes:
        if not isinstance(legend_node, QgsSymbolLegendNode) or legend_node.symbol() is None:
            continue

        layer = legend_node.layerNode().layer()
        renderer = layer.renderer()
        rule_key = legend_node.data(QgsLayerTreeModelLegendNode.RuleKeyRole)
        symbol = legend_node.symbol().clone()

        if _reset_symbol_fill_only(symbol):
            renderer.setLegendSymbolItem(rule_key, symbol)
            layer.setRenderer(renderer)
            touched_layers[layer.id()] = layer

    context = QgsRenderContext()
    for layer in _expand_to_layers(nodes):
        renderer = layer.renderer()
        changed = False

        for symbol in renderer.symbols(context):
            if _reset_symbol_fill_only(symbol):
                changed = True

        if changed:
            layer.setRenderer(renderer)
            touched_layers[layer.id()] = layer

    if not touched_layers:
        QMessageBox.warning(dock_widget, "경고", "채우기를 초기화할 면 또는 점 심볼이 없습니다.")
        return

    _refresh_layers_and_restore_selection(iface, touched_layers, selected_legend_items)


def _reset_symbol_outline_only(symbol):
    if not isinstance(symbol, (QgsFillSymbol, QgsMarkerSymbol, QgsLineSymbol)):
        return False

    random_color = QColor.fromHsv(
        random.randint(0, 359),
        random.randint(130, 190),
        random.randint(225, 250)
    )
    changed = False

    for index in range(symbol.symbolLayerCount()):
        symbol_layer = symbol.symbolLayer(index)
        if isinstance(symbol_layer, (QgsSimpleFillSymbolLayer, QgsSimpleMarkerSymbolLayer)):
            symbol_layer.setStrokeStyle(Qt.SolidLine)
            symbol_layer.setStrokeColor(random_color)
            symbol_layer.setStrokeWidth(0.26)
            changed = True
        elif isinstance(symbol_layer, QgsSimpleLineSymbolLayer):
            symbol_layer.setPenStyle(Qt.SolidLine)
            symbol_layer.setColor(random_color)
            symbol_layer.setWidth(0.26)
            changed = True

    return changed


def clear_symbol_outline_this(iface, dock_widget):
    nodes, legend_nodes = _get_selection(iface)
    if not nodes and not legend_nodes:
        QMessageBox.warning(dock_widget, "경고", "외곽선을 초기화할 레이어(또는 심볼)를 선택해주세요.")
        return

    touched_layers = {}
    selected_legend_items = _get_legend_selection_items(legend_nodes)

    for legend_node in legend_nodes:
        if not isinstance(legend_node, QgsSymbolLegendNode) or legend_node.symbol() is None:
            continue

        layer = legend_node.layerNode().layer()
        renderer = layer.renderer()
        rule_key = legend_node.data(QgsLayerTreeModelLegendNode.RuleKeyRole)
        symbol = legend_node.symbol().clone()

        if _reset_symbol_outline_only(symbol):
            renderer.setLegendSymbolItem(rule_key, symbol)
            layer.setRenderer(renderer)
            touched_layers[layer.id()] = layer

    context = QgsRenderContext()
    for layer in _expand_to_layers(nodes):
        renderer = layer.renderer()
        changed = False

        for symbol in renderer.symbols(context):
            if _reset_symbol_outline_only(symbol):
                changed = True

        if changed:
            layer.setRenderer(renderer)
            touched_layers[layer.id()] = layer

    if not touched_layers:
        QMessageBox.warning(dock_widget, "경고", "외곽선을 초기화할 면, 점 또는 선 심볼이 없습니다.")
        return

    _refresh_layers_and_restore_selection(iface, touched_layers, selected_legend_items)


def clear_symbol(iface, dock_widget):
    nodes, legend_nodes = _get_selection(iface)
    if not nodes and not legend_nodes:
        QMessageBox.warning(dock_widget, "경고", "초기화할 레이어(또는 심볼)를 선택해주세요.")
        return

    touched_layers = {}
    selected_legend_items = _get_legend_selection_items(legend_nodes)

    for legend_node in legend_nodes:
        if not isinstance(legend_node, QgsSymbolLegendNode) or legend_node.symbol() is None:
            continue
        layer = _reset_legend_symbol(legend_node)
        touched_layers[layer.id()] = layer

    for layer in _expand_to_layers(nodes):
        _reset_layer_symbol(layer)
        touched_layers[layer.id()] = layer

    if not touched_layers:
        QMessageBox.warning(dock_widget, "경고", "벡터 레이어에만 적용할 수 있습니다.")
        return

    _refresh_layers_and_restore_selection(iface, touched_layers, selected_legend_items)

def set_red_dashdotdot_outline(iface, dock_widget):
    nodes, legend_nodes = _get_selection(iface)
    if not nodes and not legend_nodes:
        QMessageBox.warning(dock_widget, "경고", "적용할 레이어(또는 심볼)를 선택해주세요.")
        return

    red = QColor(255, 0, 0)
    touched = _apply_outline_to_selection(iface, red, width=1.0, line_style=Qt.DashDotDotLine)

    if not touched:
        QMessageBox.warning(dock_widget, "경고", "벡터 레이어에만 적용할 수 있습니다.")
        return

    print(f"[OK] {len(touched)}개 레이어에 빨간색 2점쇄선 외곽선이 적용되었습니다.")


SYMBOL_PALETTE_COLORS = [
    ("빨강", (255, 0, 0)),
    ("주황", (255, 128, 0)),
    ("노랑", (255, 255, 0)),
    ("초록", (0, 255, 0)),
    ("파랑", (0, 0, 255)),
    ("보라", (128, 0, 255)),
    ("흰색", (255, 255, 255)),
    ("검정", (0, 0, 0)),
    ("파스텔 빨강", (255, 179, 186)),
    ("파스텔 주황", (255, 209, 179)),
    ("파스텔 노랑", (255, 244, 179)),
    ("파스텔 초록", (186, 230, 190)),
    ("파스텔 파랑", (179, 217, 255)),
    ("파스텔 보라", (215, 190, 235)),
    ("민트", (128, 220, 200)),
    ("하늘", (90, 190, 235)),
    ("청록", (0, 150, 155)),
    ("분홍", (235, 90, 150)),
    ("갈색", (145, 95, 65)),
    ("회색", (128, 128, 128)),
    ("연회색", (205, 205, 205)),
    ("진회색", (70, 70, 70)),
    ("네이비", (13, 27, 61)),
]


def _apply_palette_color_to_symbol(symbol, color, use_fill, use_outline, use_pattern):
    changed = False

    symbol_name = symbol.__class__.__name__.lower()
    if use_fill and "line" not in symbol_name:
        saved_outline_colors = []
        for index in range(symbol.symbolLayerCount()):
            symbol_layer = symbol.symbolLayer(index)
            if hasattr(symbol_layer, "strokeColor") and hasattr(symbol_layer, "setStrokeColor"):
                saved_outline_colors.append((symbol_layer, QColor(symbol_layer.strokeColor())))

        symbol.setColor(color)
        changed = True

        for index in range(symbol.symbolLayerCount()):
            symbol_layer = symbol.symbolLayer(index)
            layer_name = symbol_layer.__class__.__name__.lower()
            is_pattern_layer = "pattern" in layer_name or "hatch" in layer_name or "svg" in layer_name
            if not is_pattern_layer and hasattr(symbol_layer, "setBrushStyle"):
                symbol_layer.setBrushStyle(Qt.SolidPattern)

        if not use_outline:
            for symbol_layer, outline_color in saved_outline_colors:
                symbol_layer.setStrokeColor(outline_color)

    for index in range(symbol.symbolLayerCount()):
        symbol_layer = symbol.symbolLayer(index)
        layer_name = symbol_layer.__class__.__name__.lower()
        is_pattern = "pattern" in layer_name or "hatch" in layer_name

        if use_pattern and is_pattern:
            sub_symbol = symbol_layer.subSymbol() if hasattr(symbol_layer, "subSymbol") else None
            if sub_symbol is not None:
                sub_symbol.setColor(color)
                changed = True
            elif hasattr(symbol_layer, "setColor"):
                symbol_layer.setColor(color)
                changed = True

        if use_outline:
            if hasattr(symbol_layer, "setStrokeColor"):
                symbol_layer.setStrokeColor(color)
                changed = True
            elif "line" in layer_name and hasattr(symbol_layer, "setColor"):
                symbol_layer.setColor(color)
                changed = True

    return changed


def _apply_palette_color_to_selection(
    iface_object,
    color,
    use_fill,
    use_outline,
    use_pattern,
    selected_nodes=None,
    selected_legend_nodes=None,
):
    if selected_nodes is None or selected_legend_nodes is None:
        nodes, legend_nodes = _get_selection(iface_object)
    else:
        nodes = selected_nodes
        legend_nodes = selected_legend_nodes
    touched_layers = {}
    selected_legend_items = _get_legend_selection_items(legend_nodes)

    for legend_node in legend_nodes:
        if not isinstance(legend_node, QgsSymbolLegendNode) or legend_node.symbol() is None:
            continue

        layer = legend_node.layerNode().layer()
        renderer = layer.renderer().clone()
        rule_key = legend_node.data(QgsLayerTreeModelLegendNode.RuleKeyRole)
        symbol = legend_node.symbol().clone()

        if _apply_palette_color_to_symbol(symbol, color, use_fill, use_outline, use_pattern):
            renderer.setLegendSymbolItem(rule_key, symbol)
            layer.setRenderer(renderer)
            touched_layers[layer.id()] = layer

    render_context = QgsRenderContext()
    for layer in _expand_to_layers(nodes):
        renderer = layer.renderer().clone()
        changed = False
        for symbol in renderer.symbols(render_context):
            if _apply_palette_color_to_symbol(symbol, color, use_fill, use_outline, use_pattern):
                changed = True
        if changed:
            layer.setRenderer(renderer)
            touched_layers[layer.id()] = layer

    for layer in touched_layers.values():
        layer.emitStyleChanged()

    _refresh_layers_and_restore_selection(iface_object, touched_layers, selected_legend_items)
    iface_object.mapCanvas().refreshAllLayers()
    return touched_layers


class SymbolColorDialog(QColorDialog):
    def __init__(self, iface_object, selected_nodes, selected_legend_nodes, parent=None):
        super().__init__(parent)
        self.iface_object = iface_object
        self.selected_nodes = list(selected_nodes)
        self.selected_legend_nodes = list(selected_legend_nodes)

        self.setWindowTitle("심볼 색상 지정")
        self.setOption(QColorDialog.DontUseNativeDialog, True)
        self.setOption(QColorDialog.ShowAlphaChannel, True)
        self.setCurrentColor(QColor(255, 0, 0, 255))
        self.setFont(QFont("Noto Sans KR", 9))
        self.setStyleSheet("""
            QColorDialog {
                background-color: rgb(255, 255, 255);
                color: rgb(13, 27, 61);
                font-family: "Noto Sans KR";
                font-size: 9pt;
            }
            QCheckBox, QLabel { color: rgb(13, 27, 61); }
            QPushButton {
                color: rgb(255, 255, 255);
                background-color: rgb(42, 120, 214);
                border: 1px solid rgb(42, 120, 214);
                border-radius: 5px;
                padding: 5px 12px;
            }
            QPushButton:hover { background-color: rgb(65, 140, 225); }
            QPushButton:pressed { background-color: rgb(13, 27, 61); }
        """)

        standard_rows = 6
        standard_columns = 8
        for palette_index, (color_name, rgb) in enumerate(SYMBOL_PALETTE_COLORS):
            row = palette_index // standard_columns
            column = palette_index % standard_columns
            color_index = column * standard_rows + row
            self.setStandardColor(
                color_index, QColor(rgb[0], rgb[1], rgb[2])
            )

        option_widget = QWidget(self)
        option_layout = QHBoxLayout(option_widget)
        option_layout.setContentsMargins(8, 4, 8, 4)
        option_layout.addWidget(QLabel("적용 대상", option_widget))

        self.check_fill = QCheckBox("채우기", option_widget)
        self.check_outline = QCheckBox("외곽선", option_widget)
        self.check_pattern = QCheckBox("패턴", option_widget)
        self.check_fill.setChecked(True)

        option_layout.addWidget(self.check_fill)
        option_layout.addWidget(self.check_outline)
        option_layout.addWidget(self.check_pattern)
        option_layout.addStretch(1)

        dialog_layout = self.layout()
        button_box = self.findChild(QDialogButtonBox)
        if button_box is not None:
            dialog_layout.removeWidget(button_box)
            button_box.setParent(option_widget)
            option_layout.addWidget(button_box)
        dialog_layout.addWidget(option_widget)

        noto_font = QFont("Noto Sans KR", 9)
        self.setFont(noto_font)
        for child_widget in self.findChildren(QWidget):
            child_widget.setFont(noto_font)

    def accept(self):
        if not any((
            self.check_fill.isChecked(),
            self.check_outline.isChecked(),
            self.check_pattern.isChecked(),
        )):
            QMessageBox.warning(self, "적용 대상", "채우기, 외곽선, 패턴 중 하나 이상을 선택해주세요.")
            return

        color = self.currentColor()
        if not color.isValid():
            QMessageBox.warning(self, "색상 확인", "적용할 색상을 선택해주세요.")
            return

        touched_layers = _apply_palette_color_to_selection(
            self.iface_object,
            color,
            self.check_fill.isChecked(),
            self.check_outline.isChecked(),
            self.check_pattern.isChecked(),
            self.selected_nodes,
            self.selected_legend_nodes,
        )
        if not touched_layers:
            QMessageBox.warning(self, "적용 실패", "선택한 대상에 적용할 수 있는 심볼이 없습니다.")
            return

        print(f"[OK] {len(touched_layers)}개 레이어의 심볼 색상이 변경되었습니다.")
        super().accept()

def open_symbol_color_dialog(iface_object, dock_widget):
    nodes, legend_nodes = _get_selection(iface_object)
    if not nodes and not legend_nodes:
        QMessageBox.warning(dock_widget, "선택 필요", "색상을 변경할 레이어 또는 분류 심볼을 선택해주세요.")
        return

    dialog = SymbolColorDialog(iface_object, nodes, legend_nodes, dock_widget)
    dock_widget._symbol_color_dialog = dialog
    dialog.show()
