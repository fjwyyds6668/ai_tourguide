# Prisma 生成脚本 - 解决 Windows 编码问题
# 设置 UTF-8 编码环境变量
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# 切换到 UTF-8 代码页
chcp 65001 | Out-Null

# 清理旧的生成文件（如果存在）
if (Test-Path "prisma\__pycache__") {
    Remove-Item -Recurse -Force "prisma\__pycache__"
}

# 生成 Prisma 客户端
Write-Host "正在生成 Prisma 客户端..." -ForegroundColor Green
prisma generate

if ($LASTEXITCODE -eq 0) {
    Write-Host "Prisma 客户端生成成功！" -ForegroundColor Green
} else {
    Write-Host "Prisma 客户端生成失败，错误代码: $LASTEXITCODE" -ForegroundColor Red
}

