import os
from PySide6.QtCore import Qt, QEvent, QThread, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtWidgets import QDialog, QMessageBox
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QTimer
import config
from http_server import HttpServer
from utils import LoadingAnimation, join_path, show_message_box

# 添加推理线程类
class InferenceThread(QThread):
    result_ready = Signal(list)  # 结果信号
    error_occurred = Signal(Exception)  # 错误信号
    
    def __init__(self, img_list, question, normal_img_list, history):
        super().__init__()
        self.img_list = img_list
        self.question = question
        self.normal_img_list = normal_img_list
        self.history = history
        
    def run(self):
        try:
            print(f"img_list: {self.img_list}\nquestion: {self.question}\nnormal_img_list: {self.normal_img_list}\nhistory: {self.history}")
            results = HttpServer().anomaly_gpt_infer(
                img_list=self.img_list,
                question=self.question,
                normal_img_list=self.normal_img_list,
                history=self.history
            )
            if not results or len(results) == 0:
                raise Exception("AI返回结果为空")
            self.result_ready.emit(results)
        except Exception as e:
            self.error_occurred.emit(e)

class AIChatDialog(QDialog):
    """AI 聊天对话框，用于与大模型交互分析图像异常"""
    
    def __init__(self, parent=None, image_info_list=None):
        super().__init__(parent)
        
        # 加载UI
        self.ui = QUiLoader().load('ui/ai_chat.ui')
        
        # 设置窗口标题和图标
        self.setWindowTitle(self.ui.windowTitle())
        self.resize(self.ui.size())
        
        # 复制UI的布局到当前对话框
        self.setLayout(self.ui.layout())
        self.ui.setParent(None)  # 解除原始UI的父子关系
        
        # 保存图像信息列表
        self.image_info_list = image_info_list or []
        
        # 连接导航按钮
        self.ui.prevImageButton.clicked.connect(self.show_prev_image)
        self.ui.nextImageButton.clicked.connect(self.show_next_image)
        
        # 连接信号和槽
        self.ui.sendButton.clicked.connect(self.on_send_clicked)
        self.ui.questionEdit.returnPressed.connect(self.on_send_clicked)
        
        # 为中央图像添加点击事件处理
        self.ui.centerImageLabel.installEventFilter(self) # 安装事件过滤器
        self.ui.centerImageLabel.setCursor(Qt.PointingHandCursor) # 设置鼠标样式
        
        # 初始化图像显示状态
        self.show_original = True  # 默认显示原图
        
        # 初始化对话历史，包含所有图片的对话记录：
        # [ 1号图对话记录[[question1, answer11], [question2,answer21],...], 2号图对话记录[...], ...]
        self.ai_conversation_history = []
        
        # 设置当前图像索引
        self.current_image_idx = 0
        # 更新图像显示
        self.update_image_gallery()
        
        # 自动发起第一次分析
        self.start_initial_analysis()
    
    def eventFilter(self, obj, event):
        """事件过滤器，处理中央图像的点击事件"""
        if obj == self.ui.centerImageLabel and event.type() == QEvent.MouseButtonPress:
            self.toggle_image_view()
            return True
        return super().eventFilter(obj, event)
    
    def toggle_image_view(self):
        """切换中央图像的显示（原图/结果图）"""
        self.show_original = not self.show_original
        self.update_center_image()
    
    def update_center_image(self):
        """根据当前状态更新中央图像显示"""
        if not self.image_info_list or self.current_image_idx >= len(self.image_info_list):
            return
            
        info = self.image_info_list[self.current_image_idx]
        image_name = info.get('origin_name')
        
        if not image_name:
            return
            
        # 获取原图路径
        original_path = join_path(config.SAMPLE_PATH, config.DETECT_SAMPLE_GROUP, image_name)
        
        # 获取结果图路径
        base_name = os.path.splitext(image_name)[0]
        result_path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP, f"{base_name}__1.png")
        
        # 选择显示原图还是结果图
        image_path = original_path if self.show_original else result_path
        
        # 检查所选图像是否存在
        if not os.path.exists(image_path):
            # 如果所选类型的图像不存在，使用另一种类型
            image_path = result_path if self.show_original else original_path
            if not os.path.exists(image_path):
                self.ui.centerImageLabel.setText("图像不存在")
                return
            # 更新状态以匹配实际显示的图像类型
            self.show_original = not self.show_original
            
        # 加载并显示图像
        pixmap = QPixmap(image_path)
        scaled_pixmap = pixmap.scaled(
            self.ui.centerImageLabel.width(), 
            self.ui.centerImageLabel.height(), 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        self.ui.centerImageLabel.setPixmap(scaled_pixmap)
        
        # 更新提示信息
        display_type = "原图" if self.show_original else "结果图"
        self.ui.centerImageLabel.setToolTip(f"点击切换显示原图和结果图 (当前: {display_type})")
        
        # 更新标题
        current_info = self.image_info_list[self.current_image_idx]
        self.file_name = current_info.get('file_name')
        display_name = self.file_name
        self.ui.imageNameLabel.setText(f"当前图像: {display_name} ({self.current_image_idx+1}/{len(self.image_info_list)}) - {display_type}")
    
    def update_image_gallery(self):
        """更新图像画廊，显示当前图像及两侧图像"""
        if not self.image_info_list:
            return
        
        # 获取左侧图像索引
        left_idx = (self.current_image_idx - 1) % len(self.image_info_list) if len(self.image_info_list) > 1 else -1
        
        # 获取右侧图像索引
        right_idx = (self.current_image_idx + 1) % len(self.image_info_list) if len(self.image_info_list) > 1 else -1
        
        # 加载中间图像（使用update_center_image以便应用当前的图像类型选择）
        self.update_center_image()
        
        # 加载左侧图像
        if left_idx >= 0:
            self.load_image_to_label(left_idx, self.ui.leftImageLabel)
        else:
            self.ui.leftImageLabel.clear()
        
        # 加载右侧图像
        if right_idx >= 0:
            self.load_image_to_label(right_idx, self.ui.rightImageLabel)
        else:
            self.ui.rightImageLabel.clear()
        
        # 更新聊天显示，只显示当前图像的对话历史
        self.update_chat_display()
    
    def load_image_to_label(self, image_idx, label, is_center=False):
        """加载图像到指定的标签，并应用样式效果"""
        if image_idx < 0 or image_idx >= len(self.image_info_list):
            label.clear()
            return
        
        info = self.image_info_list[image_idx]
        image_name = info.get('origin_name')
        
        # 尝试加载图像
        if not image_name:
            label.setText("无效图像")
            return
        
        # 先尝试加载原图
        original_path = join_path(config.SAMPLE_PATH, config.DETECT_SAMPLE_GROUP, image_name)
        result_path = None
        
        # 如果原图不存在，尝试加载结果图
        if not os.path.exists(original_path):
            base_name = os.path.splitext(image_name)[0]
            result_path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP, f"{base_name}__1.png")
            if not os.path.exists(result_path):
                label.setText("图像不存在")
                return
        
        # 加载图像并应用效果
        img_path = original_path if os.path.exists(original_path) else result_path
        pixmap = QPixmap(img_path)
        
        # 调整尺寸
        if is_center:
            # 中心图像使用更大的尺寸
            scaled_pixmap = pixmap.scaled(
                label.width(), 
                label.height(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
        else:
            # 侧边图像使用较小的尺寸，应用虚化效果
            scaled_pixmap = pixmap.scaled(
                label.width(), 
                label.height(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            # 创建半透明效果 (通过QImage和QPainter实现)
            img = scaled_pixmap.toImage()
            painter = QPainter(img)
            painter.setCompositionMode(QPainter.CompositionMode_SourceAtop)
            painter.fillRect(img.rect(), QColor(255, 255, 255, 120))  # 半透明白色蒙版
            painter.end()
            scaled_pixmap = QPixmap.fromImage(img)
        
        # 设置图像
        label.setPixmap(scaled_pixmap)
    
    def update_chat_display(self):
        """更新聊天显示，只显示当前图像的对话历史"""
        self.ui.chatTextBrowser.clear()
        
        # 如果还没有对话历史，直接返回
        if not self.ai_conversation_history or self.current_image_idx >= len(self.ai_conversation_history):
            return
        
        # 获取当前图像的对话历史
        current_history = self.ai_conversation_history[self.current_image_idx]
        
        # 显示对话历史
        for question, answer in current_history:
            # 显示问题
            self.ui.chatTextBrowser.append(f"<div style='color:#1E3A8A; font-weight:bold;'>你:</div>")
            self.ui.chatTextBrowser.append(f"<div style='margin-left:10px;'>{question}</div><br>")
            
            # 显示回答
            self.ui.chatTextBrowser.append(f"<div style='color:#8E44AD; font-weight:bold;'>AI 回答:</div>")
            self.ui.chatTextBrowser.append(f"<div style='margin-left:10px;'>{answer}</div><br>")
    
    def show_prev_image(self):
        """显示上一张图像"""
        if len(self.image_info_list) > 1:
            self.current_image_idx = (self.current_image_idx - 1) % len(self.image_info_list)
            # 重置为显示原图，除非结果图已下载并存在
            self.check_and_reset_image_view()
            self.update_image_gallery()
    
    def show_next_image(self):
        """显示下一张图像"""
        if len(self.image_info_list) > 1:
            self.current_image_idx = (self.current_image_idx + 1) % len(self.image_info_list)
            # 重置为显示原图，除非结果图已下载并存在
            self.check_and_reset_image_view()
            self.update_image_gallery()
    
    def check_and_reset_image_view(self):
        """检查结果图是否存在，并根据情况重置图像视图模式"""
        if not self.image_info_list or self.current_image_idx >= len(self.image_info_list):
            return
            
        info = self.image_info_list[self.current_image_idx]
        image_name = info.get('origin_name')
        
        if not image_name:
            return
            
        # 检查结果图是否存在
        base_name = os.path.splitext(image_name)[0]
        result_path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP, f"{base_name}__1.png")
        
        # 如果切换到结果图模式，但结果图不存在，则重置为原图模式
        if not self.show_original and not os.path.exists(result_path):
            self.show_original = True
    
    def start_initial_analysis(self):
        """自动开始第一次分析"""
        if not self.image_info_list:
            return
        # 构建初始问题
        initial_question = "Is there any anomaly in this image?"
        # 显示初始问题
        self.ui.questionEdit.setText("")
        # 模拟点击发送按钮
        self.send_question(initial_question)
    
    def send_question(self, question):
        """发送问题到大模型并处理响应"""
        if not question:
            return
        
        # 显示问题
        self.ui.chatTextBrowser.append(f"<div style='color:#1E3A8A; font-weight:bold;'>你:</div><div style='margin-left:10px;'>{question}</div><br>")
        
        # 禁用发送按钮，避免重复发送
        self.reset_button_status(False)
        
        # 显示加载动画
        self.loading_animation = LoadingAnimation(self)
        self.loading_animation.set_text("AI分析中，请稍候...")
        self.loading_animation.show()
        
        # 准备所有图像的文件名列表
        self.img_list = []
        for info in self.image_info_list:
            self.img_list.append(info.get('file_name'))
        # 如果没有图像可分析，显示错误
        if not self.img_list:
            raise Exception("没有有效的图像可供分析")
        
        # 是否为追问（历史记录是否已存在）
        is_followup = len(self.ai_conversation_history) > 0
        
        # 使用线程执行推理请求
        self.inference_thread = InferenceThread(
            img_list=self.img_list,
            question=question,
            normal_img_list=[],
            history=self.ai_conversation_history if is_followup else []
        )
        # 连接信号
        self.inference_thread.result_ready.connect(lambda results: self.handle_inference_results(results, question, is_followup))
        self.inference_thread.error_occurred.connect(self.handle_inference_error)
        # 启动线程
        self.inference_thread.start()
    
    def handle_inference_results(self, results, question, is_followup):
        """处理推理结果"""
        # 请求已完成，关闭加载动画
        self.loading_animation.close_animation()
        
        # 清除对话窗口已有内容，仅显示当前图像的回复
        self.ui.chatTextBrowser.clear()
        
        # 先记录所有图像的回复
        for idx, result in enumerate(results):
            # 更新对话历史
            if is_followup:
                # 追问：在对应图像的对话记录中追加
                self.ai_conversation_history[idx].append([question, result])
            else:
                # 首次对话：初始化对话历史
                self.ai_conversation_history.append([[question, result]])
                # 下载推理结果图片
                img_name = self.img_list[idx]
                file_name = f"{os.path.splitext(img_name)[0]}__1.png"
                path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP)
                try:
                    HttpServer().save_downloaded_sample(file_name, path)
                    print(f"下载推理结果图片成功: {path}/{file_name}")
                except Exception as e:
                    print(f"下载推理结果图片失败: {str(e)}")
                # 如果当前显示的是该图像，刷新图像显示
                if idx == self.current_image_idx:
                    self.update_image_gallery()
        
        # 显示当前图像的对话历史
        self.update_chat_display()
        # 恢复按钮状态
        self.reset_button_status(True)
    
    def handle_inference_error(self, e):
        """处理推理错误"""
        # 确保加载动画已关闭
        self.loading_animation.close_animation()
        show_message_box("错误", f"AI分析失败: {str(e)}", QMessageBox.Critical)
        print(f"AI分析失败: {str(e)}")
        # 恢复按钮状态
        self.reset_button_status(True)

    def reset_button_status(self, is_enable=True):
        """重置按钮状态"""
        if is_enable:
            self.ui.sendButton.setEnabled(True)
            self.ui.questionEdit.setEnabled(True)
            self.ui.questionEdit.setFocus()
        else:
            self.ui.sendButton.setEnabled(False)
            self.ui.questionEdit.setEnabled(False)
        
    def on_send_clicked(self):
        """处理发送按钮点击事件"""
        question = self.ui.questionEdit.text().strip()
        if question:
            self.send_question(question)
            self.ui.questionEdit.clear() 