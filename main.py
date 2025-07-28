# pdf_to_md_gui.py


import sys
import os
import traceback
from pathlib import Path
import json
import base64


from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QFileDialog, QTextEdit, QLabel, QProgressBar,
    QMessageBox, QGroupBox, QCheckBox, QLineEdit, QSpinBox,
    QTabWidget, QListWidget, QListWidgetItem, QAbstractItemView,
    QComboBox
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSettings
from PyQt5.QtGui import QFont, QPalette, QColor



# 检查 PyMuPDF (fitz) 是否可用
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False



# 确保 marker-pdf[full] 已安装
try:
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.config.parser import ConfigParser
    MARKER_AVAILABLE = True
except ImportError as e:
    MARKER_AVAILABLE = False
    MARKER_IMPORT_ERROR = str(e)

# --- 后台转换线程 ---
class ConversionWorker(QThread):
    log_signal = pyqtSignal(str)  # 发送日志信息
    progress_signal = pyqtSignal(int)  # 发送进度 (0-100)
    finished_signal = pyqtSignal(bool, str)  # 转换完成 (成功/失败, 消息)



    def __init__(self, pdf_files, output_dir, config_dict, use_llm, llm_service_config, use_fallback_extraction=False):
        super().__init__()
        self.pdf_files = pdf_files
        self.output_dir = output_dir
        self.config_dict = config_dict
        self.use_llm = use_llm
        self.llm_service_config = llm_service_config
        self.use_fallback_extraction = use_fallback_extraction # 保存新选项
        self._is_running = True
        self.converter = None







    def stop(self):
        self._is_running = False
        if self.converter:
            # 尝试中断转换器（Marker 本身可能不直接支持）
            # 这里主要是设置标志位
            pass 



    #       把下面这个【新增的辅助方法】完整地粘贴到这里。
    #
    def _extract_images_with_pymupdf(self, pdf_path, images_dir):
        """使用 PyMuPDF 作为备用方案提取图片。"""
        if not PYMUPDF_AVAILABLE:
            self.log_signal.emit("  -> PyMuPDF (fitz) 未安装，无法执行备用图片提取。")
            return []
        
        try:
            pdf_document = fitz.open(pdf_path)
            extracted_files = []
            
            for page_index in range(len(pdf_document)):
                page_document = pdf_document[page_index]
                image_list = page_document.get_images(full=True)
                if not image_list:
                    continue
                
                for image_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = pdf_document.extract_image(xref)
                    if not base_image:
                        continue

                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # 尝试生成一个与 marker 风格类似的图片名
                    img_name = f"_page_{page_index + 1}_fallback_img_{image_index + 1}.{image_ext}"
                    img_path = os.path.join(images_dir, img_name)
                    
                    with open(img_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    extracted_files.append(img_name)
            
            pdf_document.close()
            if extracted_files:
                 self.log_signal.emit(f"  -> [备用引擎] PyMuPDF 成功提取并保存了 {len(extracted_files)} 张图片。")
            else:
                 self.log_signal.emit(f"  -> [备用引擎] PyMuPDF 未在该文件中找到可提取的图片。")
            return extracted_files

        except Exception as e:
            self.log_signal.emit(f"  -> [备用引擎] PyMuPDF 提取图片时发生错误: {e}")
            return []

    def _update_markdown_image_links(self, markdown_content, fallback_image_files, pdf_stem):
        """更新Markdown中的图片链接，将备用引擎提取的图片链接到正确的路径。"""
        import re
        
        if not fallback_image_files:
            return markdown_content
        
        # 记录已使用的图片文件
        used_images = set()
        
        # 查找所有的图片引用模式
        # 匹配类似 ![](image_name.ext) 或 ![alt text](image_name.ext) 的模式
        image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        
        def replace_image_link(match):
            alt_text = match.group(1)
            original_link = match.group(2)
            
            # 如果原始链接已经是相对路径或绝对路径，不修改
            if '/' in original_link or '\\' in original_link:
                return match.group(0)
            
            # 检查是否有对应的备用引擎提取的图片
            # 尝试匹配文件名（忽略扩展名）
            original_name_without_ext = os.path.splitext(original_link)[0]
            
            # 查找最匹配的备用图片
            best_match = None
            for fallback_img in fallback_image_files:
                # 如果原始链接就在备用图片列表中，直接使用
                if original_link == fallback_img:
                    best_match = fallback_img
                    break
                # 或者如果原始链接包含页面信息，尝试匹配
                if original_name_without_ext in fallback_img:
                    best_match = fallback_img
                    break
            
            # 如果没有找到匹配的，使用第一个备用图片（按页面顺序）
            if not best_match and fallback_image_files:
                # 尝试从原始链接中提取页面信息
                page_match = re.search(r'page[_\s]*(\d+)', original_link.lower())
                if page_match:
                    page_num = int(page_match.group(1))
                    # 查找对应页面的图片
                    for fallback_img in fallback_image_files:
                        if f'_page_{page_num}_' in fallback_img:
                            best_match = fallback_img
                            break
                
                # 如果还是没找到，使用第一个未使用的图片
                if not best_match:
                    for fallback_img in fallback_image_files:
                        if fallback_img not in used_images:
                            best_match = fallback_img
                            break
            
            if best_match:
                used_images.add(best_match)
                # 构建相对路径
                relative_path = f"{pdf_stem}_images/{best_match}"
                return f'![{alt_text}]({relative_path})'
            else:
                return match.group(0)
        
        # 替换所有图片链接
        updated_content = re.sub(image_pattern, replace_image_link, markdown_content)
        
        # 找出未使用的图片（备用引擎提取但未在Markdown中引用的图片）
        unused_images = [img for img in fallback_image_files if img not in used_images]
        
        # 处理未使用的图片
        if unused_images:
            self.log_signal.emit(f"  -> 发现 {len(unused_images)} 张未在原Markdown中引用的图片，将添加到文档中")
            
            # 策略1: 尝试按页面顺序智能插入
            updated_content = self._insert_unused_images_intelligently(updated_content, unused_images, pdf_stem)
            
            # 策略2: 如果智能插入效果不好，在文档末尾添加剩余图片
            remaining_unused = [img for img in unused_images if f"{pdf_stem}_images/{img}" not in updated_content]
            if remaining_unused:
                self.log_signal.emit(f"  -> 在文档末尾添加剩余的 {len(remaining_unused)} 张图片")
                updated_content += "\n\n## 补充图片\n\n"
                updated_content += "*以下是PDF中提取到但未在原文档中引用的图片：*\n\n"
                
                # 按页面顺序排序
                remaining_unused.sort(key=lambda x: self._extract_page_number(x))
                
                for img_file in remaining_unused:
                    relative_path = f"{pdf_stem}_images/{img_file}"
                    page_num = self._extract_page_number(img_file)
                    updated_content += f"![第{page_num}页图片]({relative_path})\n\n"
        
        # 如果没有找到任何图片引用，但有备用图片，在文档末尾添加所有图片
        elif updated_content == markdown_content and fallback_image_files:
            self.log_signal.emit(f"  -> 在Markdown中未找到图片引用，将在文档末尾添加 {len(fallback_image_files)} 张提取的图片")
            updated_content += "\n\n## 提取的图片\n\n"
            for i, img_file in enumerate(fallback_image_files, 1):
                relative_path = f"{pdf_stem}_images/{img_file}"
                page_num = self._extract_page_number(img_file)
                updated_content += f"![第{page_num}页图片{i}]({relative_path})\n\n"
        
        return updated_content

    def _extract_page_number(self, img_filename):
        """从图片文件名中提取页面号"""
        import re
        match = re.search(r'_page_(\d+)_', img_filename)
        return int(match.group(1)) if match else 0

    def _insert_unused_images_intelligently(self, markdown_content, unused_images, pdf_stem):
        """智能地将未使用的图片插入到Markdown内容中"""
        import re
        
        # 按页面顺序排序未使用的图片
        unused_images.sort(key=lambda x: self._extract_page_number(x))
        
        # 将Markdown按行分割
        lines = markdown_content.split('\n')
        
        # 尝试找到合适的插入位置
        for img_file in unused_images:
            page_num = self._extract_page_number(img_file)
            relative_path = f"{pdf_stem}_images/{img_file}"
            
            # 策略1: 寻找页面相关的标题或内容
            inserted = False
            for i, line in enumerate(lines):
                # 如果找到包含页面信息的标题或内容
                if (re.search(rf'第\s*{page_num}\s*页', line) or 
                    re.search(rf'page\s*{page_num}', line.lower()) or
                    re.search(rf'p\.\s*{page_num}', line.lower())):
                    
                    # 在该行后插入图片
                    lines.insert(i + 1, f"\n![第{page_num}页补充图片]({relative_path})\n")
                    inserted = True
                    break
            
            # 策略2: 如果没有找到页面相关内容，尝试按标题层级插入
            if not inserted:
                # 寻找合适的标题位置（# ## ### 等）
                header_positions = []
                for i, line in enumerate(lines):
                    if re.match(r'^#+\s', line):
                        header_positions.append(i)
                
                # 根据页面号选择合适的标题位置
                if header_positions:
                    # 简单策略：根据页面号比例选择插入位置
                    total_headers = len(header_positions)
                    if total_headers > 1:
                        # 估算插入位置
                        insert_ratio = min(page_num / 10.0, 1.0)  # 假设最多10页
                        insert_index = int(insert_ratio * (total_headers - 1))
                        insert_pos = header_positions[insert_index]
                        
                        # 在选定的标题后插入
                        lines.insert(insert_pos + 1, f"\n![第{page_num}页图片]({relative_path})\n")
                        inserted = True
            
            # 如果还是没有插入，记录日志（这些图片会在文档末尾处理）
            if not inserted:
                self.log_signal.emit(f"    -> 图片 {img_file} 未找到合适的插入位置，将在文档末尾添加")
        
        return '\n'.join(lines)
    #
    # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
    # ===================================================================





    def run(self):
        if not MARKER_AVAILABLE:
            self.finished_signal.emit(False, f"Marker 库未正确安装或导入: {MARKER_IMPORT_ERROR}")
            return

        if not self.pdf_files:
            self.finished_signal.emit(False, "没有 PDF 文件需要转换。")
            return

        try:
            self.log_signal.emit(f"开始转换 {len(self.pdf_files)} 个 PDF 文件...")

            # --- 设置自定义模型缓存目录 ---
            try:
                main_program_dir = os.getcwd()
                custom_models_dir = os.path.join(main_program_dir, "markermodels")
                os.makedirs(custom_models_dir, exist_ok=True)
                os.environ['HF_HOME'] = main_program_dir
                self.log_signal.emit(f"已设置 HF_HOME 环境变量指向: {main_program_dir}")
                self.log_signal.emit(f"Marker 模型将从 '{custom_models_dir}' 加载/下载。")
            except Exception as env_error:
                self.log_signal.emit(f"警告: 设置自定义模型目录时出错: {env_error}")

            # --- 加载 Marker 模型和配置 ---
            self.log_signal.emit("正在加载 Marker 模型...")
            try:
                artifact_dict = create_model_dict()
            except Exception as model_load_error:
                 self.log_signal.emit(f"严重错误: 加载 Marker 模型失败: {model_load_error}")
                 self.log_signal.emit(traceback.format_exc())
                 self.finished_signal.emit(False, f"加载 Marker 模型失败: {model_load_error}")
                 return

            final_config = self.config_dict.copy()
            if self.use_llm:
                final_config.update(self.llm_service_config)

            config_parser = ConfigParser(final_config)

            self.converter = PdfConverter(
                artifact_dict=artifact_dict,
                config=config_parser.generate_config_dict(),
                processor_list=config_parser.get_processors(),
                renderer=config_parser.get_renderer(),
                llm_service=config_parser.get_llm_service() if self.use_llm else None
            )
            self.log_signal.emit("Marker 模型加载完成。")

            total_files = len(self.pdf_files)
            successful = 0

            for i, pdf_path in enumerate(self.pdf_files):
                if not self._is_running:
                    self.log_signal.emit("转换任务被用户中止。")
                    self.finished_signal.emit(False, "任务被中止。")
                    return

                self.log_signal.emit(f"[{i+1}/{total_files}] 正在转换: {os.path.basename(pdf_path)}")
                self.progress_signal.emit(int((i / total_files) * 100))

                try:
                    # 步骤 1: 执行PDF到Markdown的转换
                    rendered = self.converter(pdf_path)

                    # 步骤 2: 提取和保存图片（最终修正版双引擎策略）
                    marker_extracted_images = False
                    pdf_stem = Path(pdf_path).stem
                    images_dir = os.path.join(self.output_dir, f"{pdf_stem}_images")
                    fallback_image_files = []
                    
                    # 策略一: 尝试使用 Marker (主引擎) 提取
                    if hasattr(rendered, 'metadata') and hasattr(rendered.metadata, 'images') and isinstance(rendered.metadata.images, dict) and rendered.metadata.images:
                        marker_extracted_images = True
                        os.makedirs(images_dir, exist_ok=True)
                        self.log_signal.emit(f"  -> [主引擎] Marker 发现 {len(rendered.metadata.images)} 张图片，正在保存...")

                        for img_name, img_b64_data in rendered.metadata.images.items():
                            img_path = os.path.join(images_dir, img_name)
                            try:
                                img_bytes = base64.b64decode(img_b64_data)
                                with open(img_path, 'wb') as img_file:
                                    img_file.write(img_bytes)
                                self.log_signal.emit(f"    -> 已保存图片: {img_name}")
                            except Exception as img_save_error:
                                self.log_signal.emit(f"    -> 错误: 保存 Marker 提取的图片 '{img_name}' 失败: {img_save_error}")
                    
                    # 策略二: 根据主引擎的结果，决定是否需要启动备用引擎
                    if not marker_extracted_images:
                        if self.use_fallback_extraction:
                            self.log_signal.emit("  -> [主引擎] Marker 未提取到图片，启动备用引擎 PyMuPDF...")
                            os.makedirs(images_dir, exist_ok=True)
                            fallback_image_files = self._extract_images_with_pymupdf(pdf_path, images_dir)
                        else:
                            self.log_signal.emit("  -> 未在文档中检测到可提取的图片。(备用引擎未开启)")

                    # 步骤 3: 处理Markdown内容并保存文件
                    markdown_content = rendered.markdown
                    
                    # 如果使用了备用引擎提取图片，需要更新Markdown中的图片链接
                    if fallback_image_files:
                        markdown_content = self._update_markdown_image_links(markdown_content, fallback_image_files, pdf_stem)
                    
                    md_filename = Path(pdf_path).stem + ".md"
                    md_output_path = os.path.join(self.output_dir, md_filename)
                    with open(md_output_path, 'w', encoding='utf-8') as f:
                        f.write(markdown_content)

                    self.log_signal.emit(f"  -> 已保存: {md_filename}")
                    successful += 1

                except Exception as e:
                    error_msg = f"转换失败 '{os.path.basename(pdf_path)}': {e}"
                    self.log_signal.emit(f"  -> 错误: {error_msg}")
                    self.log_signal.emit(traceback.format_exc())

            self.progress_signal.emit(100)
            self.finished_signal.emit(True, f"转换完成! 成功: {successful}/{total_files}")

        except Exception as e:
            self.log_signal.emit(f"严重错误: {e}")
            self.log_signal.emit(traceback.format_exc())
            self.finished_signal.emit(False, f"转换因严重错误失败: {e}")







# --- 主窗口 ---
class PDFToMdApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PDF to Markdown 批量转换器 (基于 Marker)')
        self.setGeometry(100, 100, 1000, 700)
        
        # 检查依赖
        if not MARKER_AVAILABLE:
             QMessageBox.critical(self, "依赖错误", f"无法导入 Marker 库。请确保已安装 'marker-pdf[full]'。\n错误信息: {MARKER_IMPORT_ERROR}")
             sys.exit(1)

        self.settings = QSettings("MyCompany", "PDFToMdApp")
        self.pdf_files = []
        self.worker_thread = None
        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # --- 文件选择区域 ---
        file_group = QGroupBox("1. 选择 PDF 文件")
        file_layout = QVBoxLayout()
        
        self.btn_select_files = QPushButton("选择 PDF 文件")
        self.btn_select_files.clicked.connect(self.select_files)
        self.btn_select_folder = QPushButton("选择包含 PDF 的文件夹")
        self.btn_select_folder.clicked.connect(self.select_folder)
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.btn_remove_selected = QPushButton("移除选中")
        self.btn_remove_selected.clicked.connect(self.remove_selected_files)
        self.btn_clear_list = QPushButton("清空列表")
        self.btn_clear_list.clicked.connect(self.clear_file_list)

        file_btn_layout = QHBoxLayout()
        file_btn_layout.addWidget(self.btn_select_files)
        file_btn_layout.addWidget(self.btn_select_folder)
        file_btn_layout.addStretch()

        list_btn_layout = QHBoxLayout()
        list_btn_layout.addWidget(self.btn_remove_selected)
        list_btn_layout.addWidget(self.btn_clear_list)
        list_btn_layout.addStretch()

        file_layout.addLayout(file_btn_layout)
        file_layout.addWidget(self.list_widget)
        file_layout.addLayout(list_btn_layout)
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        # --- 配置和输出区域 ---
        config_output_widget = QWidget()
        config_output_layout = QHBoxLayout()
        
        # --- 配置选项卡 ---
        self.tabs = QTabWidget()
        
        # 基础设置
        self.basic_tab = QWidget()
        basic_layout = QFormLayout()
        
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("选择输出目录")
        self.btn_browse_output = QPushButton("浏览...")
        self.btn_browse_output.clicked.connect(self.browse_output_dir)
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(self.btn_browse_output)
        basic_layout.addRow("输出目录:", output_dir_layout)

        self.page_range_edit = QLineEdit()
        self.page_range_edit.setPlaceholderText("例如: 0,5-10,20 (留空为全部)")
        basic_layout.addRow("页码范围:", self.page_range_edit)

        self.format_lines_cb = QCheckBox("格式化行 (改善数学公式)")
        self.force_ocr_cb = QCheckBox("强制 OCR")
        self.strip_existing_ocr_cb = QCheckBox("移除现有 OCR 文本")
        basic_layout.addRow(self.format_lines_cb)
        basic_layout.addRow(self.force_ocr_cb)
        basic_layout.addRow(self.strip_existing_ocr_cb)

        self.basic_tab.setLayout(basic_layout)
        self.tabs.addTab(self.basic_tab, "基础设置")

        # LLM 设置
        self.llm_tab = QWidget()
        llm_layout = QFormLayout()
        
        self.use_llm_cb = QCheckBox("使用 LLM 提高准确性")
        self.use_llm_cb.stateChanged.connect(self.toggle_llm_options)
        llm_layout.addRow(self.use_llm_cb)

        self.llm_service_combo = QComboBox()
        self.llm_service_combo.addItems(["OpenAI", "Ollama", "Gemini", "Claude", "Azure OpenAI"])
        llm_layout.addRow("LLM 服务:", self.llm_service_combo)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        llm_layout.addRow("API 密钥:", self.api_key_edit)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("例如: https://api.openai.com/v1")
        llm_layout.addRow("Base URL:", self.base_url_edit)

        self.model_name_edit = QLineEdit()
        self.model_name_edit.setPlaceholderText("例如: gpt-4, llama3, gemini-pro")
        llm_layout.addRow("模型名称:", self.model_name_edit)

        self.llm_tab.setLayout(llm_layout)
        self.tabs.addTab(self.llm_tab, "LLM 设置")
        self.toggle_llm_options(Qt.Unchecked) # 初始禁用 LLM 选项

        # 高级设置
        self.advanced_tab = QWidget()
        advanced_layout = QFormLayout()
        
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["markdown", "json", "html", "chunks"])
        advanced_layout.addRow("输出格式:", self.output_format_combo)

        self.debug_cb = QCheckBox("启用调试模式")
        advanced_layout.addRow(self.debug_cb)

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 16)
        self.workers_spin.setValue(4)
        advanced_layout.addRow("工作进程数:", self.workers_spin)




        # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼ 新增代码 ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
        self.fallback_image_extraction_cb = QCheckBox("启用 PyMuPDF 作为备用图片提取引擎")
        self.fallback_image_extraction_cb.setToolTip(
            "当 Marker 未能提取出图片时，自动尝试使用 PyMuPDF 进行二次提取。\n"
            "可以解决某些特殊PDF图片无法导出的问题。"
        )
        self.fallback_image_extraction_cb.setChecked(True) # 默认开启
        advanced_layout.addRow(self.fallback_image_extraction_cb)
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲ 新增代码结束 ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲


        

        self.advanced_tab.setLayout(advanced_layout)
        self.tabs.addTab(self.advanced_tab, "高级设置")

        # --- 操作按钮 ---
        self.action_group = QGroupBox("3. 操作")
        action_layout = QVBoxLayout()
        self.btn_start = QPushButton("🚀 开始转换")
        self.btn_start.clicked.connect(self.start_conversion)
        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.clicked.connect(self.stop_conversion)
        self.btn_stop.setEnabled(False)
        
        action_layout.addWidget(self.btn_start)
        action_layout.addWidget(self.btn_stop)
        self.action_group.setLayout(action_layout)

        config_output_layout.addWidget(self.tabs, 3)
        config_output_layout.addWidget(self.action_group, 1)
        config_output_widget.setLayout(config_output_layout)
        main_layout.addWidget(config_output_widget)

        # --- 进度和日志 ---
        progress_log_widget = QWidget()
        progress_log_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        # 设置日志字体
        log_font = QFont("Consolas", 9) # 或 "Monospace"
        self.log_text.setFont(log_font)
        # 设置日志背景色为浅灰色，提高可读性
        palette = self.log_text.palette()
        palette.setColor(QPalette.Base, QColor(245, 245, 245)) # 浅灰色
        self.log_text.setPalette(palette)
        
        self.btn_save_log = QPushButton("💾 保存日志")
        self.btn_save_log.clicked.connect(self.save_log)
        self.btn_clear_log = QPushButton("🗑 清空日志")
        self.btn_clear_log.clicked.connect(self.clear_log)
        
        log_btn_layout = QHBoxLayout()
        log_btn_layout.addWidget(self.btn_save_log)
        log_btn_layout.addWidget(self.btn_clear_log)
        log_btn_layout.addStretch()
        
        log_layout.addWidget(self.log_text)
        log_layout.addLayout(log_btn_layout)
        log_group.setLayout(log_layout)
        
        progress_log_layout.addWidget(self.progress_bar)
        progress_log_layout.addWidget(log_group)
        progress_log_widget.setLayout(progress_log_layout)
        main_layout.addWidget(progress_log_widget)

        self.setLayout(main_layout)

    def toggle_llm_options(self, state):
        enabled = state == Qt.Checked
        self.llm_service_combo.setEnabled(enabled)
        self.api_key_edit.setEnabled(enabled)
        self.base_url_edit.setEnabled(enabled)
        self.model_name_edit.setEnabled(enabled)

    def select_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "选择 PDF 文件", "", "PDF Files (*.pdf)")
        if file_paths:
            self.add_files_to_list(file_paths)

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "选择包含 PDF 的文件夹")
        if folder_path:
            pdf_files = [str(p) for p in Path(folder_path).rglob("*.pdf")]
            if pdf_files:
                self.add_files_to_list(pdf_files)
            else:
                QMessageBox.information(self, "信息", "所选文件夹中未找到 PDF 文件。")

    def add_files_to_list(self, file_paths):
        current_files = set(self.pdf_files)
        new_files = []
        for fp in file_paths:
            if fp not in current_files:
                self.pdf_files.append(fp)
                item = QListWidgetItem(os.path.basename(fp))
                item.setToolTip(fp) # 鼠标悬停显示完整路径
                self.list_widget.addItem(item)
                new_files.append(fp)
        if new_files:
            self.log(f"已添加 {len(new_files)} 个新文件到列表。")

    def remove_selected_files(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            row = self.list_widget.row(item)
            file_path = self.pdf_files.pop(row)
            self.list_widget.takeItem(row)
            self.log(f"已从列表移除: {os.path.basename(file_path)}")

    def clear_file_list(self):
        self.pdf_files.clear()
        self.list_widget.clear()
        self.log("文件列表已清空。")

    def browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if dir_path:
            self.output_dir_edit.setText(dir_path)

    def get_config_dict(self):
        config = {
            "output_format": self.output_format_combo.currentText(),
        }
        if self.page_range_edit.text():
            config["page_range"] = self.page_range_edit.text()
        if self.format_lines_cb.isChecked():
            config["format_lines"] = True
        if self.force_ocr_cb.isChecked():
            config["force_ocr"] = True
        if self.strip_existing_ocr_cb.isChecked():
            config["strip_existing_ocr"] = True
        if self.debug_cb.isChecked():
            config["debug"] = True
            
        # workers 通常在命令行工具中使用，对于单进程 GUI 调用可能不直接适用
        # config["workers"] = self.workers_spin.value() 
        
        return config

    def get_llm_config(self):
        service_map = {
            "OpenAI": "marker.services.openai.OpenAIService",
            "Ollama": "marker.services.ollama.OllamaService",
            "Gemini": "marker.services.gemini.GoogleGeminiService",
            "Claude": "marker.services.claude.ClaudeService",
            "Azure OpenAI": "marker.services.azure_openai.AzureOpenAIService",
        }
        service_name = self.llm_service_combo.currentText()
        service_class = service_map.get(service_name, "")

        llm_config = {
            "llm_service": service_class,
        }

        api_key = self.api_key_edit.text().strip()
        base_url = self.base_url_edit.text().strip()
        model_name = self.model_name_edit.text().strip()

        if service_name == "OpenAI":
            # 兼容 LM Studio 等本地 OpenAI API 兼容服务器
            # LM Studio 通常使用 openai_api_key, openai_base_url, model
            if api_key: llm_config["openai_api_key"] = api_key
            if base_url: llm_config["openai_base_url"] = base_url
            # 关键修改：使用 "model" 键而不是 "openai_model"
            # 这样可以同时兼容标准 OpenAI 和 LM Studio
            if model_name: llm_config["model"] = model_name
            
        elif service_name == "Ollama":
            if base_url: llm_config["ollama_base_url"] = base_url
            if model_name: llm_config["ollama_model"] = model_name
        elif service_name == "Gemini":
            if api_key: llm_config["gemini_api_key"] = api_key
            # Gemini 默认模型通常是 gemini-flash 或 gemini-pro
            if model_name: llm_config["gemini_model"] = model_name 
        elif service_name == "Claude":
            if api_key: llm_config["claude_api_key"] = api_key
            if model_name: llm_config["claude_model_name"] = model_name
        elif service_name == "Azure OpenAI":
            if api_key: llm_config["azure_api_key"] = api_key
            if base_url: llm_config["azure_endpoint"] = base_url
            if model_name: llm_config["deployment_name"] = model_name
            
        return llm_config

    def start_conversion(self):
        if not self.pdf_files:
            QMessageBox.warning(self, "警告", "请先选择要转换的 PDF 文件。")
            return

        output_dir = self.output_dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "警告", "请选择输出目录。")
            return

        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法创建输出目录 '{output_dir}': {e}")
                return

        self.save_settings() # 保存当前设置

        config_dict = self.get_config_dict()
        use_llm = self.use_llm_cb.isChecked()
        llm_service_config = self.get_llm_config() if use_llm else {}





        # ===================================================================
        # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
        #
        #       在这里【插入】获取新复选框状态的代码。
        #
        use_fallback = self.fallback_image_extraction_cb.isChecked()
        #
        #       【修改】下面的日志记录部分，加入新选项的状态。
        #
        self.log("="*50)
        self.log("开始新的转换任务...")
        self.log(f"文件总数: {len(self.pdf_files)}")
        self.log(f"输出目录: {output_dir}")
        self.log(f"基础配置: {config_dict}")
        if use_llm:
            self.log(f"使用 LLM: 是")
            self.log(f"LLM 服务: {self.llm_service_combo.currentText()}")
            # 出于安全考虑，不记录 API 密钥
            safe_llm_config = {k:v for k,v in llm_service_config.items() if 'key' not in k.lower() and 'secret' not in k.lower()}
            self.log(f"LLM 配置: {safe_llm_config}")
        else:
            self.log("使用 LLM: 否")
        #       在这里【插入】新的日志行。
        self.log(f"启用备用图片提取: {'是' if use_fallback else '否'}")
        self.log("-"*30)
        #
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        # ===================================================================





        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)





        # ===================================================================
        # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
        #
        #       【修改】下面这一行，将新的 use_fallback 参数传递给 ConversionWorker 的构造函数。
        #
        # 原来的代码:
        # self.worker_thread = ConversionWorker(
        #     self.pdf_files, output_dir, config_dict, use_llm, llm_service_config
        # )
        #
        # 修改后的代码:
        self.worker_thread = ConversionWorker(
            self.pdf_files, output_dir, config_dict, use_llm, llm_service_config,
            use_fallback_extraction=use_fallback  # 传递新参数
        )
        #
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        # ===================================================================



        self.worker_thread.log_signal.connect(self.log)
        self.worker_thread.progress_signal.connect(self.progress_bar.setValue)
        self.worker_thread.finished_signal.connect(self.on_conversion_finished)
        self.worker_thread.start()

    def stop_conversion(self):
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(self, '确认', '确定要停止转换吗？',
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.log("正在请求停止转换...")
                self.btn_stop.setEnabled(False)
                self.worker_thread.stop() # 设置停止标志

    def on_conversion_finished(self, success, message):
        self.worker_thread = None
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100 if success else 0)
        
        if success:
            self.log(f"🎉 {message}")
            QMessageBox.information(self, "完成", message)
        else:
            self.log(f"❌ {message}")
            QMessageBox.critical(self, "错误", message)

    def log(self, message):
        self.log_text.append(message)
        # 自动滚动到底部
        self.log_text.moveCursor(self.log_text.textCursor().End)
        QApplication.processEvents() # 确保 UI 及时更新

    def save_log(self):
        log_content = self.log_text.toPlainText()
        if not log_content:
            QMessageBox.information(self, "信息", "日志为空。")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "保存日志", "conversion_log.txt", "Text Files (*.txt)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                QMessageBox.information(self, "成功", f"日志已保存到 {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存日志失败: {e}")

    def clear_log(self):
        self.log_text.clear()

    def save_settings(self):
        self.settings.setValue("output_dir", self.output_dir_edit.text())
        self.settings.setValue("page_range", self.page_range_edit.text())
        self.settings.setValue("format_lines", self.format_lines_cb.isChecked())
        self.settings.setValue("force_ocr", self.force_ocr_cb.isChecked())
        self.settings.setValue("strip_existing_ocr", self.strip_existing_ocr_cb.isChecked())
        self.settings.setValue("use_llm", self.use_llm_cb.isChecked())
        self.settings.setValue("llm_service", self.llm_service_combo.currentText())
        self.settings.setValue("api_key", self.api_key_edit.text()) # 注意：保存 API 密钥需谨慎
        self.settings.setValue("base_url", self.base_url_edit.text())
        self.settings.setValue("model_name", self.model_name_edit.text())
        self.settings.setValue("output_format", self.output_format_combo.currentText())
        self.settings.setValue("debug", self.debug_cb.isChecked())
        self.settings.setValue("workers", self.workers_spin.value())


        # ===================================================================
        # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
        #
        #       把下面这行【新增代码】粘贴到这里。
        #
        self.settings.setValue("fallback_extraction", self.fallback_image_extraction_cb.isChecked())
        #
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        # ===================================================================

        
        self.log("设置已保存。")

    def load_settings(self):
        self.output_dir_edit.setText(self.settings.value("output_dir", ""))
        self.page_range_edit.setText(self.settings.value("page_range", ""))
        self.format_lines_cb.setChecked(self.settings.value("format_lines", False, type=bool))
        self.force_ocr_cb.setChecked(self.settings.value("force_ocr", False, type=bool))
        self.strip_existing_ocr_cb.setChecked(self.settings.value("strip_existing_ocr", False, type=bool))
        self.use_llm_cb.setChecked(self.settings.value("use_llm", False, type=bool))
        
        llm_service = self.settings.value("llm_service", "OpenAI")
        index = self.llm_service_combo.findText(llm_service)
        if index >= 0:
            self.llm_service_combo.setCurrentIndex(index)
            
        self.api_key_edit.setText(self.settings.value("api_key", ""))
        self.base_url_edit.setText(self.settings.value("base_url", ""))
        self.model_name_edit.setText(self.settings.value("model_name", ""))
        
        output_format = self.settings.value("output_format", "markdown")
        index = self.output_format_combo.findText(output_format)
        if index >= 0:
            self.output_format_combo.setCurrentIndex(index)
            
        self.debug_cb.setChecked(self.settings.value("debug", False, type=bool))
        self.workers_spin.setValue(self.settings.value("workers", 4, type=int))



        # ===================================================================
        # ▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼▼
        #
        #       把下面这行【新增代码】粘贴到这里。
        #
        self.fallback_image_extraction_cb.setChecked(self.settings.value("fallback_extraction", True, type=bool))
        #
        # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲
        # ===================================================================



        
        # 根据加载的 LLM 状态更新 UI
        self.toggle_llm_options(Qt.Checked if self.use_llm_cb.isChecked() else Qt.Unchecked)
        self.log("设置已加载。")

    def closeEvent(self, event):
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(self, '确认退出', '转换正在进行中，确定要退出吗？',
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.worker_thread.stop()
                self.worker_thread.wait(2000) # 等待最多2秒
                self.save_settings()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_settings()
            event.accept()

# --- 主程序入口 ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName("PDF to Markdown Converter")
    app.setApplicationVersion("1.0")
    
    # 设置应用程序样式 (可选)
    # app.setStyle('Fusion') 

    window = PDFToMdApp()
    window.show()
    sys.exit(app.exec_())
