import os
import json
import traceback
from PySide6.QtWidgets import (QDialog, QFileDialog, QMessageBox, 
                              QTreeWidgetItem, QApplication, QVBoxLayout)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtUiTools import QUiLoader

from detect_report import analyze_defect_textures


class AnalysisWorker(QThread):
    """
    执行缺陷纹理分析的工作线程
    """
    progress_signal = Signal(int, str)
    finished_signal = Signal(dict)
    error_signal = Signal(str)
    
    def __init__(self, detect_path, detect_group, threshold, eps, min_samples):
        super().__init__()
        self.detect_path = detect_path
        self.detect_group = detect_group
        self.threshold = threshold
        self.eps = eps
        self.min_samples = min_samples
    
    def run(self):
        try:
            # 调用分析函数，传递进度回调
            result = analyze_defect_textures(
                self.detect_path,
                self.detect_group,
                self.threshold,
                self.eps,
                self.min_samples,
                self.update_progress
            )
            
            if result:
                self.finished_signal.emit(result)
            else:
                self.error_signal.emit("分析未返回有效结果")
                
        except Exception as e:
            error_msg = f"分析过程出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.error_signal.emit(str(e))
    
    def update_progress(self, value, message):
        """
        更新进度信息
        """
        self.progress_signal.emit(value, message)


