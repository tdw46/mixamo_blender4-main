Get-ChildItem -Path . -Recurse -Force -ErrorAction SilentlyContinue -Filter "Desktop.ini" | Remove-Item -Force -ErrorAction SilentlyContinue
