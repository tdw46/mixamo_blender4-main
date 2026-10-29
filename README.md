Based on: https://www.adobe.com/products/substance3d/plugins/mixamo-in-blender.html

Download the version from that link for Blender versions older than 4.0

## Installation troubleshooting

If Blender reports `acquire(): cookie doesn't exist! (when it should)` while
using **Install from Disk**, the extension has not been parsed or imported yet.
Blender's extension manager cannot find its current session temporary directory.

1. Close every Blender window, reopen Blender, and try the installation again.
2. If the error returns, open Blender's Python Console and run:

   ```python
   import bpy, os
   print(bpy.app.tempdir, os.path.isdir(bpy.app.tempdir))
   ```

3. If the command prints `False`, make sure the temporary-files directory set
   in Blender Preferences exists and is writable. Also check that the Windows
   `TEMP` and `TMP` locations exist and are writable, then restart Blender.

Running Blender as Administrator is not required and can create avoidable
permission differences between elevated and normal sessions.

## IK poles reverting after keying

With **Visual Keying** enabled, Blender can record the evaluated position of an
IK pole, including its Child Of constraint, into its local location channels.
When the frame is evaluated again, the constraint is applied again and the pole
shifts. Hand controls can appear unaffected while their master is at rest.

The Mixamo Rig Settings panel now warns about Visual Keying. Click **Use Local
Transform Keying** to disable that animation preference and select the ordinary
Location & Rotation keying set. This changes keying settings throughout Blender;
it does not change Auto Keying's enabled state or rewrite existing animation.
Reposition and re-key any poses already recorded with incorrect values.

A warning popup also appears when you enter Pose Mode or interact with a Mixamo
rig while Visual Keying is enabled. Click **Fix Keying Settings** to apply the
same correction, or dismiss the popup to keep your settings. It appears once per
rig until Visual Keying is turned off and back on, or a file is loaded. The panel
warning remains available after dismissal. Playback and active modal operations
do not open the popup.

If the problem continues with Visual Keying off, include a minimal `.blend`
file and your auto-key settings in the bug report so that case can be reproduced.
