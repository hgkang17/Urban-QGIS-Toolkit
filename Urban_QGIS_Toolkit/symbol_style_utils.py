from qgis.core import QgsSimpleFillSymbolLayer


def build_symbol_from_style(symbol, raw_style, registry):
    layer_indices = set()
    for k in raw_style.keys():
        if k.startswith('layer_'):
            idx = k.split('_')[1]
            if idx.isdigit():
                layer_indices.add(int(idx))

    if not layer_indices:
        s_layer = QgsSimpleFillSymbolLayer.create(raw_style)
        symbol.appendSymbolLayer(s_layer)
        return

    for l_idx in sorted(list(layer_indices)):
        l_type = raw_style.get(f'layer_{l_idx}_type', 'SimpleFill')

        l_props = {}
        prefix = f'layer_{l_idx}_'
        for k, v in raw_style.items():
            if k.startswith(prefix) and not k.startswith(f'{prefix}sub_'):
                real_key = k[len(prefix):]
                l_props[real_key] = str(v)

        metadata = registry.symbolLayerMetadata(l_type)
        if not metadata:
            continue
        sym_layer = metadata.createSymbolLayer(l_props)

        sub_layer_indices = set()
        sub_prefix = f'layer_{l_idx}_sub_'
        for k in raw_style.keys():
            if k.startswith(sub_prefix):
                s_idx = k.split('_')[3]
                if s_idx.isdigit():
                    sub_layer_indices.add(int(s_idx))

        if sub_layer_indices and hasattr(sym_layer, 'subSymbol') and sym_layer.subSymbol() is not None:
            sub_sym = sym_layer.subSymbol()
            sub_sym.deleteSymbolLayer(0)

            for sl_idx in sorted(list(sub_layer_indices)):
                sl_type = raw_style.get(f'{sub_prefix}{sl_idx}_type', 'SimpleLine')

                sl_props = {}
                sl_real_prefix = f'{sub_prefix}{sl_idx}_'
                for k, v in raw_style.items():
                    if k.startswith(sl_real_prefix):
                        real_key = k[len(sl_real_prefix):]
                        sl_props[real_key] = str(v)

                sl_metadata = registry.symbolLayerMetadata(sl_type)
                if sl_metadata:
                    sub_sym_layer = sl_metadata.createSymbolLayer(sl_props)
                    sub_sym.appendSymbolLayer(sub_sym_layer)

        symbol.appendSymbolLayer(sym_layer)
