# 更新日志

本文档记录了 PDF to Markdown Converter 项目的所有重要更改。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 计划添加
- [ ] 支持更多输出格式（Word、LaTeX）
- [ ] 添加命令行界面
- [ ] 支持批量配置模板
- [ ] 添加转换质量评分
- [ ] 支持云端模型服务

## [1.0.0] - 2025-01-29

### 新增功能
- ✨ 基于 Marker 的智能 PDF 转 Markdown 功能
- ✨ 双引擎图片提取架构（Marker + PyMuPDF）
- ✨ 图形化用户界面（基于 PyQt5）
- ✨ 多种 LLM 服务集成（OpenAI、Claude、Gemini、Ollama）
- ✨ 本地 LLM 支持（LM Studio 兼容）
- ✨ 智能图片插入和链接更新
- ✨ 批量文件处理能力
- ✨ 实时转换进度显示
- ✨ 详细的日志记录系统
- ✨ 用户配置持久化
- ✨ 多种输出格式支持（Markdown、JSON、HTML、Chunks）

### 核心特性
- 🎯 **双引擎图片提取**：主引擎智能识别 + 备用引擎全量提取
- 🤖 **AI 增强转换**：支持多种 LLM 服务提高转换质量
- 📊 **智能图片处理**：自动匹配、插入和补充图片
- 🚀 **批量处理**：支持文件夹批量转换
- ⚙️ **丰富配置**：页面范围、OCR 选项、格式化等
- 📝 **多格式输出**：适应不同使用场景

### 技术实现
- 基于 Marker 1.8.2 的 PDF 解析引擎
- PyMuPDF 作为备用图片提取引擎
- PyQt5 构建的现代化图形界面
- 多线程处理确保界面响应性
- 智能图片链接匹配算法
- 完善的错误处理和日志系统

### 支持的功能
- **文档类型**：学术论文、技术手册、扫描文档、图文混排文档
- **LLM 服务**：OpenAI、Claude、Gemini、Ollama、Azure OpenAI
- **输出格式**：Markdown、JSON、HTML、Chunks
- **图片格式**：JPEG、PNG、GIF、BMP 等常见格式
- **特殊处理**：数学公式、表格、代码块、列表

### 系统要求
- **操作系统**：Windows 10/11
- **Python**：3.8 或更高版本
- **内存**：建议 8GB 以上
- **存储**：至少 5GB（用于模型缓存）

### 已知限制
- 当前仅支持 Windows 平台
- 大文件（>100MB）处理可能较慢
- 某些复杂表格可能需要手动调整
- 加密 PDF 需要先解密

## [0.9.0] - 2025-01-28 (内部测试版)

### 新增
- 基础的 PDF 转 Markdown 功能
- 简单的图片提取
- 基本的用户界面

### 修复
- 修复了图片链接错误的问题
- 解决了缩进导致的语法错误
- 改进了错误处理机制

### 变更
- 重构了图片处理逻辑
- 优化了用户界面布局
- 改进了日志显示

---

## 版本说明

### 版本号规则
- **主版本号**：不兼容的 API 修改
- **次版本号**：向下兼容的功能性新增
- **修订号**：向下兼容的问题修正

### 更新类型
- **新增 (Added)**：新功能
- **变更 (Changed)**：对现有功能的变更
- **弃用 (Deprecated)**：不久将移除的功能
- **移除 (Removed)**：已移除的功能
- **修复 (Fixed)**：任何 bug 修复
- **安全 (Security)**：安全相关的修复

### 获取更新
- 关注 [GitHub Releases](https://github.com/yxl-sz-gd-ch/pdf-to-markdown-converter/releases)
- 查看 [项目主页](https://github.com/yxl-sz-gd-ch/pdf-to-markdown-converter) 获取最新信息