class TextureAnalysisDialog(QDialog):
    """
    缺陷纹理分析对话框
    """
    def __init__(self, detect_path, parent=None):
        super().__init__(parent)
        self.detect_path = detect_path
        
        # 加载UI
        self.ui = QUiLoader().load('ui/detect_result.ui')
        
        # 设置窗口属性
        self.setWindowTitle(self.ui.windowTitle())
        self.setMinimumSize(self.ui.size())
        
        # 创建新的布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 添加UI控件到布局
        main_layout.addWidget(self.ui)
        
        # 初始化界面
        self.init_ui()
        
        # 当前报告数据
        self.current_report = None
        
        # 分析线程
        self.worker = None
    
    def init_ui(self):
        """
        初始化界面
        """
        # 连接信号槽
        self.ui.analyzeButton.clicked.connect(self.start_analysis)
        self.ui.exportButton.clicked.connect(self.export_report)
        self.ui.thresholdSlider.valueChanged.connect(self.update_threshold_label)
        
        # 加载样本组
        self.load_sample_groups()
        
        # 禁用导出按钮，直到分析完成
        self.ui.exportButton.setEnabled(False)
        
        # 初始化进度条
        self.ui.progressBar.setValue(0)
    
    def load_sample_groups(self):
        """
        加载所有检测样本组
        """
        self.ui.sampleGroupComboBox.clear()
        
        try:
            # 检查检测路径是否存在
            if not os.path.exists(self.detect_path):
                return
            
            # 获取所有子目录
            sample_groups = [d for d in os.listdir(self.detect_path) 
                            if os.path.isdir(os.path.join(self.detect_path, d))]
            
            # 添加到下拉框
            self.ui.sampleGroupComboBox.addItems(sample_groups)
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载样本组失败: {str(e)}")
    
    def update_threshold_label(self, value):
        """
        更新阈值标签
        """
        threshold = value / 100.0
        self.ui.thresholdValueLabel.setText(f"阈值: {threshold:.2f}")
    
    def start_analysis(self):
        """
        开始分析
        """
        # 获取参数
        detect_group = self.ui.sampleGroupComboBox.currentText()
        if not detect_group:
            QMessageBox.warning(self, "警告", "请选择检测样本组")
            return
        
        threshold = self.ui.thresholdSlider.value() / 100.0
        eps = self.ui.epsSpinBox.value()
        min_samples = self.ui.minSamplesSpinBox.value()
        
        # 禁用分析按钮
        self.ui.analyzeButton.setEnabled(False)
        self.ui.exportButton.setEnabled(False)
        
        # 重置进度条
        self.ui.progressBar.setValue(0)
        
        # 创建并启动工作线程
        self.worker = AnalysisWorker(
            self.detect_path, 
            detect_group, 
            threshold, 
            eps, 
            min_samples
        )
        
        # 连接信号
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.analysis_finished)
        self.worker.error_signal.connect(self.analysis_error)
        
        # 启动线程
        self.worker.start()
    
    def update_progress(self, value, message):
        """
        更新进度信息
        """
        self.ui.progressBar.setValue(value)
        self.setWindowTitle(f"缺陷纹理分析 - {message}")
    
    def analysis_finished(self, result):
        """
        分析完成
        """
        self.current_report = result
        
        # 更新UI
        self.setWindowTitle("缺陷纹理分析 - 分析完成")
        self.ui.analyzeButton.setEnabled(True)
        self.ui.exportButton.setEnabled(True)
        
        # 显示分析图表
        if 'chart_file' in result and os.path.exists(result['chart_file']):
            pixmap = QPixmap(result['chart_file'])
            self.ui.imageLabel.setPixmap(pixmap.scaled(
                self.ui.imageLabel.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            ))
        
        # 显示统计信息
        self.show_statistics(result['report_data'])
        
        # 显示详细信息
        self.show_details(result['report_data'])
        
        # 显示完成消息
        QMessageBox.information(self, "完成", "缺陷纹理分析已完成")
    
    def analysis_error(self, error_message):
        """
        分析出错
        """
        self.ui.analyzeButton.setEnabled(True)
        self.setWindowTitle("缺陷纹理分析")
        
        # 记录错误日志
        print(f"错误: {error_message}")
        
        # 检查常见的错误原因
        error_info = "分析过程中出错"
        suggestion = ""
        
        if "No module named" in error_message:
            suggestion = "可能缺少所需的Python库，请尝试运行: pip install -r requirements.txt"
        elif "FileNotFoundError" in error_message or "No such file or directory" in error_message:
            suggestion = "找不到文件或目录，请检查路径是否正确"
        elif "read_image" in error_message.lower() or "imread" in error_message.lower():
            suggestion = "图像读取失败，请检查图像文件格式是否正确"
        elif "memory" in error_message.lower():
            suggestion = "内存不足，请尝试减少分析的图像数量或关闭其他应用程序"
            
        # 显示带有建议的错误信息
        if suggestion:
            error_info = f"{error_info}:\n\n{error_message}\n\n建议: {suggestion}"
        else:
            error_info = f"{error_info}:\n\n{error_message}"
            
        QMessageBox.critical(self, "错误", error_info)
    
    def show_statistics(self, report_data):
        """
        显示统计信息
        """
        browser = self.ui.statisticsBrowser
        browser.clear()
        
        # 基本信息
        browser.append("<h3>基本信息</h3>")
        browser.append(f"<p>检测组: <b>{report_data['detect_group']}</b></p>")
        browser.append(f"<p>总图像数: <b>{report_data['total_images']}</b></p>")
        browser.append(f"<p>缺陷图像数: <b>{report_data['defect_images']}</b></p>")
        browser.append(f"<p>缺陷位置总数: <b>{report_data['defect_positions']}</b></p>")
        
        # 聚类分析
        browser.append("<h3>聚类分析</h3>")
        clusters = report_data['position_clusters']['clusters']
        browser.append(f"<p>聚类数量: <b>{len(clusters)}</b></p>")
        if clusters:
            browser.append(f"<p>最大聚类包含: <b>{clusters[0]['count']}</b>个缺陷</p>")
            browser.append("<p>前3个聚类:</p>")
            browser.append("<ul>")
            for i, cluster in enumerate(clusters[:3]):
                browser.append(f"<li>聚类 {i+1}: 中心位置({cluster['center'][0]:.2f}, {cluster['center'][1]:.2f}), " 
                             f"半径: {cluster['radius']:.3f}, 包含: {cluster['count']}个缺陷</li>")
            browser.append("</ul>")
        
        browser.append(f"<p>噪声点数量: <b>{report_data['position_clusters']['noise']}</b></p>")
        
        # 纹理分析
        browser.append("<h3>纹理分析</h3>")
        texture_counts = report_data['texture_analysis']['texture_counts']
        if texture_counts:
            main_texture = max(texture_counts.items(), key=lambda x: x[1])[0]
            browser.append(f"<p>主要纹理类型: <b>{main_texture}</b></p>")
            
            browser.append("<p>纹理类型分布:</p>")
            browser.append("<ul>")
            for texture, count in texture_counts.items():
                browser.append(f"<li>{texture}: {count}个</li>")
            browser.append("</ul>")
        
        # 网格位置分析
        dominant_textures = report_data['texture_analysis']['dominant_position_textures']
        browser.append(f"<p>网格位置数量: <b>{len(dominant_textures)}</b></p>")
    
    def show_details(self, report_data):
        """
        显示详细信息树
        """
        tree = self.ui.detailTreeWidget
        tree.clear()
        
        # 添加根节点
        root = QTreeWidgetItem(tree)
        root.setText(0, "缺陷分析报告")
        root.setText(1, report_data['detect_group'])
        
        # 添加基本信息
        basic_info = QTreeWidgetItem(root)
        basic_info.setText(0, "基本信息")
        
        items = [
            ("检测组", report_data['detect_group']),
            ("总图像数", str(report_data['total_images'])),
            ("缺陷图像数", str(report_data['defect_images'])),
            ("缺陷位置数", str(report_data['defect_positions'])),
            ("时间戳", report_data['timestamp'])
        ]
        
        for name, value in items:
            item = QTreeWidgetItem(basic_info)
            item.setText(0, name)
            item.setText(1, value)
        
        # 添加聚类信息
        clusters_info = QTreeWidgetItem(root)
        clusters_info.setText(0, "聚类分析")
        clusters_info.setText(1, str(len(report_data['position_clusters']['clusters'])) + "个聚类")
        
        for i, cluster in enumerate(report_data['position_clusters']['clusters']):
            cluster_item = QTreeWidgetItem(clusters_info)
            cluster_item.setText(0, f"聚类 {i+1}")
            cluster_item.setText(1, f"{cluster['count']}个缺陷")
            
            for attr in ["center", "radius", "count"]:
                attr_item = QTreeWidgetItem(cluster_item)
                attr_item.setText(0, attr)
                attr_item.setText(1, str(cluster[attr]))
        
        # 添加纹理信息
        texture_info = QTreeWidgetItem(root)
        texture_info.setText(0, "纹理分析")
        
        # 添加纹理统计
        texture_counts = QTreeWidgetItem(texture_info)
        texture_counts.setText(0, "纹理统计")
        
        for texture, count in report_data['texture_analysis']['texture_counts'].items():
            texture_item = QTreeWidgetItem(texture_counts)
            texture_item.setText(0, texture)
            texture_item.setText(1, str(count))
        
        # 展开根节点
        tree.expandItem(root)
    
    def export_report(self):
        """
        导出报告
        """
        if not self.current_report:
            QMessageBox.warning(self, "警告", "没有可导出的报告")
            return
            
        # 选择导出目录
        directory = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not directory:
            return
            
        try:
            # 复制报告文件
            report_file = self.current_report['report_file']
            chart_file = self.current_report['chart_file']
            
            report_basename = os.path.basename(report_file)
            chart_basename = os.path.basename(chart_file)
            
            target_report = os.path.join(directory, report_basename)
            target_chart = os.path.join(directory, chart_basename)
            
            # 复制文件
            import shutil
            shutil.copy2(report_file, target_report)
            shutil.copy2(chart_file, target_chart)
            
            QMessageBox.information(self, "成功", f"报告已导出至:\n{directory}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出报告失败: {str(e)}")


if __name__ == "__main__":
    # 测试代码
    import sys
    
    app = QApplication(sys.argv)
    
    # 示例检测路径
    detect_path = "B:/Development/GraduationDesign/app/test/detect_result"
    
    dialog = TextureAnalysisDialog(detect_path)
    dialog.show()
    
    sys.exit(app.exec()) 