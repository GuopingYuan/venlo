@echo off
chcp 65001 >nul
cd /d "C:\Users\lenovo\Desktop\Venlo5"

echo ===== Git Status =====
git status

echo.
echo ===== Adding files =====
git add -A

echo.
echo ===== Committing =====
git commit -m "feat: 全局消息弹窗改为屏幕中央弹窗 + Team Matching功能完整实现"

echo.
echo ===== Pushing to origin/master =====
git push origin master

echo.
echo ===== Done! Press any key to exit =====
pause
