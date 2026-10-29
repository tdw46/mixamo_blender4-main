"""Run with Blender --background --factory-startup --python-exit-code 1.

Use disposable BLENDER_USER_CONFIG/SCRIPTS/EXTENSIONS directories.
"""

import importlib
import sys
from pathlib import Path

import addon_utils
import bpy

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root.parent))
addon_utils.enable(root.name, default_set=True)
functions = importlib.import_module(root.name + ".mixamo_rig_functions")
data = bpy.data.armatures.new("Issue6")
rig = bpy.data.objects.new("Issue6", data)
bpy.context.collection.objects.link(rig)
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")


def bone(name, head, tail, parent=None):
    b = data.edit_bones.new(name)
    b.head, b.tail = head, tail
    if parent:
        b.parent = data.edit_bones[parent]


bone("Hips", (0, 0, 1), (0, 0, 1.1))
for i, name in enumerate(["Spine", "Spine1", "Spine2", "Neck", "Head", "HeadTop_End"]):
    bone(
        name,
        (0, 0, 1.1 + i * 0.1),
        (0, 0, 1.2 + i * 0.1),
        ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"][i],
    )
for side, sign in [("Left", 1), ("Right", -1)]:
    bone(side + "Shoulder", (0, 0, 1.4), (sign * 0.2, 0, 1.4), "Spine2")
    bone(
        side + "Arm", (sign * 0.2, 0, 1.4), (sign * 0.5, -0.05, 1.4), side + "Shoulder"
    )
    bone(side + "ForeArm", (sign * 0.5, -0.05, 1.4), (sign * 0.8, 0, 1.4), side + "Arm")
    bone(side + "Hand", (sign * 0.8, 0, 1.4), (sign * 0.9, 0, 1.4), side + "ForeArm")
bpy.ops.object.mode_set(mode="OBJECT")
for pb in rig.pose.bones:
    pb.rotation_mode = "XYZ"
    for frame in (0, 10):
        pb.keyframe_insert(data_path="location", frame=frame)
        pb.keyframe_insert(data_path="rotation_euler", frame=frame)
assert bpy.ops.mr.make_rig(bake_anim=True) == {"FINISHED"}
bpy.ops.object.mode_set(mode="POSE")
scene = bpy.context.scene
hips = rig.pose.bones["Ctrl_Hips"]
hips.location.y = 0.2
hips.rotation_euler.z = 0.4
hips.keyframe_insert(data_path="location", frame=1)
hips.keyframe_insert(data_path="rotation_euler", frame=1)
bpy.context.preferences.edit.use_visual_keying = True
assert functions.uses_visual_keying(bpy.context)

for side in ("Left", "Right"):
    for kind in ("Hand", "ArmPole"):
        pb = rig.pose.bones[f"Ctrl_{kind}_IK_{side}"]
        scene.frame_set(1)
        bpy.ops.pose.select_all(action="DESELECT")
        if hasattr(pb, "select"):
            pb.select = True
        else:
            pb.bone.select = True
        data.bones.active = pb.bone
        scene.tool_settings.use_keyframe_insert_auto = False
        bpy.ops.transform.translate(value=(0, 0.3, 0))
        bpy.context.view_layer.update()
        desired = pb.location.copy()
        # Evaluate first, as in a viewport modal transform, then visual-key.
        pb.keyframe_insert(data_path="location", frame=1, options={"INSERTKEY_VISUAL"})
        scene.frame_set(5)
        scene.frame_set(1)
        error = (pb.location - desired).length
        assert (error > 0.1) if kind == "ArmPole" else (error < 1e-5), (pb.name, error)
        print("REPRODUCED", pb.name, error)

# Check explicit visual keying sets as well as the global preference.
sets = scene.keying_sets_all
sets.active = next(ks for ks in sets if ks.bl_idname == "BUILTIN_KSI_VisualLocRot")
scene.tool_settings.use_keyframe_insert_auto = True
assert bpy.ops.pose.mr_use_local_keying() == {"FINISHED"}
assert not functions.uses_visual_keying(bpy.context)
assert scene.tool_settings.use_keyframe_insert_auto
for side in ("Left", "Right"):
    for kind in ("Hand", "ArmPole"):
        pb = rig.pose.bones[f"Ctrl_{kind}_IK_{side}"]
        bpy.ops.pose.select_all(action="DESELECT")
        if hasattr(pb, "select"):
            pb.select = True
        else:
            pb.bone.select = True
        data.bones.active = pb.bone
        scene.frame_set(1)
        bpy.ops.transform.translate(value=(0.15, 0.3, 0.1))
        bpy.context.view_layer.update()
        desired = pb.matrix.copy()
        scene.frame_set(5)
        scene.frame_set(1)
        error = max(
            abs(a - b)
            for row_a, row_b in zip(pb.matrix, desired)
            for a, b in zip(row_a, row_b)
        )
        assert error < 1e-5, (pb.name, error)
        print("AUTO_KEY_PASS", pb.name, error)
print("ISSUE6_PASS", bpy.app.version_string)

if not bpy.app.background:
    # Native popup smoke test in a disposable windowed Blender process.
    # No screenshots or visual judgments; verify dispatch and suppression state.
    def start_popup_test():
        functions.reset_keying_warnings(None)
        bpy.context.preferences.edit.use_visual_keying = True
        functions.auto_snap_ik_fk_slider_handler(
            scene, bpy.context.evaluated_depsgraph_get()
        )
        assert bpy.app.timers.is_registered(functions.show_keying_warning)
        bpy.app.timers.register(finish_popup_test, first_interval=1.0)

    def finish_popup_test():
        try:
            key = (scene.as_pointer(), rig.as_pointer())
            assert key in functions._keying_warning_seen
            functions.queue_keying_warning(bpy.context)
            assert not bpy.app.timers.is_registered(functions.show_keying_warning)
            assert bpy.ops.pose.mr_use_local_keying() == {"FINISHED"}
            assert not functions._keying_warning_seen
            assert not functions.uses_visual_keying(bpy.context)
            # A file load/unregister must cancel pending callbacks as well.
            bpy.app.timers.register(functions.show_keying_warning, first_interval=10)
            functions.reset_keying_warnings(None)
            assert not bpy.app.timers.is_registered(functions.show_keying_warning)
            print("POPUP_PASS", bpy.app.version_string, flush=True)
        except BaseException:
            import traceback

            traceback.print_exc()
            sys.stdout.flush()
            import os

            os._exit(1)
        bpy.ops.wm.quit_blender()

    bpy.app.timers.register(start_popup_test, first_interval=1.0)
