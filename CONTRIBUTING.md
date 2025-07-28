# 贡献指南

感谢您对 PDF to Markdown Converter 项目的关注！我们欢迎各种形式的贡献，包括但不限于：

- 🐛 报告 Bug
- 💡 提出新功能建议
- 📝 改进文档
- 🔧 提交代码修复
- 🌟 分享使用经验

## 📋 目录

1. [开发环境设置](#开发环境设置)
2. [提交 Issue](#提交-issue)
3. [提交 Pull Request](#提交-pull-request)
4. [代码规范](#代码规范)
5. [测试指南](#测试指南)
6. [文档贡献](#文档贡献)

## 🔧 开发环境设置

### 前置要求

- Python 3.8 或更高版本
- Git
- Windows 10/11（当前主要支持平台）

### 环境搭建

1. **Fork 并克隆项目**
   ```bash
   git clone https://github.com/YOUR_USERNAME/pdf-to-markdown-converter.git
   cd pdf-to-markdown-converter
   ```

2. **创建虚拟环境**
   ```bash
   python -m venv env310
   env310\Scripts\activate  # Windows
   # source env310/bin/activate  # Linux/Mac
   ```

3. **安装依赖**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   
   # 安装开发依赖
   pip install pytest pytest-cov flake8 black isort
   ```

4. **验证安装**
   ```bash
   python main.py
   ```

### 开发工具推荐

- **IDE**: VS Code, PyCharm
- **代码格式化**: Black
- **导入排序**: isort
- **代码检查**: flake8
- **测试框架**: pytest

## 🐛 提交 Issue

### Bug 报告

使用 Bug 报告模板，请包含以下信息：

```markdown
## Bug 描述
简洁清晰地描述遇到的问题

## 复现步骤
1. 打开程序
2. 选择文件 'xxx.pdf'
3. 点击转换
4. 出现错误

## 预期行为
描述您期望发生的情况

## 实际行为
描述实际发生的情况

## 环境信息
- 操作系统: Windows 11
- Python 版本: 3.10.5
- 程序版本: 1.0.0
- PDF 文件信息: 大小、页数、类型

## 错误日志
```
粘贴完整的错误日志
```

## 截图
如果适用，请添加截图帮助解释问题
```

### 功能请求

使用功能请求模板：

```markdown
## 功能描述
清晰描述您希望添加的功能

## 使用场景
描述这个功能的使用场景和价值

## 建议的实现方式
如果有想法，请描述可能的实现方式

## 替代方案
描述您考虑过的其他解决方案

## 附加信息
任何其他相关信息
```

## 🔄 提交 Pull Request

### PR 流程

1. **创建功能分支**
   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

2. **进行开发**
   - 编写代码
   - 添加测试
   - 更新文档

3. **提交更改**
   ```bash
   git add .
   git commit -m "feat: add new feature description"
   ```

4. **推送分支**
   ```bash
   git push origin feature/your-feature-name
   ```

5. **创建 Pull Request**
   - 在 GitHub 上创建 PR
   - 填写 PR 模板
   - 等待代码审查

### PR 模板

```markdown
## 更改类型
- [ ] Bug 修复
- [ ] 新功能
- [ ] 文档更新
- [ ] 性能优化
- [ ] 代码重构

## 更改描述
简洁描述这个 PR 的更改内容

## 相关 Issue
Fixes #(issue number)

## 测试
- [ ] 已添加单元测试
- [ ] 已进行手动测试
- [ ] 所有测试通过

## 检查清单
- [ ] 代码遵循项目规范
- [ ] 已更新相关文档
- [ ] 已添加必要的注释
- [ ] 没有引入新的警告
```

## 📏 代码规范

### Python 代码风格

我们遵循 PEP 8 标准，并使用以下工具：

```bash
# 代码格式化
black main.py

# 导入排序
isort main.py

# 代码检查
flake8 main.py
```

### 命名规范

- **变量和函数**: `snake_case`
- **类名**: `PascalCase`
- **常量**: `UPPER_CASE`
- **私有方法**: `_private_method`

### 注释规范

```python
def convert_pdf_to_markdown(pdf_path: str, output_dir: str) -> bool:
    """
    将PDF文件转换为Markdown格式
    
    Args:
        pdf_path (str): PDF文件路径
        output_dir (str): 输出目录路径
    
    Returns:
        bool: 转换是否成功
    
    Raises:
        FileNotFoundError: 当PDF文件不存在时
        PermissionError: 当没有写入权限时
    """
    pass
```

### 提交信息规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

类型说明：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建过程或辅助工具的变动

示例：
```
feat(ui): add batch processing progress indicator

Add a detailed progress bar that shows current file being processed
and overall batch progress percentage.

Closes #123
```

## 🧪 测试指南

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_converter.py

# 运行测试并生成覆盖率报告
pytest --cov=main --cov-report=html
```

### 编写测试

```python
import pytest
from unittest.mock import Mock, patch
from main import ConversionWorker

class TestConversionWorker:
    def test_extract_images_with_pymupdf(self):
        """测试PyMuPDF图片提取功能"""
        worker = ConversionWorker([], "", {}, False, {})
        
        with patch('fitz.open') as mock_fitz:
            # 设置mock对象
            mock_doc = Mock()
            mock_page = Mock()
            mock_page.get_images.return_value = [('img1', 'jpeg')]
            mock_doc.__getitem__.return_value = mock_page
            mock_doc.__len__.return_value = 1
            mock_fitz.return_value = mock_doc
            
            # 执行测试
            result = worker._extract_images_with_pymupdf("test.pdf", "output")
            
            # 验证结果
            assert isinstance(result, list)
            mock_fitz.assert_called_once_with("test.pdf")
```

### 测试覆盖率

我们目标是保持测试覆盖率在 80% 以上。请为新功能添加相应的测试。

## 📚 文档贡献

### 文档类型

- **README.md**: 项目概述和快速开始
- **教程.md**: 详细使用教程
- **API 文档**: 代码接口文档
- **示例文档**: 使用示例和配置

### 文档规范

1. **使用清晰的标题层级**
2. **提供代码示例**
3. **包含截图说明**（如果适用）
4. **保持内容更新**

### 文档更新流程

1. 修改相关文档文件
2. 本地预览确认效果
3. 提交 PR 并说明更改内容

## 🎯 贡献类型

### 代码贡献

- **新功能开发**
  - 支持新的输出格式
  - 添加新的LLM服务
  - 改进图片处理算法

- **Bug 修复**
  - 修复转换错误
  - 解决界面问题
  - 优化性能问题

- **代码优化**
  - 重构复杂函数
  - 提高代码可读性
  - 优化算法效率

### 非代码贡献

- **文档改进**
  - 修正错误
  - 添加示例
  - 翻译文档

- **测试用例**
  - 添加单元测试
  - 提供测试数据
  - 改进测试覆盖率

- **用户体验**
  - 界面设计建议
  - 交互流程优化
  - 错误信息改进

## 🏆 贡献者认可

我们会在以下地方认可贡献者：

- **README.md** 中的贡献者列表
- **CHANGELOG.md** 中的更新记录
- **GitHub Releases** 中的致谢

### 贡献者等级

- **🌟 核心贡献者**: 长期活跃，重大功能贡献
- **🔧 代码贡献者**: 提交代码修复或功能
- **📝 文档贡献者**: 改进文档和教程
- **🐛 问题报告者**: 报告重要 Bug
- **💡 建议提供者**: 提出有价值的功能建议

## 📞 获取帮助

如果您在贡献过程中遇到问题：

1. **查看现有 Issues**: 可能已有相关讨论
2. **创建 Discussion**: 用于一般性问题讨论
3. **联系维护者**: 通过 GitHub 或邮件联系

## 📄 许可证

通过贡献代码，您同意您的贡献将在 MIT 许可证下发布。

---

再次感谢您的贡献！每一个贡献都让这个项目变得更好。 🙏