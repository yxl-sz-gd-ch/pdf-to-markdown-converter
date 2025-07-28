# 测试 PDF 文件

## 📁 目录说明

本目录用于存放测试用的 PDF 文件。由于版权原因，我们不在项目中包含具体的 PDF 文件，请您自行添加测试文件。

## 🔍 推荐的测试文件类型

### 1. 学术论文
- **特点**：包含数学公式、图表、参考文献
- **来源建议**：
  - arXiv.org（开源学术论文）
  - 您自己的研究论文
  - 开放获取的期刊文章

### 2. 技术文档
- **特点**：包含代码块、截图、步骤说明
- **来源建议**：
  - 开源项目的文档
  - API 文档
  - 技术教程

### 3. 扫描文档
- **特点**：图片化的文本，需要 OCR 处理
- **来源建议**：
  - 扫描的书籍页面
  - 手写文档的扫描件
  - 老旧文档的数字化版本

### 4. 图文混排文档
- **特点**：大量图片和文字混合排版
- **来源建议**：
  - 产品手册
  - 宣传册
  - 报告文档

## 📝 测试文件命名建议

为了便于管理和测试，建议按以下方式命名您的测试文件：

```
academic_paper_sample.pdf          # 学术论文示例
technical_manual_sample.pdf        # 技术手册示例
scanned_document_sample.pdf        # 扫描文档示例
complex_layout_sample.pdf          # 复杂排版示例
math_heavy_sample.pdf              # 数学公式密集示例
image_rich_sample.pdf              # 图片丰富示例
```

## 🎯 测试建议

### 基础测试流程

1. **准备测试文件**
   ```bash
   # 将PDF文件复制到此目录
   cp /path/to/your/document.pdf examples/test_pdfs/
   ```

2. **运行程序测试**
   ```bash
   # 启动程序
   python main.py
   
   # 在程序中选择test_pdfs目录中的文件
   ```

3. **验证转换结果**
   - 检查生成的 Markdown 文件
   - 验证图片提取是否完整
   - 确认格式转换是否正确

### 不同配置测试

#### 测试学术论文
```
推荐配置：
✅ 启用 LLM
✅ 格式化行
✅ 备用图片提取
❌ 强制 OCR
```

#### 测试技术文档
```
推荐配置：
✅ 启用 LLM
✅ 备用图片提取
❌ 格式化行
❌ 强制 OCR
```

#### 测试扫描文档
```
推荐配置：
✅ 启用 LLM
✅ 强制 OCR
✅ 移除现有 OCR 文本
✅ 备用图片提取
```

## 📊 测试评估标准

### 转换质量评估

| 评估项目 | 优秀 | 良好 | 一般 | 需改进 |
|----------|------|------|------|--------|
| 文本识别准确率 | >95% | 90-95% | 80-90% | <80% |
| 格式保持度 | >90% | 80-90% | 70-80% | <70% |
| 图片提取完整性 | 100% | >90% | 80-90% | <80% |
| 表格转换效果 | 完美 | 良好 | 可用 | 需修正 |
| 公式显示效果 | 完美 | 良好 | 可用 | 需修正 |

### 性能评估

| 指标 | 优秀 | 良好 | 一般 | 需优化 |
|------|------|------|------|--------|
| 转换速度 | <1分钟/10页 | 1-2分钟/10页 | 2-5分钟/10页 | >5分钟/10页 |
| 内存使用 | <2GB | 2-4GB | 4-6GB | >6GB |
| 成功率 | 100% | >95% | 90-95% | <90% |

## 🔧 测试工具

### 文件大小检查
```bash
# 检查PDF文件大小
ls -lh examples/test_pdfs/*.pdf

# 推荐的文件大小范围
# 小文件: < 10MB
# 中等文件: 10-50MB  
# 大文件: > 50MB
```

### 页数统计
```python
# 使用Python检查PDF页数
import fitz  # PyMuPDF

def count_pages(pdf_path):
    doc = fitz.open(pdf_path)
    page_count = len(doc)
    doc.close()
    return page_count

# 使用示例
pages = count_pages("examples/test_pdfs/sample.pdf")
print(f"PDF页数: {pages}")
```

### 图片数量估算
```python
# 估算PDF中的图片数量
def estimate_images(pdf_path):
    doc = fitz.open(pdf_path)
    total_images = 0
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        images = page.get_images()
        total_images += len(images)
    
    doc.close()
    return total_images

# 使用示例
img_count = estimate_images("examples/test_pdfs/sample.pdf")
print(f"估计图片数量: {img_count}")
```

## 📋 测试记录模板

建议为每次测试创建记录：

```markdown
# 测试记录 - [日期]

## 测试文件信息
- 文件名: sample.pdf
- 文件大小: 15MB
- 页数: 25页
- 文档类型: 技术手册
- 预估图片数: 12张

## 配置信息
- 启用LLM: 是
- LLM服务: OpenAI GPT-4
- 备用图片提取: 是
- 强制OCR: 否
- 输出格式: Markdown

## 转换结果
- 转换时间: 3分钟15秒
- 内存峰值: 2.8GB
- 成功状态: 成功
- 输出文件: sample.md
- 图片文件夹: sample_images/ (包含14张图片)

## 质量评估
- 文本准确率: 92%
- 格式保持: 良好
- 图片完整性: 100%
- 表格效果: 良好
- 整体评分: 4.2/5.0

## 问题记录
- 第3页的复杂表格格式略有偏差
- 数学公式显示正常
- 代码块保持了原有格式

## 改进建议
- 可以尝试调整表格识别参数
- 整体效果满意，符合预期
```

## 🚀 快速测试脚本

您可以创建一个简单的测试脚本：

```bash
# test_conversion.bat (Windows)
@echo off
echo 开始PDF转换测试...
echo.

echo 检查测试文件...
dir examples\test_pdfs\*.pdf

echo.
echo 启动转换程序...
python main.py

echo.
echo 测试完成！
pause
```

```bash
# test_conversion.sh (Linux/Mac)
#!/bin/bash
echo "开始PDF转换测试..."
echo

echo "检查测试文件..."
ls -la examples/test_pdfs/*.pdf

echo
echo "启动转换程序..."
python main.py

echo
echo "测试完成！"
```

## 📞 获取帮助

如果您在测试过程中遇到问题：

1. **查看日志**：程序会显示详细的转换日志
2. **检查配置**：确认配置参数是否适合您的文档类型
3. **文件问题**：确认PDF文件没有损坏或加密
4. **提交Issue**：在GitHub上报告问题并附上测试文件信息

---

**注意**：请不要将受版权保护的PDF文件提交到公共代码仓库中。