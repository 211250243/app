import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLineEdit, QMessageBox
from PySide6.QtUiTools import QUiLoader

import config
from http_server import HttpServer
from utils import ProgressDialog, join_path, show_message_box

class AIChatDialog(QDialog):
    """AI 聊天对话框，用于与大模型交互分析图像异常"""
    
    def __init__(self, parent=None, image_info=None):
        super().__init__(parent)
        
        # 加载UI
        loader = QUiLoader()
        self.ui = loader.load('ui/ai_chat.ui')
        
        # 设置窗口标题和图标
        self.setWindowTitle(self.ui.windowTitle())
        self.resize(self.ui.size())
        
        # 复制UI的布局到当前对话框
        self.setLayout(self.ui.layout())
        self.ui.setParent(None)  # 解除原始UI的父子关系
        
        # 保存图像信息
        self.image_info = image_info
        self.file_name = image_info.get('file_name')
        
        # 设置图像名称
        if self.file_name:
            self.ui.imageNameLabel.setText(f"当前图像: {self.file_name}")
        
        # 连接信号和槽
        self.ui.sendButton.clicked.connect(self.on_send_clicked)
        self.ui.closeButton.clicked.connect(self.close)
        self.ui.questionEdit.returnPressed.connect(self.on_send_clicked)
        
        # 初始化对话历史，包含所有图片的对话记录：
        # [ 1号图对话记录[[question1, answer11], [question2,answer21],...], 2号图对话记录[...], ...]
        self.ai_conversation_history = []
        self.current_image_idx = 0  # 当前图像在历史记录中的索引
        
        # 自动发起第一次分析
        self.start_initial_analysis()
    
    def start_initial_analysis(self):
        """自动开始第一次分析"""
        if not self.file_name or not self.image_info:
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
        self.ui.sendButton.setEnabled(False)
        self.ui.questionEdit.setEnabled(False)
        
        # 显示进度对话框
        progress_dialog = ProgressDialog(self, {
            "title": "AI分析中",
            "text": "正在分析图像，请稍候..."
        })
        progress_dialog.show()
        
        try:
            # 准备参数
            img_list = [self.file_name]
            
            # 是否为追问（历史记录是否已存在）
            is_followup = len(self.ai_conversation_history) > 0
            
            # 调用大模型推理
            http_server = HttpServer()
            print(f"img_list: {img_list}")
            print(f"question: {question}")
            print(f"normal_img_list: {[]}")
            print(f"history: {self.ai_conversation_history if is_followup else []}")
            results = http_server.anomaly_gpt_infer(
                img_list=img_list,
                question=question,
                normal_img_list=[],
                history=self.ai_conversation_history if is_followup else []
            )
            
            # 关闭进度对话框
            progress_dialog.close()
            
            # 处理结果
            if not results or len(results) == 0:
                raise Exception("AI返回结果为空")

            for idx, result in enumerate(results):
                # 显示AI回答
                self.ui.chatTextBrowser.append(f"<div style='color:#8E44AD; font-weight:bold;'>AI:</div>")
                self.ui.chatTextBrowser.append(f"<div style='margin-left:10px;'>{result}</div>")
                self.ui.chatTextBrowser.append("<br>")
                
                # 更新对话历史
                if is_followup:
                    # 追问：在对应图像的对话记录中追加
                    self.ai_conversation_history[idx].append([
                        question,
                        result
                    ])
                else:
                    # 首次对话：初始化对话历史
                    self.ai_conversation_history.append([[
                        question,
                        result
                    ]])
                    # 下载推理结果图片                        
                    file_name = f"{os.path.splitext(self.file_name)[0]}__1.png"
                    path = join_path(config.DETECT_PATH, config.DETECT_SAMPLE_GROUP)
                    http_server.save_downloaded_sample(file_name, path)
                    path = join_path(path, file_name)
                    print(f"下载推理结果图片成功: {path}")                        
                    # 显示结果图片
                    result_image_path = join_path(path, file_name)
                    print(f"result_image_path: {result_image_path}")
                    if os.path.exists(result_image_path):
                        pixmap = QPixmap(result_image_path)
                        scaled_pixmap = pixmap.scaled(
                            self.ui.imageLabel.width(), 
                            150, 
                            Qt.KeepAspectRatio, 
                            Qt.SmoothTransformation
                        )
                        self.ui.imageLabel.setPixmap(scaled_pixmap)
                        self.ui.imageNameLabel.setText(f"当前图像: {self.file_name} (结果图)")
                
        except Exception as e:
            progress_dialog.close()
            show_message_box("错误", f"AI分析失败: {str(e)}", QMessageBox.Critical)
            print(f"AI分析失败: {str(e)}")
        
        # 恢复按钮状态
        self.ui.sendButton.setEnabled(True)
        self.ui.questionEdit.setEnabled(True)
        self.ui.questionEdit.setFocus()
    
    def on_send_clicked(self):
        """处理发送按钮点击事件"""
        question = self.ui.questionEdit.text().strip()
        if question:
            self.send_question(question)
            self.ui.questionEdit.clear() 