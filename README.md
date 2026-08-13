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
