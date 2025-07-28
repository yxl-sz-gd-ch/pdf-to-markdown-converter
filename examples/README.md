# 示例文件

本目录包含了 PDF to Markdown Converter 的使用示例和测试文件。

## 📁 目录结构

```
examples/
├── README.md                    # 本文件
├── sample_configs/              # 配置示例
│   ├── academic_paper.json     # 学术论文配置
│   ├── technical_manual.json   # 技术手册配置
│   └── scanned_document.json   # 扫描文档配置
├── sample_outputs/              # 输出示例
│   ├── academic_paper.md       # 学术论文转换结果
│   ├── technical_manual.md     # 技术手册转换结果
│   └── scanned_document.md     # 扫描文档转换结果
└── test_pdfs/                   # 测试PDF文件（需要用户自行添加）
    ├── README.md               # 测试文件说明
    └── .gitkeep                # 保持目录结构
```

## 🎯 使用说明

### 1. 配置示例

#### 学术论文配置 (academic_paper.json)
适用于包含大量公式、图表和参考文献的学术论文。

#### 技术手册配置 (technical_manual.json)
适用于技术文档、用户手册等结构化文档。

#### 扫描文档配置 (scanned_document.json)
适用于扫描的PDF文档，需要OCR处理。

### 2. 输出示例

每个输出示例都展示了不同类型文档的转换效果：
- Markdown格式规范
- 图片链接处理
- 表格转换效果
- 公式显示方式

### 3. 测试文件

由于版权原因，本项目不包含测试PDF文件。您可以：
- 将自己的PDF文件放入 `test_pdfs/` 目录
- 使用开源的PDF文档进行测试
- 创建简单的测试PDF文件

## 🚀 快速测试

1. **准备测试文件**
   ```bash
   # 将您的PDF文件复制到test_pdfs目录
   cp your_document.pdf examples/test_pdfs/
   ```

2. **使用示例配置**
   - 根据文档类型选择合适的配置文件
   - 在程序中导入配置（如果支持）
   - 或手动设置相应的参数

3. **运行转换**
   ```bash
   # 启动程序
   python main.py
   
   # 选择test_pdfs中的文件进行转换
   # 参考sample_configs中的配置
   ```

4. **对比结果**
   - 将转换结果与sample_outputs中的示例对比
   - 检查转换质量和格式

## 📊 性能基准

以下是不同类型文档的转换性能参考：

| 文档类型 | 页数 | 图片数 | 转换时间 | 内存使用 |
|---------|------|--------|----------|----------|
| 学术论文 | 10页 | 5张 | ~2分钟 | ~2GB |
| 技术手册 | 50页 | 20张 | ~8分钟 | ~4GB |
| 扫描文档 | 20页 | 0张 | ~5分钟 | ~3GB |

*注：性能数据基于Intel i7-8700K, 16GB RAM的测试环境*

## 🔧 自定义示例

您可以创建自己的示例配置：

1. **复制现有配置**
   ```bash
   cp sample_configs/academic_paper.json sample_configs/my_config.json
   ```

2. **修改参数**
   ```json
   {
     "output_format": "markdown",
     "use_llm": true,
     "llm_service": "OpenAI",
     "force_ocr": false,
     "fallback_extraction": true
   }
   ```

3. **测试配置**
   - 使用新配置转换测试文档
   - 评估转换效果
   - 调整参数优化结果

## 📝 贡献示例

如果您有好的示例想要分享：

1. **准备示例文件**
   - 确保PDF文件无版权问题
   - 提供高质量的转换结果
   - 包含详细的配置说明

2. **提交Pull Request**
   - Fork项目
   - 添加示例文件
   - 更新README说明
   - 提交PR

## ❓ 常见问题

**Q: 为什么没有提供测试PDF文件？**
A: 出于版权考虑，我们不提供PDF文件。请使用您自己的文档或开源文档进行测试。

**Q: 如何创建测试PDF？**
A: 您可以：
- 使用Word等软件创建包含文字、图片、表格的文档并导出为PDF
- 下载开源的学术论文或技术文档
- 使用在线PDF生成工具

**Q: 示例配置如何使用？**
A: 目前需要手动在程序界面中设置相应参数。未来版本将支持配置文件导入功能。

## 🔗 相关链接

- [项目主页](https://github.com/yxl-sz-gd-ch/pdf-to-markdown-converter)
- [使用教程](../教程.md)
- [问题反馈](https://github.com/yxl-sz-gd-ch/pdf-to-markdown-converter/issues)