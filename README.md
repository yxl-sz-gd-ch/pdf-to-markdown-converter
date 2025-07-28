# PDF to Markdown Converter

<div align="center">

![Python](https://img.shields.io/badge/python-v3.8+-blue.svg)
![PyQt5](https://img.shields.io/badge/PyQt5-5.15+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

**一个基于 Marker 和 PyMuPDF 的智能 PDF 转 Markdown 工具**

[功能特性](#功能特性) • [安装指南](#安装指南) • [使用教程](#使用教程) • [配置说明](#配置说明) • [常见问题](#常见问题)

</div>

## 📖 项目简介

PDF to Markdown Converter 是一个功能强大的桌面应用程序，专门用于将 PDF 文档转换为高质量的 Markdown 格式。该工具采用双引擎架构，结合了 Marker 的智能文档理解能力和 PyMuPDF 的全面图片提取功能，确保转换结果的完整性和准确性。

## ✨ 功能特性

### 🚀 核心功能
- **批量转换**：支持单个文件或整个文件夹的批量处理
- **双引擎架构**：Marker 主引擎 + PyMuPDF 备用引擎，确保图片提取完整性
- **智能图片处理**：自动提取、保存图片并生成正确的 Markdown 链接
- **多种输出格式**：支持 Markdown、JSON、HTML、Chunks 等格式
- **实时进度显示**：详细的转换进度和日志信息

### 🤖 AI 增强功能
- **LLM 集成**：支持 OpenAI、Ollama、Gemini、Claude、Azure OpenAI
- **本地 LLM 支持**：兼容 LM Studio 等本地 API 服务
- **智能文档理解**：利用 AI 提高复杂文档的转换准确性

### 🎯 高级特性
- **智能图片插入**：自动将提取的图片插入到文档的合适位置
- **页面范围控制**：支持指定转换特定页面范围
- **OCR 选项**：强制 OCR 和现有 OCR 文本处理
- **自定义配置**：丰富的参数配置选项
- **设置持久化**：自动保存和恢复用户配置

## 🛠 技术架构

### 双引擎图片提取策略
1. **主引擎 (Marker)**：智能识别文档结构和图片位置
2. **备用引擎 (PyMuPDF)**：全量提取 PDF 中的所有图片
3. **智能合并**：自动匹配和补充遗漏的图片

### 支持的文档类型
- 学术论文和研究报告
- 技术文档和手册
- 图文并茂的演示文稿
- 扫描文档（通过 OCR）
- 复杂排版的 PDF 文件

## 📦 安装指南

### 系统要求
- **操作系统**：Windows 10/11
- **Python**：3.8 或更高版本（开发环境python3.10.11）
- **内存**：建议 8GB 以上
- **存储空间**：至少 5GB（用于模型缓存）

### 快速安装

1. **克隆项目**
```bash
git clone https://github.com/yxl-sz-gd-ch/.git
cd pdf-to-markdown-converter
```

2. **创建虚拟环境**
```bash
python -m venv env310
env310\Scripts\activate
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **运行程序**
```bash
python main.py
```

### 依赖说明

#### 核心依赖
- `marker-pdf[full]` - 主要的 PDF 转换引擎
- `PyMuPDF` - 备用图片提取引擎
- `PyQt5` - 图形用户界面框架

#### AI 服务依赖
- `openai` - OpenAI API 支持
- `anthropic` - Claude API 支持
- `google-genai` - Gemini API 支持

## 🚀 快速开始

### 基础使用流程

1. **启动程序**
   ```bash
   python main.py
   ```

2. **选择 PDF 文件**
   - 点击"选择 PDF 文件"按钮选择单个文件
   - 或点击"选择包含 PDF 的文件夹"进行批量处理

3. **配置输出目录**
   - 在"基础设置"选项卡中设置输出目录

4. **开始转换**
   - 点击"🚀 开始转换"按钮
   - 在日志窗口中查看转换进度

### 高级配置

#### LLM 设置
1. 在"LLM 设置"选项卡中启用"使用 LLM 提高准确性"
2. 选择 LLM 服务提供商
3. 配置 API 密钥和模型参数

#### 高级选项
- **输出格式**：选择 Markdown、JSON 等格式
- **页面范围**：指定转换的页面范围
- **OCR 选项**：配置 OCR 相关设置
- **备用图片提取**：启用 PyMuPDF 备用引擎

## 📋 使用示例

### 示例 1：基础转换
```
输入：document.pdf
输出：
├── document.md
└── document_images/
    ├── _page_1_fallback_img_1.jpeg
    ├── _page_2_fallback_img_1.png
    └── ...
```

### 示例 2：批量转换
```
输入文件夹：/path/to/pdfs/
输出：
├── doc1.md
├── doc1_images/
├── doc2.md
├── doc2_images/
└── ...
```

## ⚙️ 配置说明

### 基础配置
- `output_format`: 输出格式 (markdown/json/html/chunks)
- `page_range`: 页面范围 (例如: "1,3-5,10")
- `format_lines`: 格式化行，改善数学公式显示
- `force_ocr`: 强制使用 OCR
- `strip_existing_ocr`: 移除现有 OCR 文本

### LLM 配置
- `llm_service`: LLM 服务类型
- `api_key`: API 密钥
- `base_url`: API 基础 URL
- `model`: 模型名称

### 高级配置
- `debug`: 启用调试模式
- `workers`: 工作进程数
- `fallback_extraction`: 启用备用图片提取

## 🔧 故障排除

### 常见问题

**Q: 程序启动时提示缺少依赖？**
A: 请确保已安装所有必需的依赖包：
```bash
pip install -r requirements.txt
```

**Q: 转换时出现内存不足错误？**
A: 建议：
- 关闭其他占用内存的程序
- 减少并发处理的文件数量
- 考虑升级系统内存

**Q: 图片没有正确显示在 Markdown 中？**
A: 检查：
- 确保启用了"备用图片提取"选项
- 验证图片文件夹是否正确生成
- 检查 Markdown 中的图片链接路径

**Q: LLM 服务连接失败？**
A: 验证：
- API 密钥是否正确
- 网络连接是否正常
- Base URL 配置是否正确

### 日志分析

程序提供详细的日志信息，包括：
- 模型加载状态
- 文件转换进度
- 图片提取结果
- 错误和警告信息

## 🤝 贡献指南

我们欢迎社区贡献！请遵循以下步骤：

1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

### 开发环境设置

```bash
# 克隆项目
git clone https://github.com/yxl-sz-gd-ch/pdf-to-markdown-converter.git
cd pdf-to-markdown-converter

# 安装开发依赖
pip install -r requirements.txt

# 运行测试
python -m pytest tests/
```

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [Marker](https://github.com/VikParuchuri/marker) - 优秀的 PDF 转换引擎
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) - 强大的 PDF 处理库
- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) - 跨平台 GUI 框架

## 📞 联系方式

- **项目主页**：[GitHub Repository](https://github.com/yxl-sz-gd-ch/pdf-to-markdown-converter)
- **问题反馈**：[Issues](https://github.com/yxl-sz-gd-ch/pdf-to-markdown-converter/issues)
- **功能建议**：[Discussions](https://github.com/yxl-sz-gd-ch/pdf-to-markdown-converter/discussions)

---

<div align="center">

**如果这个项目对您有帮助，请给我们一个 ⭐ Star！**

</div>