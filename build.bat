@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] 生成图标 app.ico ...
python make_icon.py || goto :err
echo [2/3] PyInstaller 打包（--onefile --noconsole，64 位单文件）...
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name "HashTool" --icon "%~dp0app.ico" --distpath dist --workpath build --specpath build main.py || goto :err
echo [3/3] 完成：dist\HashTool.exe
pause
exit /b 0
:err
echo 打包失败，请检查上方错误信息（需先安装：python -m pip install pyinstaller）。
pause
exit /b 1
