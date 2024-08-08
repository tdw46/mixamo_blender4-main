import bpy

def get_data_bone(name):
    return bpy.context.active_object.data.bones.get(name)


def set_bone_collection(armt, databone, coll_name, multi=False):
    if databone is None:
        return

    armt_data = armt.data if hasattr(armt, 'data') else armt

    coll = armt_data.collections.get(coll_name)
    if coll is None:
        coll = armt_data.collections.new(coll_name)

    colls_to_remove_from = None
    if not multi:
        colls_to_remove_from = list(databone.collections)

    coll.assign(databone)

    if colls_to_remove_from is not None:
        for c in colls_to_remove_from:
            if c != coll:
                c.unassign(databone)

    return coll

    # ~ databone.layers[layer_idx] = True

    # ~ for i, lay in enumerate(databone.layers):
        # ~ if i != layer_idx:
            # ~ databone.layers[i] = False
