"""
Animation Compatibility Layer for Blender 4.4+ Slotted Actions
Provides backward-compatible access to animation data for both:
- Legacy Actions (Blender < 4.4)
- Slotted Actions (Blender 4.4+)
"""

import bpy


def has_slotted_actions():
    """Check if Blender supports slotted actions (4.4+)"""
    return bpy.app.version >= (4, 4, 0)


def get_action_fcurves(action, slot=None):
    """
    Get F-Curves from an action, compatible with legacy, slotted, and layered actions.

    IMPORTANT: Call this ONCE and store the result if you need to use it multiple times
    in a loop. Repeated calls can cause dependency graph issues in Blender 4.4+.

    Args:
        action: bpy.types.Action
        slot: Optional slot for Blender 5.0+ layered actions. If None, uses first slot.

    Returns:
        Collection of F-Curves (or empty list if none exist)

    Example:
        # GOOD - call once, use many times
        fcurves = get_action_fcurves(action)
        for fc in fcurves:
            print(fc.data_path)

        # BAD - repeated calls in loop
        for i in range(3):
            fcurves = get_action_fcurves(action)  # DON'T DO THIS
    """
    if action is None:
        return []

    # Blender 5.0+: action.fcurves is removed, use layered action API
    if bpy.app.version >= (5, 0, 0):
        # Use the new layered action system
        if hasattr(action, "layers") and len(action.layers) > 0:
            layer = action.layers[0]
            if hasattr(layer, "strips") and len(layer.strips) > 0:
                strip = layer.strips[0]
                if hasattr(strip, "channelbag"):
                    # Get the slot to use
                    if slot is None:
                        if hasattr(action, "slots") and len(action.slots) > 0:
                            slot = action.slots[0]
                    if slot is not None:
                        try:
                            channelbag = strip.channelbag(slot)
                            cbag_has_fc = hasattr(channelbag, "fcurves")
                            if channelbag is not None and cbag_has_fc:
                                return channelbag.fcurves
                        except Exception:
                            pass
        return []

    # Blender 4.4+: action.fcurves is a proxy for the layered system
    # Blender < 4.4: action.fcurves is the direct access
    if hasattr(action, "fcurves"):
        return action.fcurves

    return []


def get_action_frame_range(action):
    """
    Get frame range from an action.

    Args:
        action: bpy.types.Action

    Returns:
        tuple: (frame_start, frame_end) or None if no action
    """
    if action is None:
        return None

    # frame_range works the same in both versions
    return action.frame_range


def get_action_from_animdata(anim_data):
    """
    Get the active action from animation data.

    Args:
        anim_data: bpy.types.AnimData or None

    Returns:
        bpy.types.Action or None
    """
    if anim_data is None:
        return None

    return anim_data.action


def get_action_from_nla_strip(nla_strip):
    """
    Get action from an NLA strip.

    Args:
        nla_strip: bpy.types.NlaStrip

    Returns:
        bpy.types.Action or None
    """
    if nla_strip is None:
        return None

    return nla_strip.action


def assign_action_to_animdata(anim_data, action, target_datablock=None):
    """
    Assign an action to animation data, handling slot assignment for 4.4+.

    Args:
        anim_data: bpy.types.AnimData
        action: bpy.types.Action
        target_datablock: The data-block being animated (slot assign)  # noqa: E501

    Returns:
        bool: True if successful
    """
    if anim_data is None or action is None:
        return False

    # Assign the action (works in all versions)
    anim_data.action = action

    # Blender 4.4+: explicitly assign an Action Slot if auto-assignment didn't happen
    if has_slotted_actions():
        # Official pattern: use anim_data.action_slot and action_suitable_slots
        if hasattr(anim_data, "action_slot"):
            try:
                if anim_data.action_slot is None:
                    suitable = getattr(anim_data, "action_suitable_slots", None)
                    if suitable and len(suitable) > 0:
                        # Direct assignment of the slot object
                        anim_data.action_slot = suitable[0]
                    else:
                        # Fallback: ensure a slot by creating/ensuring an FCurve for this datablock  # noqa: E501
                        # This API will also create the layer/strip/slot and assign it as needed  # noqa: E501
                        if target_datablock is not None and hasattr(
                            action, "fcurve_ensure_for_datablock"
                        ):
                            try:
                                # Use a representative data path for the datablock type
                                data_path = "location"
                                if (
                                    hasattr(target_datablock, "pose")
                                    and hasattr(target_datablock.pose, "bones")
                                    and len(target_datablock.pose.bones) > 0
                                ):
                                    first_bone_name = target_datablock.pose.bones[
                                        0
                                    ].name
                                    data_path = f'pose.bones["{first_bone_name}"].rotation_euler'  # noqa: E501
                                action.fcurve_ensure_for_datablock(
                                    target_datablock, data_path, index=0
                                )
                            except Exception:
                                pass
            except Exception:
                pass

    return True


