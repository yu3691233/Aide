#!/bin/bash
# AideLink Git 提交前检查脚本
# 检查是否有未提交的修改，以及是否有冲突

echo "========================================"
echo "  AideLink 提交前检查"
echo "========================================"
echo ""

# 1. 检查是否有未提交的修改
echo "[1/3] 检查未提交的修改..."
if [ -n "$(git status --porcelain)" ]; then
    echo "  ⚠️  发现未提交的修改："
    git status --short
    echo ""
    echo "  请先提交或暂存这些修改后再继续。"
    exit 1
fi
echo "  ✅ 没有未提交的修改"
echo ""

# 2. 检查是否有冲突标记
echo "[2/3] 检查冲突标记..."
if grep -r "<<<<<<" --include="*.py" --include="*.kt" --include="*.java" . 2>/dev/null; then
    echo "  ❌ 发现冲突标记！"
    echo "  请先解决冲突后再提交。"
    exit 1
fi
echo "  ✅ 没有冲突标记"
echo ""

# 3. 检查语法（Python）
echo "[3/3] 检查 Python 语法..."
if command -v python &> /dev/null; then
    find server -name "*.py" -exec python -m py_compile {} \; 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "  ✅ Python 语法检查通过"
    else
        echo "  ❌ Python 语法错误！"
        exit 1
    fi
else
    echo "  ⚠️  Python 未安装，跳过语法检查"
fi

echo ""
echo "========================================"
echo "  检查通过，可以提交"
echo "========================================"
