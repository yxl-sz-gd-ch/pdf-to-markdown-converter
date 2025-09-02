# pdf_to_md_gui.py

import sys
import os
import traceback
from pathlib import Path
import json
import base64
import datetime
import hashlib
from typing import List, Dict, Optional, Tuple

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QFileDialog, QTextEdit, QLabel, QProgressBar,
    QMessageBox, QGroupBox, QCheckBox, QLineEdit, QSpinBox,
    QTabWidget, QListWidget, QListWidgetItem, QAbstractItemView,
    QComboBox, QSlider, QToolTip, QSplitter, QTextBrowser
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSettings, QTimer, QMutex, QMutexLocker
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon, QPixmap

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

# --- 增强的后台转换线程 ---
class ConversionWorker(QThread):
    log_signal = pyqtSignal(str)  # 发送日志信息
    progress_signal = pyqtSignal(int)  # 发送进度 (0-100)
    finished_signal = pyqtSignal(bool, str)  # 转换完成 (成功/失败, 消息)
    file_progress_signal = pyqtSignal(str, int, int)  # 文件进度 (文件名, 当前, 总数)
    error_signal = pyqtSignal(str, str)  # 错误信息 (文件名, 错误详情)

    def __init__(self, pdf_files, output_dir, config_dict, use_llm, llm_service_config, use_fallback_extraction=False):
        super().__init__()
        self.pdf_files = pdf_files
        self.output_dir = output_dir
        self.config_dict = config_dict
        self.use_llm = use_llm
        self.llm_service_config = llm_service_config
        self.use_fallback_extraction = use_fallback_extraction
        self._is_running = True
        self.converter = None
        self._mutex = QMutex()  # 线程安全
        self.failed_files = []  # 记录失败的文件
        self.conversion_stats = {
            'total_pages': 0,
            'total_images': 0,
            'processing_time': 0
        }

    def stop(self):
        with QMutexLocker(self._mutex):
            self._is_running = False
        if self.converter:
            # 尝试中断转换器
            pass

    def _validate_pdf(self, pdf_path: str) -> Tuple[bool, str]:
        """验证PDF文件的完整性和可读性"""
        try:
            if not os.path.exists(pdf_path):
                return False, "文件不存在"
            
            if os.path.getsize(pdf_path) == 0:
                return False, "文件大小为0"
            
            # 尝试打开PDF验证其有效性
            if PYMUPDF_AVAILABLE:
                try:
                    doc = fitz.open(pdf_path)
                    page_count = len(doc)
                    doc.close()
                    if page_count == 0:
                        return False, "PDF没有页面"
                except Exception as e:
                    return False, f"PDF损坏或无法读取: {str(e)}"
            
            return True, "OK"
        except Exception as e:
            return False, f"验证失败: {str(e)}"

    def _extract_images_with_pymupdf(self, pdf_path, images_dir):
        """使用 PyMuPDF 作为备用方案提取图片（增强版）"""
        if not PYMUPDF_AVAILABLE:
            self.log_signal.emit("  -> PyMuPDF (fitz) 未安装，无法执行备用图片提取。")
            return []
        
        try:
            pdf_document = fitz.open(pdf_path)
            extracted_files = []
            total_images = 0
            
            for page_index in range(len(pdf_document)):
                if not self._is_running:  # 检查是否需要停止
                    pdf_document.close()
                    return extracted_files
                
                page_document = pdf_document[page_index]
                image_list = page_document.get_images(full=True)
                if not image_list:
                    continue
                
                for image_index, img in enumerate(image_list):
                    total_images += 1
                    xref = img[0]
                    
                    try:
                        base_image = pdf_document.extract_image(xref)
                        if not base_image:
                            continue

                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # 生成更有意义的图片名称
                        img_hash = hashlib.md5(image_bytes).hexdigest()[:8]
                        img_name = f"page_{page_index + 1:03d}_img_{image_index + 1:02d}_{img_hash}.{image_ext}"
                        img_path = os.path.join(images_dir, img_name)
                        
                        # 避免重复保存相同的图片
                        if not os.path.exists(img_path):
                            with open(img_path, "wb") as img_file:
                                img_file.write(image_bytes)
                            extracted_files.append(img_name)
                            
                            # 记录图片大小信息
                            img_size = len(image_bytes) / 1024  # KB
                            self.log_signal.emit(f"    -> 提取图片: {img_name} ({img_size:.1f} KB)")
                    
                    except Exception as img_error:
                        self.log_signal.emit(f"    -> 警告: 提取第{page_index + 1}页第{image_index + 1}张图片失败: {img_error}")
            
            pdf_document.close()
            
            self.conversion_stats['total_images'] += len(extracted_files)
            
            if extracted_files:
                self.log_signal.emit(f"  -> [备用引擎] PyMuPDF 成功提取并保存了 {len(extracted_files)}/{total_images} 张图片。")
            else:
                self.log_signal.emit(f"  -> [备用引擎] PyMuPDF 未在该文件中找到可提取的图片。")
            
            return extracted_files

        except Exception as e:
            self.log_signal.emit(f"  -> [备用引擎] PyMuPDF 提取图片时发生错误: {e}")
            return []

    def _update_markdown_image_links(self, markdown_content, fallback_image_files, pdf_stem):
        """更新Markdown中的图片链接（增强版）"""
        import re
        
        if not fallback_image_files:
            return markdown_content
        
        # 记录已使用的图片文件
        used_images = set()
        image_replacements = []
        
        # 查找所有的图片引用模式
        image_pattern = r'!\[([^]]*)\]\(([^)]+)\)'
        
        def replace_image_link(match):
            alt_text = match.group(1)
            original_link = match.group(2)
            
            # 如果原始链接已经是相对路径或绝对路径，不修改
            if '/' in original_link or '\\' in original_link:
                return match.group(0)
            
            # 智能匹配备用图片
            best_match = self._find_best_image_match(original_link, fallback_image_files, used_images)
            
            if best_match:
                used_images.add(best_match)
                relative_path = f"{pdf_stem}_images/{best_match}"
                replacement = f'![{alt_text}]({relative_path})'
                image_replacements.append((original_link, best_match))
                return replacement
            else:
                return match.group(0)
        
        # 替换所有图片链接
        updated_content = re.sub(image_pattern, replace_image_link, markdown_content)
        
        # 记录图片替换信息
        if image_replacements:
            self.log_signal.emit(f"  -> 已更新 {len(image_replacements)} 个图片链接")
        
        # 处理未使用的图片
        unused_images = [img for img in fallback_image_files if img not in used_images]
        if unused_images:
            updated_content = self._handle_unused_images(updated_content, unused_images, pdf_stem)
        
        return updated_content

    def _find_best_image_match(self, original_link: str, fallback_images: List[str], used_images: set) -> Optional[str]:
        """智能查找最匹配的备用图片"""
        import re
        
        # 提取原始链接中的页面信息
        page_match = re.search(r'page[_\s]*(\d+)', original_link.lower())
        if page_match:
            target_page = int(page_match.group(1))
            
            # 查找对应页面的图片
            for img in fallback_images:
                if img not in used_images and f'page_{target_page:03d}_' in img:
                    return img
        
        # 如果没有页面信息，尝试其他匹配策略
        original_name_without_ext = os.path.splitext(original_link)[0]
        
        # 精确匹配
        for img in fallback_images:
            if img not in used_images and original_link == img:
                return img
        
        # 部分匹配
        for img in fallback_images:
            if img not in used_images and original_name_without_ext in img:
                return img
        
        # 返回第一个未使用的图片
        for img in fallback_images:
            if img not in used_images:
                return img
        
        return None

    def _handle_unused_images(self, content: str, unused_images: List[str], pdf_stem: str) -> str:
        """处理未使用的图片"""
        self.log_signal.emit(f"  -> 发现 {len(unused_images)} 张未在原Markdown中引用的图片")
        
        # 尝试智能插入
        content = self._insert_unused_images_intelligently(content, unused_images, pdf_stem)
        
        # 检查是否还有剩余的未使用图片
        remaining_unused = []
        for img in unused_images:
            if f"{pdf_stem}_images/{img}" not in content:
                remaining_unused.append(img)
        
        # 在文档末尾添加剩余图片
        if remaining_unused:
            content += self._append_remaining_images(remaining_unused, pdf_stem)
        
        return content

    def _insert_unused_images_intelligently(self, markdown_content, unused_images, pdf_stem):
        """智能地将未使用的图片插入到Markdown内容中（增强版）"""
        import re
        
        # 按页面顺序排序未使用的图片
        unused_images.sort(key=lambda x: self._extract_page_number(x))
        
        lines = markdown_content.split('\n')
        inserted_count = 0
        
        for img_file in unused_images[:]:  # 使用副本以便修改原列表
            page_num = self._extract_page_number(img_file)
            relative_path = f"{pdf_stem}_images/{img_file}"
            
            # 多种插入策略
            inserted = False
            
            # 策略1: 寻找页面相关的标题或内容
            patterns = [
                rf'第\s*{page_num}\s*页',
                rf'page\s*{page_num}\b',
                rf'p\.\s*{page_num}\b',
                rf'页码[:：]\s*{page_num}',
                rf'\b{page_num}\s*页'
            ]
            
            for i, line in enumerate(lines):
                for pattern in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        # 在该行后插入图片
                        insert_pos = i + 1
                        # 确保不在代码块中插入
                        if not self._is_in_code_block(lines, insert_pos):
                            lines.insert(insert_pos, f"\n![第{page_num}页图片]({relative_path})\n")
                            inserted = True
                            inserted_count += 1
                            break
                if inserted:
                    break
            
            # 策略2: 基于内容结构插入
            if not inserted:
                insert_pos = self._find_structural_insert_position(lines, page_num)
                if insert_pos >= 0:
                    lines.insert(insert_pos, f"\n![第{page_num}页图片]({relative_path})\n")
                    inserted = True
                    inserted_count += 1
        
        if inserted_count > 0:
            self.log_signal.emit(f"    -> 智能插入了 {inserted_count} 张图片")
        
        return '\n'.join(lines)

    def _is_in_code_block(self, lines: List[str], position: int) -> bool:
        """检查指定位置是否在代码块中"""
        code_block_count = 0
        for i in range(min(position, len(lines))):
            if lines[i].strip().startswith('```'):
                code_block_count += 1
        return code_block_count % 2 == 1

    def _find_structural_insert_position(self, lines: List[str], page_num: int) -> int:
        """基于文档结构查找插入位置"""
        import re
        
        # 查找所有标题位置
        headers = []
        for i, line in enumerate(lines):
            if re.match(r'^#+\s', line):
                headers.append((i, line.count('#')))
        
        if not headers:
            return -1
        
        # 根据页面号估算插入位置
        # 假设文档页面均匀分布
        total_lines = len(lines)
        estimated_position = int((page_num / 100.0) * total_lines)  # 假设最多100页
        
        # 找到最接近估算位置的标题
        best_header_pos = -1
        min_distance = float('inf')
        
        for pos, level in headers:
            distance = abs(pos - estimated_position)
            if distance < min_distance:
                min_distance = distance
                best_header_pos = pos
        
        # 在标题后插入
        if best_header_pos >= 0:
            return best_header_pos + 1
        
        return -1

    def _append_remaining_images(self, remaining_images: List[str], pdf_stem: str) -> str:
        """在文档末尾添加剩余图片"""
        self.log_signal.emit(f"  -> 在文档末尾添加剩余的 {len(remaining_images)} 张图片")
        
        content = "\n\n---\n\n## 附加图片\n\n"
        content += "*以下图片从PDF中提取但未在文档主体中引用：*\n\n"
        
        # 按页面分组
        images_by_page = {}
        for img in remaining_images:
            page_num = self._extract_page_number(img)
            if page_num not in images_by_page:
                images_by_page[page_num] = []
            images_by_page[page_num].append(img)
        
        # 按页面顺序添加
        for page_num in sorted(images_by_page.keys()):
            if len(images_by_page[page_num]) == 1:
                img = images_by_page[page_num][0]
                relative_path = f"{pdf_stem}_images/{img}"
                content += f"![第{page_num}页图片]({relative_path})\n\n"
            else:
                content += f"### 第{page_num}页图片\n\n"
                for i, img in enumerate(images_by_page[page_num], 1):
                    relative_path = f"{pdf_stem}_images/{img}"
                    content += f"![第{page_num}页图片{i}]({relative_path})\n\n"
        
        return content

    def _extract_page_number(self, img_filename):
        """从图片文件名中提取页面号（增强版）"""
        import re
        # 支持多种页面号格式
        patterns = [
            r'page_(\d+)',
            r'_page_(\d+)_',
            r'p(\d+)_',
            r'第(\d+)页'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, img_filename, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return 0

    def _create_conversion_summary(self, pdf_path: str, success: bool, error_msg: str = "") -> Dict:
        """创建转换摘要信息"""
        return {
            'file': os.path.basename(pdf_path),
            'path': pdf_path,
            'success': success,
            'error': error_msg,
            'timestamp': datetime.datetime.now().isoformat(),
            'pages': self.conversion_stats.get('total_pages', 0),
            'images': self.conversion_stats.get('total_images', 0)
        }

    def run(self):
        if not MARKER_AVAILABLE:
            self.finished_signal.emit(False, f"Marker 库未正确安装或导入: {MARKER_IMPORT_ERROR}")
            return

        if not self.pdf_files:
            self.finished_signal.emit(False, "没有 PDF 文件需要转换。")
            return

        start_time = datetime.datetime.now()
        conversion_summaries = []

        try:
            self.log_signal.emit(f"开始转换 {len(self.pdf_files)} 个 PDF 文件...")
            self.log_signal.emit(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

            # 设置自定义模型缓存目录
            try:
                main_program_dir = os.getcwd()
                custom_models_dir = os.path.join(main_program_dir, "markermodels")
                os.makedirs(custom_models_dir, exist_ok=True)
                os.environ['HF_HOME'] = main_program_dir
                self.log_signal.emit(f"已设置 HF_HOME 环境变量指向: {main_program_dir}")
                self.log_signal.emit(f"Marker 模型将从 '{custom_models_dir}' 加载/下载。")
            except Exception as env_error:
                self.log_signal.emit(f"警告: 设置自定义模型目录时出错: {env_error}")

            # 加载 Marker 模型和配置
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
            failed = 0

            for i, pdf_path in enumerate(self.pdf_files):
                if not self._is_running:
                    self.log_signal.emit("转换任务被用户中止。")
                    self.finished_signal.emit(False, "任务被中止。")
                    return

                file_start_time = datetime.datetime.now()
                self.file_progress_signal.emit(os.path.basename(pdf_path), i + 1, total_files)
                self.log_signal.emit(f"\n[{i+1}/{total_files}] 正在转换: {os.path.basename(pdf_path)}")
                self.progress_signal.emit(int((i / total_files) * 100))

                # 验证PDF文件
                is_valid, validation_msg = self._validate_pdf(pdf_path)
                if not is_valid:
                    error_msg = f"文件验证失败: {validation_msg}"
                    self.log_signal.emit(f"  -> 错误: {error_msg}")
                    self.error_signal.emit(os.path.basename(pdf_path), error_msg)
                    failed += 1
                    self.failed_files.append(pdf_path)
                    conversion_summaries.append(self._create_conversion_summary(pdf_path, False, error_msg))
                    continue

                try:
                    # 重置统计信息
                    self.conversion_stats = {
                        'total_pages': 0,
                        'total_images': 0,
                        'processing_time': 0
                    }

                    # 步骤 1: 执行PDF到Markdown的转换
                    self.log_signal.emit("  -> 正在解析PDF内容...")
                    rendered = self.converter(pdf_path)

                    # 获取页面数
                    if hasattr(rendered, 'metadata') and hasattr(rendered.metadata, 'page_count'):
                        self.conversion_stats['total_pages'] = rendered.metadata.page_count
                        self.log_signal.emit(f"  -> PDF共有 {rendered.metadata.page_count} 页")

                    # 步骤 2: 提取和保存图片
                    marker_extracted_images = False
                    pdf_stem = Path(pdf_path).stem
                    images_dir = os.path.join(self.output_dir, f"{pdf_stem}_images")
                    fallback_image_files = []
                    
                    # 策略一: 尝试使用 Marker (主引擎) 提取
                    if hasattr(rendered, 'metadata') and hasattr(rendered.metadata, 'images') and isinstance(rendered.metadata.images, dict) and rendered.metadata.images:
                        marker_extracted_images = True
                        os.makedirs(images_dir, exist_ok=True)
                        self.log_signal.emit(f"  -> [主引擎] Marker 发现 {len(rendered.metadata.images)} 张图片，正在保存...")

                        saved_count = 0
                        for img_name, img_b64_data in rendered.metadata.images.items():
                            if not self._is_running:
                                break
                            
                            img_path = os.path.join(images_dir, img_name)
                            try:
                                img_bytes = base64.b64decode(img_b64_data)
                                with open(img_path, 'wb') as img_file:
                                    img_file.write(img_bytes)
                                saved_count += 1
                                self.log_signal.emit(f"    -> 已保存图片: {img_name} ({len(img_bytes)/1024:.1f} KB)")
                            except Exception as img_save_error:
                                self.log_signal.emit(f"    -> 错误: 保存图片 '{img_name}' 失败: {img_save_error}")
                        
                        self.conversion_stats['total_images'] = saved_count
                        self.log_signal.emit(f"  -> [主引擎] 成功保存 {saved_count} 张图片")
                    
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
                        self.log_signal.emit("  -> 正在更新Markdown中的图片链接...")
                        markdown_content = self._update_markdown_image_links(markdown_content, fallback_image_files, pdf_stem)
                    
                    # 添加元数据信息到Markdown
                    metadata_header = self._create_metadata_header(pdf_path, rendered)
                    markdown_content = metadata_header + markdown_content
                    
                    # 保存Markdown文件
                    md_filename = Path(pdf_path).stem + ".md"
                    md_output_path = os.path.join(self.output_dir, md_filename)
                    with open(md_output_path, 'w', encoding='utf-8') as f:
                        f.write(markdown_content)

                    # 计算处理时间
                    file_end_time = datetime.datetime.now()
                    processing_time = (file_end_time - file_start_time).total_seconds()
                    self.conversion_stats['processing_time'] = processing_time

                    self.log_signal.emit(f"  -> 已保存: {md_filename}")
                    self.log_signal.emit(f"  -> 处理时间: {processing_time:.2f} 秒")
                    successful += 1
                    
                    conversion_summaries.append(self._create_conversion_summary(pdf_path, True))

                except Exception as e:
                    error_msg = f"转换失败: {str(e)}"
                    self.log_signal.emit(f"  -> 错误: {error_msg}")
                    self.log_signal.emit(f"  -> 详细错误:\n{traceback.format_exc()}")
                    self.error_signal.emit(os.path.basename(pdf_path), error_msg)
                    failed += 1
                    self.failed_files.append(pdf_path)
                    conversion_summaries.append(self._create_conversion_summary(pdf_path, False, error_msg))

            # 生成转换报告
            end_time = datetime.datetime.now()
            total_time = (end_time - start_time).total_seconds()
            
            self.progress_signal.emit(100)
            self._generate_conversion_report(conversion_summaries, successful, failed, total_time)
            
            if failed > 0:
                self.finished_signal.emit(True, f"转换完成! 成功: {successful}/{total_files}, 失败: {failed}")
            else:
                self.finished_signal.emit(True, f"转换完成! 成功: {successful}/{total_files}")

        except Exception as e:
            self.log_signal.emit(f"严重错误: {e}")
            self.log_signal.emit(traceback.format_exc())
            self.finished_signal.emit(False, f"转换因严重错误失败: {e}")

    def _create_metadata_header(self, pdf_path: str, rendered) -> str:
        """创建包含元数据的Markdown头部"""
        header = "---\n"
        header += f"source: {os.path.basename(pdf_path)}\n"
        header += f"converted: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if hasattr(rendered, 'metadata'):
            if hasattr(rendered.metadata, 'page_count'):
                header += f"pages: {rendered.metadata.page_count}\n"
            if hasattr(rendered.metadata, 'title') and rendered.metadata.title:
                header += f"title: {rendered.metadata.title}\n"
            if hasattr(rendered.metadata, 'author') and rendered.metadata.author:
                header += f"author: {rendered.metadata.author}\n"
        
        header += "---\n\n"
        return header

    def _generate_conversion_report(self, summaries: List[Dict], successful: int, failed: int, total_time: float):
        """生成详细的转换报告"""
        report_path = os.path.join(self.output_dir, f"conversion_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        
        try:
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write("PDF转换报告\n")
                f.write("=" * 60 + "\n\n")
                f.write(f"转换时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"总耗时: {total_time:.2f} 秒\n")
                f.write(f"文件总数: {len(summaries)}\n")
                f.write(f"成功: {successful}\n")
                f.write(f"失败: {failed}\n\n")
                
                if successful > 0:
                    f.write("成功转换的文件:\n")
                    f.write("-" * 40 + "\n")
                    for summary in summaries:
                        if summary['success']:
                            f.write(f"  - {summary['file']}\n")
                            if summary['pages'] > 0:
                                f.write(f"    页数: {summary['pages']}\n")
                            if summary['images'] > 0:
                                f.write(f"    图片: {summary['images']}\n")
                    f.write("\n")
                
                if failed > 0:
                    f.write("失败的文件:\n")
                    f.write("-" * 40 + "\n")
                    for summary in summaries:
                        if not summary['success']:
                            f.write(f"  - {summary['file']}\n")
                            f.write(f"    错误: {summary['error']}\n")
                    f.write("\n")
            
            self.log_signal.emit(f"\n转换报告已保存到: {report_path}")
            
        except Exception as e:
            self.log_signal.emit(f"保存转换报告失败: {e}")


# --- 增强的主窗口 ---
class PDFToMdApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('PDF to Markdown 批量转换器 (基于 Marker) v2.0')
        self.setGeometry(100, 100, 1200, 800)
        
        # 检查依赖
        if not MARKER_AVAILABLE:
            QMessageBox.critical(self, "依赖错误", 
                f"无法导入 Marker 库。请确保已安装 'marker-pdf[full]'。\n"
                f"错误信息: {MARKER_IMPORT_ERROR}\n\n"
                f"请运行: pip install marker-pdf[full]")
            sys.exit(1)

        self.settings = QSettings("MyCompany", "PDFToMdApp")
        self.pdf_files = []
        self.worker_thread = None
        self.conversion_history = []  # 转换历史记录
        self.init_ui()
        self.load_settings()
        self.setup_shortcuts()

    def init_ui(self):
        main_layout = QVBoxLayout()
        
        # 添加工具栏样式的顶部区域
        self.create_toolbar_area(main_layout)

        # 使用分割器创建主要内容区域
        splitter = QSplitter(Qt.Vertical)

        # --- 文件选择区域 ---
        file_group = QGroupBox("1. 选择 PDF 文件")
        file_layout = QVBoxLayout()
        
        # 文件操作按钮
        file_btn_layout = QHBoxLayout()
        
        self.btn_select_files = QPushButton("📄 选择 PDF 文件")
        self.btn_select_files.setToolTip("选择一个或多个PDF文件 (Ctrl+O)")
        self.btn_select_files.clicked.connect(self.select_files)
        
        self.btn_select_folder = QPushButton("📁 选择文件夹")
        self.btn_select_folder.setToolTip("选择包含PDF文件的文件夹")
        self.btn_select_folder.clicked.connect(self.select_folder)
        
        self.btn_remove_selected = QPushButton("➖ 移除选中")
        self.btn_remove_selected.setToolTip("移除选中的文件 (Delete)")
        self.btn_remove_selected.clicked.connect(self.remove_selected_files)
        
        self.btn_clear_list = QPushButton("🗑️ 清空列表")
        self.btn_clear_list.setToolTip("清空所有文件")
        self.btn_clear_list.clicked.connect(self.clear_file_list)
        
        file_btn_layout.addWidget(self.btn_select_files)
        file_btn_layout.addWidget(self.btn_select_folder)
        file_btn_layout.addWidget(self.btn_remove_selected)
        file_btn_layout.addWidget(self.btn_clear_list)
        file_btn_layout.addStretch()
        
        # 文件列表
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setAlternatingRowColors(True)  # 交替行颜色
        self.list_widget.itemDoubleClicked.connect(self.preview_pdf)
        
        # 文件统计标签
        self.file_stats_label = QLabel("未选择文件")
        
        file_layout.addLayout(file_btn_layout)
        file_layout.addWidget(self.list_widget)
        file_layout.addWidget(self.file_stats_label)
        file_group.setLayout(file_layout)
        
        # --- 配置和输出区域 ---
        config_output_widget = QWidget()
        config_output_layout = QHBoxLayout()
        
        # --- 配置选项卡 ---
        self.tabs = QTabWidget()
        
        # 基础设置
        self.create_basic_tab()
        
        # LLM 设置
        self.create_llm_tab()
        
        # 高级设置
        self.create_advanced_tab()
        
        # 预设配置
        self.create_presets_tab()
        
        # --- 操作按钮 ---
        self.action_group = QGroupBox("3. 操作")
        action_layout = QVBoxLayout()
        
        self.btn_start = QPushButton("🚀 开始转换")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.btn_start.clicked.connect(self.start_conversion)
        
        self.btn_stop = QPushButton("⏹ 停止")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.btn_stop.clicked.connect(self.stop_conversion)
        self.btn_stop.setEnabled(False)
        
        # 添加批处理选项
        self.batch_options_group = QGroupBox("批处理选项")
        batch_layout = QVBoxLayout()
        
        self.auto_open_output_cb = QCheckBox("转换完成后自动打开输出文件夹")
        self.auto_open_output_cb.setChecked(True)
        
        self.create_subfolder_cb = QCheckBox("为每个PDF创建子文件夹")
        self.create_subfolder_cb.setToolTip("在输出目录中为每个PDF文件创建独立的子文件夹")
        
        batch_layout.addWidget(self.auto_open_output_cb)
        batch_layout.addWidget(self.create_subfolder_cb)
        self.batch_options_group.setLayout(batch_layout)
        
        action_layout.addWidget(self.btn_start)
        action_layout.addWidget(self.btn_stop)
        action_layout.addWidget(self.batch_options_group)
        action_layout.addStretch()
        self.action_group.setLayout(action_layout)

        config_output_layout.addWidget(self.tabs, 3)
        config_output_layout.addWidget(self.action_group, 1)
        config_output_widget.setLayout(config_output_layout)
        
        # 添加到分割器
        splitter.addWidget(file_group)
        splitter.addWidget(config_output_widget)
        
        # --- 进度和日志 ---
        progress_log_widget = self.create_progress_log_widget()
        splitter.addWidget(progress_log_widget)
        
        # 设置分割器比例
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 3)
        
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    def create_toolbar_area(self, parent_layout):
        """创建工具栏区域"""
        toolbar_widget = QWidget()
        toolbar_widget.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                border-bottom: 1px solid #cccccc;
            }
        """)
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(10, 5, 10, 5)
        
        # Logo/标题
        title_label = QLabel("PDF → Markdown 转换器")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        
        # 快速操作按钮
        self.btn_quick_convert = QPushButton("⚡ 快速转换")
        self.btn_quick_convert.setToolTip("使用默认设置快速转换")
        self.btn_quick_convert.clicked.connect(self.quick_convert)
        
        self.btn_history = QPushButton("📋 历史记录")
        self.btn_history.setToolTip("查看转换历史")
        self.btn_history.clicked.connect(self.show_history)
        
        self.btn_help = QPushButton("❓ 帮助")
        self.btn_help.clicked.connect(self.show_help)
        
        toolbar_layout.addWidget(title_label)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.btn_quick_convert)
        toolbar_layout.addWidget(self.btn_history)
        toolbar_layout.addWidget(self.btn_help)
        
        toolbar_widget.setLayout(toolbar_layout)
        parent_layout.addWidget(toolbar_widget)

    def create_basic_tab(self):
        """创建基础设置标签页"""
        self.basic_tab = QWidget()
        basic_layout = QFormLayout()
        
        # 输出目录
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("选择输出目录")
        self.btn_browse_output = QPushButton("浏览...")
        self.btn_browse_output.clicked.connect(self.browse_output_dir)
        
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(self.btn_browse_output)
        basic_layout.addRow("输出目录:", output_dir_layout)

        # 页码范围
        self.page_range_edit = QLineEdit()
        self.page_range_edit.setPlaceholderText("例如: 1-5,8,10-15 (留空为全部)")
        self.page_range_edit.setToolTip("支持多种格式：1-5（范围）、1,3,5（单页）、混合使用")
        basic_layout.addRow("页码范围:", self.page_range_edit)

        # 基本选项
        self.format_lines_cb = QCheckBox("格式化行 (改善数学公式)")
        self.format_lines_cb.setToolTip("优化文本行的格式，特别适合包含数学公式的文档")
        
        self.force_ocr_cb = QCheckBox("强制 OCR")
        self.force_ocr_cb.setToolTip("即使PDF包含文本层，也强制使用OCR重新识别")
        
        self.strip_existing_ocr_cb = QCheckBox("移除现有 OCR 文本")
        self.strip_existing_ocr_cb.setToolTip("在处理前移除PDF中已有的OCR文本层")
        
        basic_layout.addRow(self.format_lines_cb)
        basic_layout.addRow(self.force_ocr_cb)
        basic_layout.addRow(self.strip_existing_ocr_cb)
        
        # 添加语言选择
        language_layout = QHBoxLayout()
        self.language_label = QLabel("OCR语言:")
        self.language_combo = QComboBox()
        self.language_combo.addItems(["自动检测", "中文+英文", "仅中文", "仅英文", "日文", "韩文"])
        self.language_combo.setToolTip("选择OCR识别的语言")
        language_layout.addWidget(self.language_label)
        language_layout.addWidget(self.language_combo)
        language_layout.addStretch()
        basic_layout.addRow(language_layout)

        self.basic_tab.setLayout(basic_layout)
        self.tabs.addTab(self.basic_tab, "基础设置")

    def create_llm_tab(self):
        """创建LLM设置标签页"""
        self.llm_tab = QWidget()
        llm_layout = QFormLayout()
        
        # LLM启用选项
        self.use_llm_cb = QCheckBox("使用 LLM 提高准确性")
        self.use_llm_cb.setToolTip("使用大语言模型来改善转换质量，特别是对于复杂布局的文档")
        self.use_llm_cb.stateChanged.connect(self.toggle_llm_options)
        llm_layout.addRow(self.use_llm_cb)

        # LLM服务选择
        self.llm_service_combo = QComboBox()
        self.llm_service_combo.addItems(["OpenAI", "Ollama", "Gemini", "Claude", "Azure OpenAI", "LM Studio"])
        self.llm_service_combo.currentTextChanged.connect(self.on_llm_service_changed)
        llm_layout.addRow("LLM 服务:", self.llm_service_combo)

        # API密钥
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("输入API密钥")
        
        self.btn_show_api_key = QPushButton("👁")
        self.btn_show_api_key.setMaximumWidth(30)
        self.btn_show_api_key.setCheckable(True)
        self.btn_show_api_key.toggled.connect(self.toggle_api_key_visibility)
        
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(self.api_key_edit)
        api_key_layout.addWidget(self.btn_show_api_key)
        llm_layout.addRow("API 密钥:", api_key_layout)

        # Base URL
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("例如: https://api.openai.com/v1")
        llm_layout.addRow("Base URL:", self.base_url_edit)

        # 模型名称
        self.model_name_edit = QLineEdit()
        self.model_name_edit.setPlaceholderText("例如: gpt-4, llama3, gemini-pro")
        llm_layout.addRow("模型名称:", self.model_name_edit)

        # 添加测试连接按钮
        self.btn_test_llm = QPushButton("🔌 测试连接")
        self.btn_test_llm.clicked.connect(self.test_llm_connection)
        llm_layout.addRow("", self.btn_test_llm)

        # LLM高级选项
        llm_advanced_group = QGroupBox("LLM 高级选项")
        llm_advanced_layout = QFormLayout()
        
        self.temperature_slider = QSlider(Qt.Horizontal)
        self.temperature_slider.setRange(0, 100)
        self.temperature_slider.setValue(30)
        self.temperature_slider.setTickPosition(QSlider.TicksBelow)
        self.temperature_slider.setTickInterval(10)
        self.temperature_label = QLabel("0.3")
        self.temperature_slider.valueChanged.connect(lambda v: self.temperature_label.setText(f"{v/100:.1f}"))
        
        temp_layout = QHBoxLayout()
        temp_layout.addWidget(self.temperature_slider)
        temp_layout.addWidget(self.temperature_label)
        llm_advanced_layout.addRow("Temperature:", temp_layout)
        
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(100, 8000)
        self.max_tokens_spin.setValue(2000)
        self.max_tokens_spin.setSingleStep(100)
        llm_advanced_layout.addRow("Max Tokens:", self.max_tokens_spin)
        
        llm_advanced_group.setLayout(llm_advanced_layout)
        llm_layout.addRow(llm_advanced_group)

        self.llm_tab.setLayout(llm_layout)
        self.tabs.addTab(self.llm_tab, "LLM 设置")
        self.toggle_llm_options(Qt.Unchecked)

    def create_advanced_tab(self):
        """创建高级设置标签页"""
        self.advanced_tab = QWidget()
        advanced_layout = QFormLayout()
        
        # 输出格式
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["markdown", "json", "html", "chunks"])
        self.output_format_combo.setToolTip("选择输出文件的格式")
        advanced_layout.addRow("输出格式:", self.output_format_combo)

        # 调试模式
        self.debug_cb = QCheckBox("启用调试模式")
        self.debug_cb.setToolTip("输出详细的调试信息")
        advanced_layout.addRow(self.debug_cb)

        # 工作进程数
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 16)
        self.workers_spin.setValue(4)
        self.workers_spin.setToolTip("并行处理的工作进程数")
        advanced_layout.addRow("工作进程数:", self.workers_spin)

        # 备用图片提取
        self.fallback_image_extraction_cb = QCheckBox("启用 PyMuPDF 作为备用图片提取引擎")
        self.fallback_image_extraction_cb.setToolTip(
            "当 Marker 未能提取出图片时，自动尝试使用 PyMuPDF 进行二次提取。\n"
            "可以解决某些特殊PDF图片无法导出的问题。"
        )
        self.fallback_image_extraction_cb.setChecked(True)
        advanced_layout.addRow(self.fallback_image_extraction_cb)

        # 图片处理选项
        image_group = QGroupBox("图片处理选项")
        image_layout = QFormLayout()
        
        self.compress_images_cb = QCheckBox("压缩提取的图片")
        self.compress_images_cb.setToolTip("减小图片文件大小")
        
        self.image_quality_spin = QSpinBox()
        self.image_quality_spin.setRange(10, 100)
        self.image_quality_spin.setValue(85)
        self.image_quality_spin.setSuffix("%")
        self.image_quality_spin.setEnabled(False)
        self.compress_images_cb.toggled.connect(self.image_quality_spin.setEnabled)
        
        image_layout.addRow(self.compress_images_cb)
        image_layout.addRow("图片质量:", self.image_quality_spin)
        
        self.extract_image_metadata_cb = QCheckBox("提取图片元数据")
        self.extract_image_metadata_cb.setToolTip("保存图片的尺寸、格式等信息")
        image_layout.addRow(self.extract_image_metadata_cb)
        
        image_group.setLayout(image_layout)
        advanced_layout.addRow(image_group)

        # 性能优化选项
        performance_group = QGroupBox("性能优化")
        performance_layout = QFormLayout()
        
        self.cache_models_cb = QCheckBox("缓存模型到本地")
        self.cache_models_cb.setChecked(True)
        self.cache_models_cb.setToolTip("首次下载后缓存模型，加快后续启动速度")
        
        self.low_memory_mode_cb = QCheckBox("低内存模式")
        self.low_memory_mode_cb.setToolTip("适用于内存较小的系统，但可能降低处理速度")
        
        performance_layout.addRow(self.cache_models_cb)
        performance_layout.addRow(self.low_memory_mode_cb)
        
        performance_group.setLayout(performance_layout)
        advanced_layout.addRow(performance_group)

        self.advanced_tab.setLayout(advanced_layout)
        self.tabs.addTab(self.advanced_tab, "高级设置")

    def create_presets_tab(self):
        """创建预设配置标签页"""
        self.presets_tab = QWidget()
        presets_layout = QVBoxLayout()
        
        # 预设说明
        info_label = QLabel("选择预设配置以快速设置适合特定类型文档的参数：")
        info_label.setWordWrap(True)
        presets_layout.addWidget(info_label)
        
        # 预设列表
        self.presets_list = QListWidget()
        self.presets_list.itemDoubleClicked.connect(self.apply_preset)
        
        # 添加预设
        presets = [
            ("📚 学术论文", "适合包含公式、图表的学术文档"),
            ("📊 技术报告", "适合包含代码、表格的技术文档"),
            ("📖 电子书", "适合纯文本为主的书籍"),
            ("🖼️ 扫描文档", "适合扫描版PDF，强制OCR"),
            ("⚡ 快速转换", "最快速度，适合简单文档"),
            ("🎯 高精度", "最高质量，适合复杂布局"),
        ]
        
        for name, desc in presets:
            item = QListWidgetItem(name)
            item.setToolTip(desc)
            self.presets_list.addItem(item)
        
        # 预设操作按钮
        preset_btn_layout = QHBoxLayout()
        self.btn_apply_preset = QPushButton("应用预设")
        self.btn_apply_preset.clicked.connect(self.apply_preset)
        
        self.btn_save_preset = QPushButton("保存当前设置为预设")
        self.btn_save_preset.clicked.connect(self.save_custom_preset)
        
        preset_btn_layout.addWidget(self.btn_apply_preset)
        preset_btn_layout.addWidget(self.btn_save_preset)
        preset_btn_layout.addStretch()
        
        presets_layout.addWidget(self.presets_list)
        presets_layout.addLayout(preset_btn_layout)
        
        self.presets_tab.setLayout(presets_layout)
        self.tabs.addTab(self.presets_tab, "预设配置")

    def create_progress_log_widget(self):
        """创建进度和日志部件"""
        progress_log_widget = QWidget()
        progress_log_layout = QVBoxLayout()
        
        # 进度信息
        progress_info_layout = QHBoxLayout()
        self.current_file_label = QLabel("等待开始...")
        self.progress_detail_label = QLabel("")
        progress_info_layout.addWidget(self.current_file_label)
        progress_info_layout.addStretch()
        progress_info_layout.addWidget(self.progress_detail_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        
        # 日志区域
        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout()
        
        # 使用QTextBrowser支持富文本
        self.log_text = QTextBrowser()
        self.log_text.setReadOnly(True)
        self.log_text.setOpenExternalLinks(True)
        
        # 设置日志样式
        log_font = QFont("Consolas", 9)
        self.log_text.setFont(log_font)
        self.log_text.setStyleSheet("""
            QTextBrowser {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        
        # 日志操作按钮
        log_btn_layout = QHBoxLayout()
        
        self.btn_save_log = QPushButton("💾 保存日志")
        self.btn_save_log.clicked.connect(self.save_log)
        
        self.btn_clear_log = QPushButton("🗑️ 清空日志")
        self.btn_clear_log.clicked.connect(self.clear_log)
        
        self.btn_copy_log = QPushButton("📋 复制日志")
        self.btn_copy_log.clicked.connect(self.copy_log)
        
        # 日志过滤
        self.log_filter_combo = QComboBox()
        self.log_filter_combo.addItems(["所有日志", "仅错误", "仅警告", "仅信息"])
        self.log_filter_combo.currentTextChanged.connect(self.filter_log)
        
        log_btn_layout.addWidget(QLabel("过滤:"))
        log_btn_layout.addWidget(self.log_filter_combo)
        log_btn_layout.addStretch()
        log_btn_layout.addWidget(self.btn_copy_log)
        log_btn_layout.addWidget(self.btn_save_log)
        log_btn_layout.addWidget(self.btn_clear_log)
        
        log_layout.addWidget(self.log_text)
        log_layout.addLayout(log_btn_layout)
        log_group.setLayout(log_layout)
        
        progress_log_layout.addLayout(progress_info_layout)
        progress_log_layout.addWidget(self.progress_bar)
        progress_log_layout.addWidget(log_group)
        progress_log_widget.setLayout(progress_log_layout)
        
        return progress_log_widget

    def setup_shortcuts(self):
        """设置快捷键"""
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        
        # Ctrl+O: 打开文件
        QShortcut(QKeySequence("Ctrl+O"), self, self.select_files)
        
        # Ctrl+S: 开始转换
        QShortcut(QKeySequence("Ctrl+S"), self, self.start_conversion)
        
        # Delete: 删除选中文件
        QShortcut(QKeySequence("Delete"), self.list_widget, self.remove_selected_files)
        
        # F1: 显示帮助
        QShortcut(QKeySequence("F1"), self, self.show_help)
        
        # Ctrl+Q: 退出
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)

    def toggle_llm_options(self, state):
        """切换LLM选项的启用状态"""
        enabled = state == Qt.Checked
        self.llm_service_combo.setEnabled(enabled)
        self.api_key_edit.setEnabled(enabled)
        self.base_url_edit.setEnabled(enabled)
        self.model_name_edit.setEnabled(enabled)
        self.btn_test_llm.setEnabled(enabled)
        self.btn_show_api_key.setEnabled(enabled)
        self.temperature_slider.setEnabled(enabled)
        self.max_tokens_spin.setEnabled(enabled)
        
    def on_llm_service_changed(self, service):
        """LLM服务变更时更新UI"""
        if service == "Ollama":
            self.api_key_edit.setEnabled(False)
            self.api_key_edit.setPlaceholderText("Ollama不需要API密钥")
            self.base_url_edit.setText("http://localhost:11434")
            self.model_name_edit.setPlaceholderText("例如: llama3, mistral, qwen")
        elif service == "LM Studio":
            self.api_key_edit.setEnabled(False)
            self.api_key_edit.setPlaceholderText("LM Studio不需要API密钥")
            self.base_url_edit.setText("http://localhost:1234/v1")
            self.model_name_edit.setPlaceholderText("例如: local-model")
        elif service == "OpenAI":
            self.api_key_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("输入OpenAI API密钥")
            self.base_url_edit.setText("https://api.openai.com/v1")
            self.model_name_edit.setPlaceholderText("例如: gpt-4, gpt-3.5-turbo")
        elif service == "Claude":
            self.api_key_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("输入Anthropic API密钥")
            self.base_url_edit.setText("")
            self.model_name_edit.setPlaceholderText("例如: claude-3-opus, claude-3-sonnet")
        elif service == "Gemini":
            self.api_key_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("输入Google API密钥")
            self.base_url_edit.setText("")
            self.model_name_edit.setPlaceholderText("例如: gemini-pro, gemini-flash")
        elif service == "Azure OpenAI":
            self.api_key_edit.setEnabled(True)
            self.api_key_edit.setPlaceholderText("输入Azure API密钥")
            self.base_url_edit.setPlaceholderText("https://YOUR-RESOURCE.openai.azure.com/")
            self.model_name_edit.setPlaceholderText("输入部署名称")

    def toggle_api_key_visibility(self, checked):
        """切换API密钥可见性"""
        if checked:
            self.api_key_edit.setEchoMode(QLineEdit.Normal)
            self.btn_show_api_key.setText("🙈")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.Password)
            self.btn_show_api_key.setText("👁")

    def test_llm_connection(self):
        """测试LLM连接"""
        # 这里可以实现实际的连接测试
        QMessageBox.information(self, "测试连接", "LLM连接测试功能将在后续版本中实现。")

    def select_files(self):
        """选择PDF文件"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择 PDF 文件", 
            self.settings.value("last_open_dir", ""), 
            "PDF Files (*.pdf);;All Files (*.*)"
        )
        if file_paths:
            self.add_files_to_list(file_paths)
            # 保存最后打开的目录
            if file_paths:
                self.settings.setValue("last_open_dir", os.path.dirname(file_paths[0]))

    def select_folder(self):
        """选择包含PDF的文件夹"""
        folder_path = QFileDialog.getExistingDirectory(
            self, "选择包含 PDF 的文件夹",
            self.settings.value("last_folder_dir", "")
        )
        if folder_path:
            self.settings.setValue("last_folder_dir", folder_path)
            pdf_files = []
            
            # 递归搜索PDF文件
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith('.pdf'):
                        pdf_files.append(os.path.join(root, file))
            
            if pdf_files:
                self.add_files_to_list(pdf_files)
                self.log(f"从文件夹 '{folder_path}' 中找到 {len(pdf_files)} 个PDF文件。")
            else:
                QMessageBox.information(self, "信息", "所选文件夹中未找到 PDF 文件。")

    def add_files_to_list(self, file_paths):
        """添加文件到列表"""
        current_files = set(self.pdf_files)
        new_files = []
        
        for fp in file_paths:
            if fp not in current_files:
                # 获取文件信息
                file_info = self.get_file_info(fp)
                
                self.pdf_files.append(fp)
                item = QListWidgetItem(f"{file_info['name']} ({file_info['size_str']})")
                item.setToolTip(f"路径: {fp}\n大小: {file_info['size_str']}\n修改时间: {file_info['modified']}")
                item.setData(Qt.UserRole, fp)  # 存储完整路径
                
                # 根据文件大小设置不同的图标颜色
                if file_info['size_mb'] > 50:
                    item.setForeground(QColor("#ff6b6b"))  # 大文件用红色
                elif file_info['size_mb'] > 10:
                    item.setForeground(QColor("#ffa94d"))  # 中等文件用橙色
                
                self.list_widget.addItem(item)
                new_files.append(fp)
        
        if new_files:
            self.log(f"已添加 {len(new_files)} 个新文件到列表。")
            self.update_file_stats()

    def get_file_info(self, file_path):
        """获取文件信息"""
        try:
            stat = os.stat(file_path)
            size_bytes = stat.st_size
            size_mb = size_bytes / (1024 * 1024)
            
            if size_mb < 1:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_mb:.1f} MB"
            
            modified_time = datetime.datetime.fromtimestamp(stat.st_mtime)
            
            return {
                'name': os.path.basename(file_path),
                'size_bytes': size_bytes,
                'size_mb': size_mb,
                'size_str': size_str,
                'modified': modified_time.strftime('%Y-%m-%d %H:%M:%S')
            }
        except:
            return {
                'name': os.path.basename(file_path),
                'size_bytes': 0,
                'size_mb': 0,
                'size_str': '未知',
                'modified': '未知'
            }

    def update_file_stats(self):
        """更新文件统计信息"""
        total_files = len(self.pdf_files)
        if total_files == 0:
            self.file_stats_label.setText("未选择文件")
        else:
            total_size = sum(self.get_file_info(fp)['size_mb'] for fp in self.pdf_files)
            self.file_stats_label.setText(f"共 {total_files} 个文件，总大小: {total_size:.1f} MB")

    def remove_selected_files(self):
        """移除选中的文件"""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
        
        # 确认删除
        if len(selected_items) > 1:
            reply = QMessageBox.question(
                self, '确认删除', 
                f'确定要从列表中移除 {len(selected_items)} 个文件吗？',
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        
        for item in selected_items:
            row = self.list_widget.row(item)
            file_path = self.pdf_files.pop(row)
            self.list_widget.takeItem(row)
            self.log(f"已从列表移除: {os.path.basename(file_path)}")
        
        self.update_file_stats()

    def clear_file_list(self):
        """清空文件列表"""
        if self.pdf_files:
            reply = QMessageBox.question(
                self, '确认清空', 
                '确定要清空所有文件吗？',
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.pdf_files.clear()
                self.list_widget.clear()
                self.log("文件列表已清空。")
                self.update_file_stats()

    def preview_pdf(self, item):
        """预览PDF文件（双击时）"""
        file_path = item.data(Qt.UserRole)
        if file_path and os.path.exists(file_path):
            # 使用系统默认程序打开PDF
            import subprocess
            import platform
            
            try:
                if platform.system() == 'Windows':
                    os.startfile(file_path)
                elif platform.system() == 'Darwin':  # macOS
                    subprocess.run(['open', file_path])
                else:  # Linux
                    subprocess.run(['xdg-open', file_path])
            except Exception as e:
                QMessageBox.warning(self, "打开失败", f"无法打开文件: {e}")

    def browse_output_dir(self):
        """浏览输出目录"""
        current_dir = self.output_dir_edit.text() or self.settings.value("last_output_dir", "")
        dir_path = QFileDialog.getExistingDirectory(self, "选择输出目录", current_dir)
        if dir_path:
            self.output_dir_edit.setText(dir_path)
            self.settings.setValue("last_output_dir", dir_path)

    def apply_preset(self, item=None):
        """应用预设配置"""
        if not item:
            item = self.presets_list.currentItem()
        
        if not item:
            return
        
        preset_name = item.text()
        
        # 预设配置映射
        presets = {
            "📚 学术论文": {
                'format_lines': True,
                'force_ocr': False,
                'use_llm': True,
                'output_format': 'markdown',
                'fallback_extraction': True,
                'language': '中文+英文'
            },
            "📊 技术报告": {
                'format_lines': False,
                'force_ocr': False,
                'use_llm': False,
                'output_format': 'markdown',
                'fallback_extraction': True,
                'language': '中文+英文'
            },
            "📖 电子书": {
                'format_lines': True,
                'force_ocr': False,
                'use_llm': False,
                'output_format': 'markdown',
                'fallback_extraction': False,
                'language': '自动检测'
            },
            "🖼️ 扫描文档": {
                'format_lines': True,
                'force_ocr': True,
                'use_llm': True,
                'output_format': 'markdown',
                'fallback_extraction': True,
                'language': '中文+英文'
            },
            "⚡ 快速转换": {
                'format_lines': False,
                'force_ocr': False,
                'use_llm': False,
                'output_format': 'markdown',
                'fallback_extraction': False,
                'language': '自动检测'
            },
            "🎯 高精度": {
                'format_lines': True,
                'force_ocr': False,
                'use_llm': True,
                'output_format': 'markdown',
                'fallback_extraction': True,
                'language': '中文+英文'
            }
        }
        
        if preset_name in presets:
            config = presets[preset_name]
            
            # 应用配置
            self.format_lines_cb.setChecked(config.get('format_lines', False))
            self.force_ocr_cb.setChecked(config.get('force_ocr', False))
            self.use_llm_cb.setChecked(config.get('use_llm', False))
            self.output_format_combo.setCurrentText(config.get('output_format', 'markdown'))
            self.fallback_image_extraction_cb.setChecked(config.get('fallback_extraction', True))
            
            # 设置语言
            language_index = self.language_combo.findText(config.get('language', '自动检测'))
            if language_index >= 0:
                self.language_combo.setCurrentIndex(language_index)
            
            self.log(f"已应用预设配置: {preset_name}")
            QMessageBox.information(self, "预设应用", f"已应用预设配置: {preset_name}")

    def save_custom_preset(self):
        """保存自定义预设"""
        # 这里可以实现保存自定义预设的功能
        QMessageBox.information(self, "保存预设", "自定义预设保存功能将在后续版本中实现。")

    def quick_convert(self):
        """快速转换（使用默认设置）"""
        if not self.pdf_files:
            QMessageBox.warning(self, "警告", "请先选择要转换的PDF文件。")
            return
        
        # 应用快速转换预设
        quick_preset = self.presets_list.findItems("⚡ 快速转换", Qt.MatchExactly)
        if quick_preset:
            self.apply_preset(quick_preset[0])
        
        # 开始转换
        self.start_conversion()

    def show_history(self):
        """显示转换历史"""
        history_dialog = QMessageBox(self)
        history_dialog.setWindowTitle("转换历史")
        history_dialog.setText("转换历史功能将在后续版本中实现。")
        history_dialog.setDetailedText("将显示最近的转换记录，包括文件名、转换时间、状态等信息。")
        history_dialog.exec_()

    def show_help(self):
        """显示帮助信息"""
        help_text = """
        <h2>PDF to Markdown 转换器使用帮助</h2>
        
        <h3>快捷键：</h3>

        <ul>
            <li><b>Ctrl+O:</b> 选择PDF文件</li>
            <li><b>Ctrl+S:</b> 开始转换</li>
            <li><b>Delete:</b> 从列表中移除选中的文件</li>
            <li><b>F1:</b> 显示此帮助信息</li>
            <li><b>Ctrl+Q:</b> 退出程序</li>
        </ul>

        <h3>功能说明：</h3>
        <p><b>1. 文件选择:</b><br>
        - "选择PDF文件"或"选择文件夹"来添加文件。<br>
        - 双击列表中的文件可以用系统默认程序打开预览。<br>
        - 使用 "移除选中" 或 "清空列表" 管理文件。</p>

        <p><b>2. 配置:</b><br>
        - <b>基础设置:</b> 配置输出目录、页码、OCR等基本选项。<br>
        - <b>LLM设置:</b> (可选) 启用大语言模型以提高复杂文档的转换质量。<br>
        - <b>高级设置:</b> 配置输出格式、备用图片提取等高级功能。<br>
        - <b>预设配置:</b> 为不同类型的文档（如学术论文、扫描件）快速应用推荐设置。</p>

        <p><b>3. 开始转换:</b><br>
        - 配置完成后，点击 "开始转换" 按钮。<br>
        - 转换过程中可以随时点击 "停止" 来中止任务。</p>
        
        <h3>提示：</h3>
        <p>- "快速转换" 按钮会使用默认的优化设置来处理您已选择的文件。<br>
        - "启用PyMuPDF作为备用图片提取引擎" 选项可以显著提高图片提取的成功率，建议保持开启。</p>
        """
        QMessageBox.information(self, "帮助", help_text)

    def log(self, message, level="INFO"):
        """增强的日志记录功能，支持级别和颜色"""
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        
        color_map = {
            "INFO": "#333333",    # 默认黑色
            "SUCCESS": "#28a745", # 绿色
            "ERROR": "#dc3545",   # 红色
            "WARN": "#ffc107",    # 黄色
            "DEBUG": "#6c757d",   # 灰色
        }
        
        html_message = f'<span style="color: {color_map.get(level, "#333333")};"><b>[{timestamp} {level}]</b> {message}</span>'
        
        # 存储原始日志以供过滤
        # 这里不应该使用setMetaInformation，而是直接追加日志
        pass

        # 使用HTML追加到QTextBrowser
        self.log_text.append(html_message)
        self.log_text.moveCursor(self.log_text.textCursor().End)
        QApplication.processEvents() # 确保UI及时更新

    def filter_log(self, filter_text):
        """根据选择过滤日志显示"""
        # (此功能较为复杂，暂提供一个简单的思路实现)
        QMessageBox.information(self, "功能说明", f"日志过滤功能 ({filter_text}) 正在开发中。")

    def copy_log(self):
        """复制日志到剪贴板"""
        self.log_text.selectAll()
        self.log_text.copy()
        cursor = self.log_text.textCursor()
        cursor.clearSelection()
        self.log_text.setTextCursor(cursor)
        self.log("日志内容已复制到剪贴板。", "INFO")
        
    def save_log(self):
        """保存日志文件"""
        log_content = self.log_text.toPlainText()
        if not log_content:
            QMessageBox.information(self, "信息", "日志为空。")
            return
        
        default_filename = f"conversion_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path, _ = QFileDialog.getSaveFileName(self, "保存日志", default_filename, "Text Files (*.txt);;All Files (*.*)")
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                self.log(f"日志已成功保存到: {file_path}", "SUCCESS")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"保存日志失败: {e}")
                self.log(f"保存日志失败: {e}", "ERROR")

    def clear_log(self):
        """清空日志显示"""
        self.log_text.clear()

    def get_config_dict(self):
        """获取基础配置字典"""
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
        # worker进程数现在是Marker内部处理，UI的设置可以作为参考或传递
        config["workers"] = self.workers_spin.value()
        
        return config

    def get_llm_config(self):
        """获取LLM配置字典"""
        service_map = {
            "OpenAI": "marker.services.openai.OpenAIService",
            "Ollama": "marker.services.ollama.OllamaService",
            "Gemini": "marker.services.gemini.GoogleGeminiService",
            "Claude": "marker.services.claude.ClaudeService",
            "Azure OpenAI": "marker.services.azure_openai.AzureOpenAIService",
            "LM Studio": "marker.services.openai.OpenAIService", # LM Studio 使用 OpenAI 兼容接口
        }
        service_name = self.llm_service_combo.currentText()
        service_class = service_map.get(service_name, "")

        llm_config = {"llm_service": service_class}

        api_key = self.api_key_edit.text().strip()
        base_url = self.base_url_edit.text().strip()
        model_name = self.model_name_edit.text().strip()
        
        if service_name in ["OpenAI", "LM Studio"]:
            if api_key: llm_config["openai_api_key"] = api_key
            if base_url: llm_config["openai_base_url"] = base_url
            if model_name: llm_config["model"] = model_name
        elif service_name == "Ollama":
            if base_url: llm_config["ollama_base_url"] = base_url
            if model_name: llm_config["ollama_model"] = model_name
        elif service_name == "Gemini":
            if api_key: llm_config["gemini_api_key"] = api_key
            if model_name: llm_config["gemini_model"] = model_name 
        elif service_name == "Claude":
            if api_key: llm_config["claude_api_key"] = api_key
            if model_name: llm_config["claude_model_name"] = model_name
        elif service_name == "Azure OpenAI":
            if api_key: llm_config["azure_api_key"] = api_key
            if base_url: llm_config["azure_endpoint"] = base_url
            if model_name: llm_config["deployment_name"] = model_name
        
        # LLM 高级选项
        llm_config["temperature"] = self.temperature_slider.value() / 100.0
        llm_config["top_p"] = 1.0 # Marker config parser expects this
        llm_config["max_tokens"] = self.max_tokens_spin.value()
            
        return llm_config

    def start_conversion(self):
        """开始转换流程"""
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

        self.save_settings()

        config_dict = self.get_config_dict()
        use_llm = self.use_llm_cb.isChecked()
        llm_service_config = self.get_llm_config() if use_llm else {}
        use_fallback = self.fallback_image_extraction_cb.isChecked()

        self.log("="*60, "INFO")
        self.log("开始新的转换任务...", "INFO")
        self.log(f"文件总数: {len(self.pdf_files)}", "INFO")
        self.log(f"输出目录: {output_dir}", "INFO")
        self.log(f"基础配置: {config_dict}", "DEBUG")
        if use_llm:
            self.log("使用 LLM: 是", "INFO")
            self.log(f"LLM 服务: {self.llm_service_combo.currentText()}", "INFO")
            safe_llm_config = {k:v for k,v in llm_service_config.items() if 'key' not in k.lower()}
            self.log(f"LLM 配置: {safe_llm_config}", "DEBUG")
        else:
            self.log("使用 LLM: 否", "INFO")
        self.log(f"启用备用图片提取: {'是' if use_fallback else '否'}", "INFO")
        self.log("-"*40, "INFO")

        self.set_ui_state_for_conversion(True)

        self.worker_thread = ConversionWorker(
            self.pdf_files, output_dir, config_dict, use_llm, llm_service_config,
            use_fallback_extraction=use_fallback
        )

        # 连接所有信号
        self.worker_thread.log_signal.connect(lambda msg: self.log(msg, "INFO"))
        self.worker_thread.error_signal.connect(self.on_conversion_error)
        self.worker_thread.progress_signal.connect(self.progress_bar.setValue)
        self.worker_thread.file_progress_signal.connect(self.update_file_progress)
        self.worker_thread.finished_signal.connect(self.on_conversion_finished)
        self.worker_thread.start()

    def stop_conversion(self):
        """停止转换线程"""
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(self, '确认', '确定要停止当前的转换任务吗？',
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.log("正在请求停止转换...", "WARN")
                self.btn_stop.setEnabled(False)
                self.worker_thread.stop()

    def set_ui_state_for_conversion(self, is_running):
        """设置UI在转换开始和结束时的状态"""
        self.btn_start.setEnabled(not is_running)
        self.btn_stop.setEnabled(is_running)
        self.list_widget.setEnabled(not is_running)
        self.tabs.setEnabled(not is_running)
        self.action_group.setEnabled(not is_running)
        
        # 保持停止按钮可用
        self.btn_stop.setEnabled(is_running)
        self.action_group.setEnabled(True)
        self.btn_start.setEnabled(not is_running)

        if is_running:
            self.progress_bar.setValue(0)
            self.current_file_label.setText("准备开始...")
            self.progress_detail_label.setText("")

    def on_conversion_error(self, filename, error_message):
        """处理来自工作线程的错误信号"""
        self.log(f"文件 '{filename}' 发生错误: {error_message}", "ERROR")

    def update_file_progress(self, filename, current, total):
        """更新当前文件进度标签"""
        self.current_file_label.setText(f"处理中: {filename}")
        self.progress_detail_label.setText(f"文件 {current}/{total}")

    def on_conversion_finished(self, success, message):
        """转换完成后的处理"""
        self.worker_thread = None
        self.set_ui_state_for_conversion(False)
        self.current_file_label.setText("转换完成")
        self.progress_bar.setValue(100)
        
        self.log(f"任务完成. 结果: {message}", "SUCCESS" if "失败: 0" in message or "成功" in message else "WARN")
        
        if "严重错误" in message:
            QMessageBox.critical(self, "严重错误", message)
        else:
            QMessageBox.information(self, "完成", message)

        if self.auto_open_output_cb.isChecked():
            self.open_output_directory()

    def open_output_directory(self):
        """打开输出文件夹"""
        output_dir = self.output_dir_edit.text()
        if os.path.isdir(output_dir):
            import subprocess
            import platform
            try:
                if platform.system() == "Windows":
                    os.startfile(output_dir)
                elif platform.system() == "Darwin": # macOS
                    subprocess.run(["open", output_dir])
                else: # Linux
                    subprocess.run(["xdg-open", output_dir])
                self.log(f"已打开输出文件夹: {output_dir}", "INFO")
            except Exception as e:
                self.log(f"无法自动打开输出文件夹: {e}", "ERROR")
                QMessageBox.warning(self, "打开失败", f"无法打开文件夹 '{output_dir}':\n{e}")
        else:
            self.log(f"输出文件夹不存在: {output_dir}", "WARN")

    def save_settings(self):
        """保存所有UI设置"""
        self.settings.setValue("output_dir", self.output_dir_edit.text())
        self.settings.setValue("page_range", self.page_range_edit.text())
        self.settings.setValue("format_lines", self.format_lines_cb.isChecked())
        self.settings.setValue("force_ocr", self.force_ocr_cb.isChecked())
        self.settings.setValue("strip_existing_ocr", self.strip_existing_ocr_cb.isChecked())
        self.settings.setValue("language", self.language_combo.currentText())
        self.settings.setValue("use_llm", self.use_llm_cb.isChecked())
        self.settings.setValue("llm_service", self.llm_service_combo.currentText())
        self.settings.setValue("api_key", self.api_key_edit.text()) # 注意：明文保存API密钥有风险
        self.settings.setValue("base_url", self.base_url_edit.text())
        self.settings.setValue("model_name", self.model_name_edit.text())
        self.settings.setValue("temperature", self.temperature_slider.value())
        self.settings.setValue("max_tokens", self.max_tokens_spin.value())
        self.settings.setValue("output_format", self.output_format_combo.currentText())
        self.settings.setValue("debug", self.debug_cb.isChecked())
        self.settings.setValue("workers", self.workers_spin.value())
        self.settings.setValue("fallback_extraction", self.fallback_image_extraction_cb.isChecked())
        self.settings.setValue("auto_open_output", self.auto_open_output_cb.isChecked())
        self.settings.setValue("create_subfolder", self.create_subfolder_cb.isChecked())
        self.log("设置已保存。", "DEBUG")

    def load_settings(self):
        """加载所有UI设置"""
        self.output_dir_edit.setText(self.settings.value("output_dir", ""))
        self.page_range_edit.setText(self.settings.value("page_range", ""))
        self.format_lines_cb.setChecked(self.settings.value("format_lines", True, type=bool))
        self.force_ocr_cb.setChecked(self.settings.value("force_ocr", False, type=bool))
        self.strip_existing_ocr_cb.setChecked(self.settings.value("strip_existing_ocr", False, type=bool))
        
        lang = self.settings.value("language", "自动检测")
        lang_index = self.language_combo.findText(lang)
        if lang_index != -1: self.language_combo.setCurrentIndex(lang_index)

        self.use_llm_cb.setChecked(self.settings.value("use_llm", False, type=bool))
        llm_service = self.settings.value("llm_service", "OpenAI")
        index = self.llm_service_combo.findText(llm_service)
        if index >= 0: self.llm_service_combo.setCurrentIndex(index)
            
        self.api_key_edit.setText(self.settings.value("api_key", ""))
        self.base_url_edit.setText(self.settings.value("base_url", ""))
        self.model_name_edit.setText(self.settings.value("model_name", ""))
        self.temperature_slider.setValue(self.settings.value("temperature", 30, type=int))
        self.max_tokens_spin.setValue(self.settings.value("max_tokens", 2000, type=int))
        
        output_format = self.settings.value("output_format", "markdown")
        index = self.output_format_combo.findText(output_format)
        if index >= 0: self.output_format_combo.setCurrentIndex(index)
            
        self.debug_cb.setChecked(self.settings.value("debug", False, type=bool))
        self.workers_spin.setValue(self.settings.value("workers", 4, type=int))
        self.fallback_image_extraction_cb.setChecked(self.settings.value("fallback_extraction", True, type=bool))
        self.auto_open_output_cb.setChecked(self.settings.value("auto_open_output", True, type=bool))
        self.create_subfolder_cb.setChecked(self.settings.value("create_subfolder", False, type=bool))

        self.toggle_llm_options(Qt.Checked if self.use_llm_cb.isChecked() else Qt.Unchecked)
        self.log("设置已加载。", "DEBUG")

    def closeEvent(self, event):
        """处理窗口关闭事件"""
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
    # 启用高DPI缩放
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("PDF to Markdown Converter")
    app.setApplicationVersion("2.0")
    
    # 设置一个现代化的样式
    app.setStyle('Fusion') 

    # 可选：设置暗色主题
    # palette = QPalette()
    # palette.setColor(QPalette.Window, QColor(53, 53, 53))
    # palette.setColor(QPalette.WindowText, Qt.white)
    # ... (设置其他颜色)
    # app.setPalette(palette)

    window = PDFToMdApp()
    window.show()
    sys.exit(app.exec_())