def copy_action_with_slots(src_action):
    """
    Create a copy of an action, preserving slots in 4.4+.

    Args:
        src_action: bpy.types.Action to copy

    Returns:
        bpy.types.Action: The copied action
    """
    if src_action is None:
        return None

    # Use Blender's built-in copy
    new_action = src_action.copy()

    return new_action


def get_or_create_action_for_datablock(datablock, action_name=None):
    """
    Get existing action or create a new one for a data-block.
    Handles slot creation in 4.4+.

    Args:
        datablock: The data-block to animate (e.g., Object, Armature)
        action_name: Optional name for the action

    Returns:
        bpy.types.Action: The action
    """
    if datablock is None:
        return None

    # Create animation data if it doesn't exist
    if datablock.animation_data is None:
        datablock.animation_data_create()

    anim_data = datablock.animation_data

    # Return existing action if present
    if anim_data.action:
        return anim_data.action

    # Create new action
    if action_name is None:
        action_name = f"{datablock.name}Action"

    action = bpy.data.actions.new(action_name)

    # Assign it (this handles slot creation in 4.4+)
    assign_action_to_animdata(anim_data, action, datablock)

    return action


def duplicate_action_assignment(src_anim_data, dst_anim_data):
    """
    Copy action assignment from one AnimData to another, including slot in 4.4+.

    Args:
        src_anim_data: Source AnimData
        dst_anim_data: Destination AnimData

    Returns:
        bool: True if successful
    """
    if src_anim_data is None or dst_anim_data is None:
        return False

    if src_anim_data.action is None:
        return False

    dst_anim_data.action = src_anim_data.action

    # In 4.4+, also copy the slot assignment
    if has_slotted_actions():
        if hasattr(src_anim_data, "action_slot") and hasattr(
            dst_anim_data, "action_slot"
        ):
            try:
                if src_anim_data.action_slot is not None:
                    dst_anim_data.action_slot = src_anim_data.action_slot
            except Exception:
                pass

    return True


def ensure_fcurve_exists(action, datablock, data_path, index=0):
    """
    Ensure an F-Curve exists on an action for a specific data-block property.
    Compatible with legacy, slotted, and layered actions.

    Args:
        action: bpy.types.Action
        datablock: The data-block being animated
        data_path: Property data path (e.g., "location")
        index: Array index for the property

    Returns:
        bpy.types.FCurve or None
    """
    if action is None:
        return None

    # In 4.4+, use the convenience function if available
    if has_slotted_actions() and hasattr(action, "fcurve_ensure_for_datablock"):
        try:
            return action.fcurve_ensure_for_datablock(datablock, data_path, index=index)
        except Exception:
            pass

    # Blender 5.0+: action.fcurves is removed, use layered action API
    if bpy.app.version >= (5, 0, 0):
        # Get fcurves collection from layered action
        fcurves = get_action_fcurves(action)
        if fcurves:
            # Try to find existing fcurve
            for fc in fcurves:
                if fc.data_path == data_path and fc.array_index == index:
                    return fc
            # Create new fcurve if collection supports it
            if hasattr(fcurves, "new"):
                try:
                    return fcurves.new(data_path, index=index)
                except Exception:
                    pass
        return None

    # Fallback to legacy API (Blender < 5.0)
    if hasattr(action, "fcurves"):
        fcurve = action.fcurves.find(data_path, index=index)
        if fcurve is None:
            fcurve = action.fcurves.new(data_path, index=index)
        return fcurve

    return None


def print_action_info(action, verbose=False):
    """
    Debug helper: Print information about an action.

    Args:
        action: bpy.types.Action
        verbose: Print detailed information
    """
    if action is None:
        print("Action: None")
        return

    print(f"Action: {action.name}")
    print(f"  Frame range: {action.frame_range}")

    if has_slotted_actions() and hasattr(action, "slots"):
        print(f"  Slots: {len(action.slots)}")
        if verbose:
            for slot in action.slots:
                print(
                    f"    - {slot.identifier} ({slot.target_id_type}): {slot.name_display}"  # noqa: E501
                )

    fcurves = get_action_fcurves(action)
    print(f"  F-Curves: {len(fcurves)}")

    if verbose:
        for fc in fcurves:
            print(
                f"    - {fc.data_path}[{fc.array_index}]: {len(fc.keyframe_points)} keys"  # noqa: E501
            )
