import os
import json
import numpy as np
import cv2
from matplotlib import pyplot as plt
from collections import Counter, defaultdict
from sklearn.cluster import DBSCAN
from datetime import datetime
import traceback

import config
from utils import join_path

# 添加必要的导入
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from io import BytesIO
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    print("警告: 未安装reportlab库，PDF报告功能不可用")


class DefectTextureAnalyzer:
    """
    缺陷分析器，用于分析检测结果热图中的缺陷位置和缺陷特征
    """
    def __init__(self, detect_path, detect_group, result_path=None, report_path=None):
        """
        初始化分析器
        
        Args:
            detect_path: 检测样本根目录路径
            detect_group: 检测样本组名称
            result_path: 结果图像保存路径，默认为detect_path/detect_group/results
            report_path: 报告保存路径，默认为detect_path/detect_group/reports
        """
        # 获取检测样本组
        self.detect_group = detect_group
        if not self.detect_group:
            raise ValueError("未指定检测样本组")
            
        # 设置路径
        self.detect_path = join_path(detect_path, self.detect_group)
        
        # 如果直接指定了result_path，则使用它，否则使用默认路径
        if result_path:
            self.result_path = result_path
        else:
            # 兼容两种路径模式：带results子目录或直接是图片目录
            possible_result_path = join_path(self.detect_path, 'results')
            if os.path.exists(possible_result_path) and os.path.isdir(possible_result_path):
                self.result_path = possible_result_path
            else:
                # 如果没有results子目录，直接使用detect_path
                self.result_path = self.detect_path
                
        # 报告路径
        self.report_path = report_path or join_path(self.detect_path, 'reports')
        
        # 显示路径信息进行调试
        print(f"检测路径: {self.detect_path}")
        print(f"结果路径: {self.result_path}")
        print(f"报告路径: {self.report_path}")
        
        # 创建报告目录
        os.makedirs(self.report_path, exist_ok=True)
            
        # 初始化结果
        self.image_count = 0  # 总图像数
        self.defect_images = []  # 存储缺陷图像信息
        self.heatmap_data = []   # 存储热图数据
        self.texture_features = []  # 存储缺陷特征
        self.defect_positions = []  # 存储缺陷位置
        self.cluster_results = None  # 聚类结果
        self.best_sample = None  # 最佳样本（得分最高的图片）
        self.best_sample_path = None  # 最佳样本原图路径
        self.patch_statistics = None  # Patch统计特征
        
        # 进度回调函数
        self.progress_callback = None
    
    def set_progress_callback(self, callback):
        """设置进度回调函数"""
        self.progress_callback = callback
    
    def update_progress(self, value, message=""):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(value, message)
    
    def load_defect_images(self, threshold=0.5):
        """
        根据检测得分加载异常热图图像
        
        Args:
            threshold: 判定为异常的得分阈值（0-1之间）
        """
        self.update_progress(0, "开始加载图像...")
        self.defect_images = []
        
        # 检查路径是否存在
        if not os.path.exists(self.result_path):
            error_msg = f"结果路径不存在: {self.result_path}"
            print(error_msg)
            self.update_progress(30, error_msg)
            return 0
        
        # 获取所有图像文件
        try:
            # 先尝试获取所有热图（包含_3.的图像）
            all_image_files = [f for f in os.listdir(self.result_path) 
                          if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')) and '_3.' in f]
            
            # 如果找不到热图，则获取所有图像文件
            if not all_image_files:
                print("未找到热图文件，尝试加载所有图像文件")
                all_image_files = [f for f in os.listdir(self.result_path) 
                              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]
            
            # 如果还是找不到图像，使用更宽松的匹配
            if not all_image_files:
                print("使用宽松匹配搜索图像文件")
                all_image_files = []
                for f in os.listdir(self.result_path):
                    try:
                        if os.path.isfile(join_path(self.result_path, f)):
                            # 尝试读取文件看是否为图像
                            img = cv2.imread(join_path(self.result_path, f), cv2.IMREAD_UNCHANGED)
                            if img is not None:
                                all_image_files.append(f)
                    except Exception as e:
                        print(f"检查文件 {f} 时出错: {str(e)}")
        
            self.image_count = len(all_image_files)
            print(f"找到 {self.image_count} 个图像文件")
            
            if self.image_count == 0:
                self.update_progress(30, "未找到图像文件")
                return 0
            
            # 加载detect_list.json获取得分信息
            detect_list = []
            print(f"self.detect_path: {self.detect_path}")
            detect_list_path = join_path(self.detect_path, 'detect_list.json')
            if os.path.exists(detect_list_path):
                try:
                    detect_list = json.load(open(detect_list_path))
                    config.DETECT_LIST = detect_list
                    print(f"加载了 {len(detect_list)} 个检测结果记录")
                except Exception as e:
                    print(f"读取detect_list.json出错: {str(e)}")
                else:
                    print(f"未找到检测结果文件: {detect_list_path}")
            
            # 创建文件名到得分的映射
            score_map = {}
            self.best_sample = None
            best_score = -1
            
            for item in detect_list:
                file_name = item.get('origin_name', '')
                score = item.get('score')
                
                # 确保得分是数值类型
                if isinstance(score, str):
                    try:
                        score = float(score)
                    except:
                        score = 0
                
                # 找出得分最高的样本
                if score > best_score:
                    best_score = score
                    self.best_sample = file_name
                
                # 将原始文件名与得分关联
                score_map[file_name] = score
            
            if self.best_sample:
                print(f"得分最高的样本是: {self.best_sample}, 得分: {best_score}")
                # 尝试找到样本原图路径
                potential_path = join_path(config.SAMPLE_PATH, self.detect_group, self.best_sample)
                if os.path.exists(potential_path):
                    self.best_sample_path = potential_path
                    print(f"找到最佳样本原图路径: {self.best_sample_path}")
            
            # 筛选出超过阈值的图像文件
            defect_image_files = []
            for image_file in all_image_files:
                # 提取原始文件名（去掉热图后缀）
                name_parts = image_file.split('_')
                if len(name_parts) > 1:
                    # 假设热图命名格式为: original_name_3.jpg
                    # 尝试提取原始文件名
                    possible_name = '_'.join(name_parts[:-1])
                    for ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                        original_name = possible_name + ext
                        if original_name in score_map:
                            score = score_map[original_name]
                            # 检查得分是否超过阈值
                            if score >= threshold:
                                print(f"图像 {image_file} 得分为 {score}，超过阈值 {threshold}，添加到缺陷列表")
                                defect_image_files.append(image_file)
                            else:
                                print(f"图像 {image_file} 得分为 {score}，低于阈值 {threshold}，跳过")
                            break
                    else:
                        # 如果找不到匹配的原始文件名，默认添加
                        print(f"无法在检测列表中找到 {image_file} 对应的原始文件名，将其添加到缺陷列表")
                        defect_image_files.append(image_file)
                else:
                    # 如果文件名格式不符合预期，默认添加
                    defect_image_files.append(image_file)
            
            # 处理每个超过阈值的缺陷图像
            for i, image_file in enumerate(defect_image_files):
                image_path = join_path(self.result_path, image_file)
                print(f"处理缺陷图像: {image_path}")
                
                # 检查文件是否存在且可读
                if not os.path.exists(image_path):
                    print(f"图像文件不存在: {image_path}")
                    continue
                
                try:
                    # 尝试读取图像，确保它是有效的
                    test_img = cv2.imread(image_path)
                    if test_img is None:
                        print(f"无法读取图像: {image_path}")
                        continue
                except Exception as e:
                    print(f"读取图像失败: {image_path}, 错误: {str(e)}")
                    continue
                
                # 添加缺陷图像
                self.defect_images.append({
                    'name': image_file,
                    'heatmap_path': image_path
                })
                
                # 更新进度
                if i % 5 == 0:  # 每5张图像更新一次进度
                    progress = int((i + 1) / len(defect_image_files) * 30)  # 总进度的30%用于加载图像
                    self.update_progress(progress, f"加载图像 {i+1}/{len(defect_image_files)}...")
            
            self.update_progress(30, f"已加载缺陷图像: {len(self.defect_images)}张，总共: {self.image_count}张")
            return len(self.defect_images)
        
        except Exception as e:
            error_msg = f"加载图像文件时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.update_progress(30, f"加载图像出错: {str(e)}")
            raise RuntimeError(error_msg)
    
    def extract_defect_features(self, grid_size=8):
        """
        从热图中提取缺陷特征和位置，同时进行图像区域特征统计分析
        
        Args:
            grid_size: 网格划分数量，将图像均匀划分为grid_size×grid_size个区域，默认为8×8网格
        """
        try:
            self.update_progress(30, "开始提取缺陷特征...")
            self.heatmap_data = []
            self.defect_positions = []
            self.texture_features = []
            
            for img_idx, img_info in enumerate(self.defect_images):
                # 读取热图
                heatmap_path = img_info['heatmap_path']
                print(f"读取热图: {heatmap_path}")
                
                heatmap = cv2.imread(heatmap_path)
                if heatmap is None:
                    print(f"无法读取热图: {heatmap_path}")
                    continue
                    
                # 输出图像形状以进行调试
                print(f"热图形状: {heatmap.shape}")
                
                # 转换为灰度图
                heatmap_gray = cv2.cvtColor(heatmap, cv2.COLOR_BGR2GRAY)
                
                # 归一化灰度值
                heatmap_norm = heatmap_gray / 255.0
                
                # 二值化，提取高热区域（缺陷区域）
                _, heatmap_thresh = cv2.threshold(heatmap_gray, 150, 255, cv2.THRESH_BINARY)
                
                # 查找缺陷区域轮廓
                contours, _ = cv2.findContours(heatmap_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                print(f"找到 {len(contours)} 个轮廓")
                
                # 处理每个轮廓
                contour_count = 0
                for contour in contours:
                    # 计算轮廓面积，过滤掉太小的区域
                    area = cv2.contourArea(contour)
                    if area < 50:  # 面积阈值
                        continue
                        
                    contour_count += 1
                    
                    # 获取缺陷区域的包围框
                    x, y, w, h = cv2.boundingRect(contour)
                    
                    # 缺陷中心位置（相对坐标，范围0-1）
                    center_x = (x + w/2) / heatmap.shape[1]
                    center_y = (y + h/2) / heatmap.shape[0]
                    
                    # 提取缺陷区域的纹理特征
                    mask = np.zeros_like(heatmap_gray)
                    cv2.drawContours(mask, [contour], 0, 255, -1)
                    
                    # 提取纹理特征 - 使用GLCM (Gray Level Co-occurrence Matrix)
                    # 在这里简化为直方图特征和基本统计特征
                    roi = cv2.bitwise_and(heatmap_gray, mask)
                    roi_valid = roi[roi > 0]
                    
                    if len(roi_valid) > 0:
                        # 基本统计特征
                        mean_val = np.mean(roi_valid)
                        std_val = np.std(roi_valid)
                        max_val = np.max(roi_valid)
                        
                        # 计算梯度特征（简化的纹理特征）
                        roi_float = roi.astype(float)
                        grad_x = cv2.Sobel(roi_float, cv2.CV_64F, 1, 0, ksize=3)
                        grad_y = cv2.Sobel(roi_float, cv2.CV_64F, 0, 1, ksize=3)
                        grad_mag = np.sqrt(grad_x**2 + grad_y**2)
                        
                        # 在有效区域计算梯度均值
                        grad_mean = np.mean(grad_mag[mask > 0])
                        
                        # 存储缺陷位置
                        self.defect_positions.append({
                            'image': img_info['name'],
                            'center_x': center_x,
                            'center_y': center_y,
                            'width': w / heatmap.shape[1],
                            'height': h / heatmap.shape[0],
                            'area': area / (heatmap.shape[0] * heatmap.shape[1])
                        })
                        
                        # 存储纹理特征
                        self.texture_features.append({
                            'image': img_info['name'],
                            'position': (center_x, center_y),
                            'mean': mean_val, # 均值
                            'std': std_val, # 标准差
                            'max': max_val, # 最大值
                            'gradient': grad_mean, # 梯度均值
                            'area': area # 面积
                        })
                
                # 输出有效轮廓数量
                print(f"有效轮廓数量: {contour_count}")
                
                # 存储热图数据
                self.heatmap_data.append({
                    'image': img_info['name'],
                    'heatmap': heatmap_norm
                })
                
                # 查找原始图像路径的基本路径
                original_sample_path = join_path(config.SAMPLE_PATH, self.detect_group)
            
                # 尝试找到检测热图对应的原始图像（热图文件名格式通常为 original_name_X.jpg）
                original_image = None
                image_name = img_info['name']
                original_name = None
                name_parts = image_name.split('_')

                # 移除最后一个组件，因为它可能是热图类型指示器
                possible_name = '_'.join(name_parts[:-1])
                
                # 尝试查找原始样本中是否有这个名称的图像
                for ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                    full_name = possible_name + ext
                    original_path = join_path(original_sample_path, full_name)
                    if os.path.exists(original_path):
                        original_name = full_name
                        break
                
                # 如果找到了原始图像名称，尝试加载它
                if original_name:
                    print(f"尝试读取原始图像: {original_path}")
                    if os.path.exists(original_path):
                        original_image = cv2.imread(original_path)
                        if original_image is not None:
                            print(f"成功加载原始图像: {original_path}")
                        else:
                            print(f"无法读取原始图像: {original_path}")
                else:
                    print(f"未找到热图 {image_name} 对应的原始图像")
                
                # 分析网格 - 现在优先使用原始图像进行分析
                try:
                    # 新逻辑：必须使用原始图像进行分析，热图仅用于确定异常区域
                    if original_image is None:
                        print(f"警告：无法找到热图 {image_name} 对应的原始图像，跳过此图像的分析")
                        continue
                    
                    # 使用原始图像进行分析
                    analyze_image = original_image
                    
                    # 如果图像是彩色的，转换为灰度图
                    if len(analyze_image.shape) == 3:
                        analyze_gray = cv2.cvtColor(analyze_image, cv2.COLOR_BGR2GRAY)
                    else:
                        analyze_gray = analyze_image
                    
                    # 计算Sobel边缘(针对原始图像)
                    analyze_sobel_x = cv2.Sobel(analyze_gray, cv2.CV_64F, 1, 0, ksize=3)
                    analyze_sobel_y = cv2.Sobel(analyze_gray, cv2.CV_64F, 0, 1, ksize=3)
                    analyze_sobel_mag = cv2.magnitude(analyze_sobel_x, analyze_sobel_y)
                    analyze_sobel_mag = cv2.normalize(analyze_sobel_mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                    _, analyze_edge_mask = cv2.threshold(analyze_sobel_mag, 50, 1, cv2.THRESH_BINARY)
                    
                    # 获取图像尺寸
                    height, width = analyze_gray.shape
                    
                    # 创建一个掩码来表示异常区域（从热图获取）
                    # 将热图二值化以获取异常区域掩码
                    _, anomaly_mask = cv2.threshold(heatmap_gray, 
                                                  int(np.mean(heatmap_gray) + 0.5 * np.std(heatmap_gray)), 
                                                  255, cv2.THRESH_BINARY)
                    
                    # 调整掩码大小以匹配原始图像
                    if anomaly_mask.shape != analyze_gray.shape:
                        anomaly_mask = cv2.resize(anomaly_mask, (width, height), 
                                                interpolation=cv2.INTER_NEAREST)
                    
                    # 确保掩码是二值的
                    _, anomaly_mask = cv2.threshold(anomaly_mask, 127, 1, cv2.THRESH_BINARY)
                    
                    # 使用形态学操作扩大异常区域，确保完全覆盖
                    kernel = np.ones((5, 5), np.uint8)
                    anomaly_mask = cv2.dilate(anomaly_mask, kernel, iterations=1)
                    
                    # 计算每个网格区域的大小
                    cell_height = height // grid_size
                    cell_width = width // grid_size
                    
                    # 如果网格太小，调整网格数量
                    if cell_height < 4 or cell_width < 4:
                        adjusted_grid_size = min(8, min(height // 4, width // 4))
                        cell_height = height // adjusted_grid_size
                        cell_width = width // adjusted_grid_size
                        print(f"网格太小，调整为{adjusted_grid_size}×{adjusted_grid_size}网格，每个区域大小为{cell_height}×{cell_width}像素")
                        grid_size = adjusted_grid_size
                    
                    # 创建两个列表分别存储异常区域和正常区域的特征
                    normal_grid_means = []
                    normal_grid_variances = []
                    normal_grid_edges = []
                    
                    anomaly_grid_means = []
                    anomaly_grid_variances = []
                    anomaly_grid_edges = []
                    
                    # 分析每个网格区域
                    for row in range(grid_size):
                        for col in range(grid_size):
                            # 确保不越界
                            if row*cell_height >= height or col*cell_width >= width:
                                continue
                                
                            # 计算区域坐标
                            y1 = row * cell_height
                            y2 = min((row + 1) * cell_height, height)
                            x1 = col * cell_width
                            x2 = min((col + 1) * cell_width, width)
                            
                            # 提取原始图像区域和对应的掩码区域
                            cell_img = analyze_gray[y1:y2, x1:x2]
                            cell_mask = anomaly_mask[y1:y2, x1:x2]
                            cell_edge = analyze_edge_mask[y1:y2, x1:x2]
                            
                            # 计算区域内异常像素的比例
                            region_size = (y2-y1) * (x2-x1)
                            if region_size > 0:
                                anomaly_count = np.sum(cell_mask)
                                anomaly_ratio = anomaly_count / region_size
                                
                                # 计算区域统计特征
                                mean_val = np.mean(cell_img)
                                std_val = np.std(cell_img)
                                edge_density = np.sum(cell_edge) / region_size
                                
                                # 判断是否为异常区域（当异常像素比例超过阈值时）
                                is_anomaly = anomaly_ratio > 0.3  # 异常比例阈值可调整
                                
                                # 根据异常标签分类特征
                                if is_anomaly:
                                    anomaly_grid_means.append(mean_val)
                                    anomaly_grid_variances.append(std_val**2)  # 方差是标准差的平方
                                    anomaly_grid_edges.append(edge_density)  # 边缘密度
                                else:
                                    normal_grid_means.append(mean_val)
                                    normal_grid_variances.append(std_val**2)
                                    normal_grid_edges.append(edge_density)
                
                except Exception as e:
                    print(f"处理图像 {img_info['name']} 的网格区域时出错: {str(e)}")
                
                # 更新进度
                progress = 30 + int((img_idx + 1) / len(self.defect_images) * 30)  # 30%-60%的进度用于特征提取
                self.update_progress(progress, f"提取缺陷特征 {img_idx+1}/{len(self.defect_images)}...")
            
            # 为了便于后续使用，我们计算一些统计量
            if normal_grid_means:
                normal_mean_avg = np.mean(normal_grid_means)
                normal_variance_avg = np.mean(normal_grid_variances)
                normal_edge_avg = np.mean(normal_grid_edges)
            else:
                normal_mean_avg = 0
                normal_variance_avg = 0
                normal_edge_avg = 0
                
            if anomaly_grid_means:
                anomaly_mean_avg = np.mean(anomaly_grid_means)
                anomaly_variance_avg = np.mean(anomaly_grid_variances)
                anomaly_edge_avg = np.mean(anomaly_grid_edges)
            else:
                anomaly_mean_avg = 0
                anomaly_variance_avg = 0
                anomaly_edge_avg = 0
                
            # 计算整体平均值
            all_means = normal_grid_means + anomaly_grid_means
            all_variances = normal_grid_variances + anomaly_grid_variances
            all_edges = normal_grid_edges + anomaly_grid_edges
            
            mean_avg = np.mean(all_means) if all_means else 0
            variance_avg = np.mean(all_variances) if all_variances else 0
            edges_avg = np.mean(all_edges) if all_edges else 0
            
            # 创建直方图数据
            mean_hist, mean_bins = np.histogram(all_means, bins=20) if all_means else ([], [])
            variance_hist, variance_bins = np.histogram(all_variances, bins=20) if all_variances else ([], [])
            edges_hist, edges_bins = np.histogram(all_edges, bins=20) if all_edges else ([], [])
            
            # 保存网格区域统计
            self.patch_statistics = {
                'patch_size': grid_size,
                'mean_avg': mean_avg,
                'variance_avg': variance_avg,
                'edges_avg': edges_avg,
                'mean_histogram': mean_hist.tolist() if isinstance(mean_hist, np.ndarray) else mean_hist,
                'mean_bin_edges': mean_bins.tolist() if isinstance(mean_bins, np.ndarray) else mean_bins,
                'variance_histogram': variance_hist.tolist() if isinstance(variance_hist, np.ndarray) else variance_hist,
                'variance_bin_edges': variance_bins.tolist() if isinstance(variance_bins, np.ndarray) else variance_bins,
                'edges_histogram': edges_hist.tolist() if isinstance(edges_hist, np.ndarray) else edges_hist,
                'edges_bin_edges': edges_bins.tolist() if isinstance(edges_bins, np.ndarray) else edges_bins,
                # 添加分类后的数据
                'normal_means': normal_grid_means,
                'normal_variances': normal_grid_variances,
                'normal_edges': normal_grid_edges,
                'anomaly_means': anomaly_grid_means,
                'anomaly_variances': anomaly_grid_variances,
                'anomaly_edges': anomaly_grid_edges,
                'normal_mean_avg': normal_mean_avg,
                'anomaly_mean_avg': anomaly_mean_avg,
                'normal_variance_avg': normal_variance_avg,
                'anomaly_variance_avg': anomaly_variance_avg,
                'normal_edge_avg': normal_edge_avg,
                'anomaly_edge_avg': anomaly_edge_avg,
                # 添加原来格式的统计数据，以保持兼容性
                'normal_regions': {
                    'count': len(normal_grid_means),
                    'mean_avg': normal_mean_avg,
                    'variance_avg': normal_variance_avg,
                    'edges_avg': normal_edge_avg
                },
                'anomaly_regions': {
                    'count': len(anomaly_grid_means),
                    'mean_avg': anomaly_mean_avg,
                    'variance_avg': anomaly_variance_avg,
                    'edges_avg': anomaly_edge_avg
                }
            }
            
            self.update_progress(60, f"已提取缺陷特征: {len(self.defect_positions)}个，分析了{len(all_means)}个网格区域")
            return len(self.defect_positions)
            
        except Exception as e:
            error_msg = f"提取缺陷特征时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.update_progress(60, f"提取特征出错: {str(e)}")
            raise RuntimeError(error_msg)

    def cluster_defect_positions(self, eps=0.1, min_samples=3):
        """
        聚类分析缺陷位置，找出缺陷频繁出现的区域
        
        Args:
            eps: DBSCAN的邻域半径参数
            min_samples: DBSCAN的最小样本数参数
        """
        try:
            self.update_progress(60, "开始聚类分析...")
            
            if not self.defect_positions:
                print("没有缺陷位置数据可供聚类")
                self.cluster_results = {
                    'total_defects': 0,
                    'clusters': [],
                    'noise': 0
                }
                return self.cluster_results
                
            print(f"进行聚类分析，数据点数量: {len(self.defect_positions)}")
            # 提取位置坐标
            positions = np.array([[d['center_x'], d['center_y']] for d in self.defect_positions])
            
            # 使用DBSCAN聚类
            clustering = DBSCAN(eps=eps, min_samples=min_samples).fit(positions)
            
            # 获取聚类标签
            labels = clustering.labels_
            
            # 统计每个簇的数量
            cluster_counts = Counter(labels[labels >= 0])
            print(f"聚类结果：{len(cluster_counts)}个聚类")
            
            # 准备结果
            clusters = []
            for cluster_id, count in cluster_counts.items():
                # 获取该簇的所有点
                cluster_points = positions[labels == cluster_id]
                
                # 计算簇的中心和范围
                center = np.mean(cluster_points, axis=0)
                radius = np.max(np.linalg.norm(cluster_points - center, axis=1))
                
                clusters.append({
                    'id': int(cluster_id),
                    'center': center.tolist(),
                    'radius': float(radius),
                    'count': int(count),
                    'points': cluster_points.tolist()
                })
            
            # 按照包含点数排序
            clusters.sort(key=lambda x: x['count'], reverse=True)
            
            self.cluster_results = {
                'total_defects': len(positions),
                'clusters': clusters,
                'noise': int(np.sum(labels == -1))
            }
            
            self.update_progress(70, f"聚类分析完成: 找到{len(clusters)}个聚类")
            return self.cluster_results
            
        except Exception as e:
            error_msg = f"聚类分析时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.update_progress(70, f"聚类分析出错: {str(e)}")
            raise RuntimeError(error_msg)
    
    def analyze_defect_texture(self):
        """
        分析缺陷特征，判断缺陷类型（基于亮度特征）
        """
        try:
            self.update_progress(70, "开始分析缺陷类型...")
            
            if not self.texture_features:
                print("没有缺陷特征数据可供分析")
                return {
                    'texture_counts': {},
                    'defect_details': []
                }
            
            print(f"分析缺陷类型，缺陷数量: {len(self.texture_features)}")
            
            # 定义亮度阈值
            LOW_BRIGHTNESS_THRESHOLD = 80  # 低亮度阈值
            HIGH_BRIGHTNESS_THRESHOLD = 180  # 高亮度阈值
            EXTREME_BRIGHTNESS_THRESHOLD = 220  # 极高亮度阈值
            
            # 创建缺陷位置字典，方便查找
            defect_pos_map = {}
            for pos in self.defect_positions:
                key = f"{pos['image']}_{pos['center_x']}_{pos['center_y']}"
                defect_pos_map[key] = pos
            
            defect_types = []
            for feature in self.texture_features:
                # 提取特征并转换为Python原生类型
                mean_val = float(feature['mean'])      # 亮度均值
                max_val = float(feature['max'])        # 最大亮度值
                
                # 查找对应的归一化面积
                pos_key = f"{feature['image']}_{feature['position'][0]}_{feature['position'][1]}"
                pos_data = defect_pos_map.get(pos_key)
                
                if pos_data:
                    # 使用defect_positions中已经归一化的面积
                    normalized_area = float(pos_data['area'])
                else:
                    # 如果找不到对应数据，使用texture_features中的面积（可能需要归一化）
                    # 这里假设面积是像素数，设置一个非常小的默认值
                    normalized_area = float(feature['area']) / 88888 # 假设平均图像大小约为88888像素
                
                # 打印面积值，用于调试
                # print(f"缺陷归一化面积: {normalized_area}, 原始面积: {feature['area']}")
                
                # 形状特征
                aspect_ratio = 1.0  # 默认值
                if pos_data:
                    width = float(pos_data['width'])
                    height = float(pos_data['height'])
                    if height > 0:
                        aspect_ratio = width / height
                print(f"最大亮度值: {max_val}, 亮度均值: {mean_val}, 归一化面积: {normalized_area}, 形状比例: {aspect_ratio}")
                # 基于亮度和形状特征的缺陷分类（详细分类）
                # 判定条件根据样本数据进行调整：
                # 000-002为严重损坏样本，003-006为正常/轻微污染样本，007-021为中度缺陷/轻度异常样本
                
                # 打印特征信息用于调试
                print(f"样本: {feature['image']}, 最大亮度值: {max_val}, 亮度均值: {mean_val}, 归一化面积: {normalized_area}, 形状比例: {aspect_ratio}")
                
                # 严重损坏类别判断
                if normalized_area > 0.03 and max_val > 210:  # 大面积高亮度缺陷
                    main_type = "严重损坏"
                    detail_type = "大缺口"
                elif normalized_area > 0.02 and max_val > 200:  # 较大面积中高亮度
                    main_type = "严重损坏"
                    detail_type = "大面积缺陷"
                # 中度缺陷类别判断
                elif normalized_area > 0.01 and max_val > 210:  # 中等面积高亮度
                    main_type = "中度缺陷"
                    if aspect_ratio > 1.8:  # 细长形状
                        detail_type = "划痕"
                    elif normalized_area > 0.015:
                        detail_type = "大面积缺陷"
                    else:
                        detail_type = "小缺口"
                elif normalized_area > 0.007 and max_val > 210:  # 小面积高亮度
                    main_type = "中度缺陷"
                    if aspect_ratio > 1.8:
                        detail_type = "划痕"
                    else:
                        detail_type = "小缺口"
                # 轻度异常类别判断
                elif normalized_area > 0.007 and max_val > 180:  # 中小面积中等亮度
                    main_type = "轻度异常"
                    detail_type = "小面积异常"
                elif normalized_area > 0.005 and max_val > 170:  # 小面积中等亮度
                    main_type = "轻度异常"
                    detail_type = "小面积异常"
                elif max_val > 190:  # 高亮度点
                    main_type = "轻度异常"
                    detail_type = "小面积异常"
                # 轻微污染或正常
                else:
                    main_type = "轻微污染"
                    detail_type = "小面积污染"
                
                defect_types.append({
                    'image': feature['image'],
                    'position': (float(feature['position'][0]), float(feature['position'][1])),
                    'defect_type': detail_type,  # 详细类型
                    'main_type': main_type,      # 主要类型
                    'mean': float(mean_val),
                    'max': float(max_val),
                    'area': float(feature['area']),
                    'normalized_area': normalized_area,
                    'aspect_ratio': float(aspect_ratio)
                })
            
            # 统计各主要类型和详细类型缺陷的数量
            main_type_counts = Counter([item['main_type'] for item in defect_types])
            detail_type_counts = Counter([item['defect_type'] for item in defect_types])
            
            print(f"主要缺陷类型分布: {dict(main_type_counts)}")
            print(f"详细缺陷类型分布: {dict(detail_type_counts)}")
            
            # 计算每个图像的主要缺陷类型
            image_defect_types = {}
            for defect in defect_types:
                image_name = defect['image']
                main_type = defect['main_type']
                
                if image_name not in image_defect_types:
                    image_defect_types[image_name] = []
                
                image_defect_types[image_name].append(main_type)
            
            # 缺陷严重程度排序（从高到低）
            # 注意：一个样本的缺陷类型由最严重的缺陷区域类型决定，而不是数量最多的缺陷类型
            severity_order = {
                "严重损坏": 4,  # 最严重
                "中度缺陷": 3,
                "轻度异常": 2,
                "轻微污染": 1   # 最轻微
            }
            
            # 对每个图像，确定主要缺陷类型（基于最严重的缺陷类型）
            image_main_type = {}
            for image_name, types in image_defect_types.items():
                # 找出该图像中最严重的缺陷类型
                most_severe_type = max(types, key=lambda t: severity_order.get(t, 0))
                image_main_type[image_name] = most_severe_type
            
            # 统计每种主要缺陷类型有多少个样本
            sample_main_type_counts = Counter(image_main_type.values())
            print(f"样本主要缺陷类型分布: {dict(sample_main_type_counts)}")
            
            # 生成主要类型与详细类型的映射关系描述
            type_description = {
                "轻微污染": f"（包括：{detail_type_counts.get('小面积污染', 0)}个小面积污染, {detail_type_counts.get('大面积污染', 0)}个大面积污染）",
                "轻度异常": f"（包括：{detail_type_counts.get('小面积异常', 0)}个小面积异常，{detail_type_counts.get('大面积异常', 0)}个大面积异常）",
                "中度缺陷": f"（包括：{detail_type_counts.get('划痕', 0)}个划痕, {detail_type_counts.get('小缺口', 0)}个小缺口, {detail_type_counts.get('大面积缺陷', 0)}个大面积缺陷）",
                "严重损坏": f"（包括：{detail_type_counts.get('裂缝', 0)}个裂缝, {detail_type_counts.get('大缺口', 0)}个大缺口）"
            }
            
            # 返回分析结果，保持键名兼容
            defect_analysis = {
                'texture_counts': dict(main_type_counts),  # 使用原键名但返回主要类型计数
                'defect_type_counts': dict(detail_type_counts),  # 详细类型计数
                'main_type_counts': dict(main_type_counts),  # 主要类型计数
                'sample_main_type_counts': dict(sample_main_type_counts),  # 样本主要类型计数
                'defect_details': defect_types,
                'type_description': type_description,  # 添加类型描述
                'image_main_type': image_main_type  # 每张图像的主要缺陷类型
            }
            
            self.update_progress(80, "缺陷类型分析完成")
            return defect_analysis
            
        except Exception as e:
            error_msg = f"缺陷类型分析时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.update_progress(80, f"缺陷类型分析出错: {str(e)}")
            raise RuntimeError(error_msg)
    
    def generate_report(self):
        """
        生成缺陷分析报告
        """
        try:
            self.update_progress(30, "开始加载缺陷图像...")
            
            # 1. 加载缺陷图像 (从load_defect_images方法移入的逻辑)
            defect_count = self.load_defect_images(self.threshold)  # 使用类的threshold属性
            if defect_count == 0:
                error_msg = "没有足够的缺陷图像用于分析"
                print(error_msg)
                self.update_progress(100, "所有检测样本良好，无需生成缺陷检测报告!")
                return None
            
            # 2. 提取缺陷特征 (从extract_defect_features方法移入的逻辑)
            self.update_progress(40, "开始提取缺陷特征...")
            feature_count = self.extract_defect_features(self.grid_size)  # 使用类的grid_size属性
            if feature_count == 0:
                error_msg = "未能提取到有效的缺陷特征"
                print(error_msg)
                self.update_progress(100, error_msg)
                raise ValueError(error_msg)
            
            # 3. 执行聚类分析 (从cluster_defect_positions方法移入的逻辑)
            self.update_progress(60, "开始进行缺陷位置聚类分析...")
            if self.cluster_results is None:
                self.cluster_defect_positions(self.eps, self.min_samples)  # 使用类的eps和min_samples属性
            
            # 4. 分析缺陷特征 (从analyze_defect_texture方法移入的逻辑)
            self.update_progress(70, "开始分析缺陷类型...")
            texture_analysis = self.analyze_defect_texture()
            
            # 5. 生成报告数据
            self.update_progress(80, "分析完毕，开始生成报告...")
            
            # 检查是否有足够的数据
            if not self.defect_positions or not self.texture_features:
                error_msg = "没有足够的缺陷数据用于分析"
                print(error_msg)
                raise ValueError(error_msg)
                
            # 准备报告数据
            report = {
                'detect_group': self.detect_group,
                'total_images': self.image_count,
                'defect_images': len(self.defect_images),
                'defect_positions': len(self.defect_positions),
                'position_clusters': self.cluster_results,
                'texture_analysis': texture_analysis,
                'patch_statistics': self.patch_statistics,
                'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S")
            }
            
            # 保存报告
            report_file = join_path(self.report_path, f"defect_analysis_{report['timestamp']}.json")
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
                
            # 生成缺陷位置分布图
            chart_path = self.generate_defect_position_chart(report, report['timestamp'])
            self.update_progress(90, "缺陷位置分布图生成完成")
            
            # 生成统计图表
            chart_paths = self.generate_statistical_charts(report)
            
            self.update_progress(100, "报告生成完成")
            
            return {
                'report_file': report_file,
                'chart_file': chart_path,
                'report_data': report,
                **chart_paths
            }
            
        except Exception as e:
            error_msg = f"生成报告时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.update_progress(100, f"生成报告出错: {str(e)}")
            raise RuntimeError(error_msg)

    def generate_defect_position_chart(self, report, timestamp):
        """
        生成缺陷位置分布图
        
        Args:
            report: 报告数据
            timestamp: 时间戳
        """
        try:
            # 设置matplotlib中文字体支持
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial Unicode MS']  # 中文字体
            plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
            plt.rcParams['font.family'] = 'sans-serif'  # 设置字体族
            
            # 创建图形
            fig = plt.figure(figsize=(10, 10))
            plt.suptitle(f"缺陷位置分析报告 - {self.detect_group}", fontsize=16)
            
            # 创建单个图表
            ax = plt.subplot(1, 1, 1)
            ax.set_title("缺陷位置分布热图")
            
            # 尝试加载最佳样本图片作为背景
            background_loaded = False
            background_width = 50  # 默认宽度
            background_height = 50  # 默认高度
            
            if self.best_sample_path and os.path.exists(self.best_sample_path):
                try:
                    # 读取图像并转换为RGB
                    background_img = cv2.imread(self.best_sample_path)
                    background_img = cv2.cvtColor(background_img, cv2.COLOR_BGR2RGB)
                    background_width = background_img.shape[1]
                    background_height = background_img.shape[0]
                    
                    # 显示背景图像
                    ax.imshow(background_img, aspect='auto')
                    background_loaded = True
                    print(f"成功加载背景图像: {self.best_sample_path}")
                except Exception as e:
                    print(f"加载背景图像失败: {str(e)}")
            else:
                print(f"未找到背景图像或路径无效: {self.best_sample_path}")
                
                # 尝试使用第一个热图作为背景
                if self.defect_images:
                    try:
                        sample_path = self.defect_images[0].get('heatmap_path')
                        if sample_path and os.path.exists(sample_path):
                            background_img = cv2.imread(sample_path)
                            background_img = cv2.cvtColor(background_img, cv2.COLOR_BGR2RGB)
                            background_width = background_img.shape[1]
                            background_height = background_img.shape[0]
                            
                            # 显示背景图像
                            ax.imshow(background_img, aspect='auto')
                            background_loaded = True
                            print(f"使用第一个热图作为背景: {sample_path}")
                    except Exception as e:
                        print(f"加载替代背景图像失败: {str(e)}")
            
            # 如果背景加载失败，使用白色背景
            if not background_loaded:
                ax.set_facecolor('white')
                ax.set_xlim(0, background_width)
                ax.set_ylim(0, background_height)
                print("使用白色背景")
            
            # 创建热力图
            heatmap = np.zeros((50, 50))
            for pos in self.defect_positions:
                x = int(pos['center_x'] * 49)
                y = int(pos['center_y'] * 49)
                heatmap[y, x] += 1
                
            # 应用高斯模糊平滑热力图
            heatmap = cv2.GaussianBlur(heatmap, (5, 5), 0)
            
            # 显示热力图，设置透明度
            im = ax.imshow(heatmap, cmap='hot', interpolation='nearest', alpha=0.7, extent=[0, background_width, background_height, 0])
            plt.colorbar(im, ax=ax, label='缺陷频率')
            
            # 在图上标注缺陷聚类中心
            for i, cluster in enumerate(report['position_clusters']['clusters']):
                center = cluster['center']
                count = cluster['count']
                
                # 计算实际坐标
                x = center[0] * background_width
                y = center[1] * background_height
                
                # 绘制聚类中心
                ax.plot(x, y, 'go', markersize=18, alpha=0.7)
                ax.annotate(f"C{i+1}: {count}个", 
                            xy=(x, y), 
                            xytext=(x+30, y+30),
                            color='white',
                            fontweight='bold',
                            fontsize=18,
                            bbox=dict(facecolor='black', alpha=0.5))
            
            # 保存图形
            plt.tight_layout(rect=[0, 0, 1, 0.95])
            fig_path = join_path(self.report_path, f"defect_analysis_{timestamp}.png")
            plt.savefig(fig_path, dpi=150)
            plt.close()
            
            return fig_path
            
        except Exception as e:
            error_msg = f"生成可视化报告时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            # 创建一个简单的错误图像
            ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, f"Error generating report: {str(e)}", 
                   ha='center', va='center', fontsize=12)
            ax.axis('off')
            fig_path = join_path(self.report_path, f"defect_analysis_error_{timestamp}.png")
            plt.savefig(fig_path, dpi=100)
            plt.close()
            return fig_path

    def generate_statistical_charts(self, report):
        """
        生成统计图表并保存到指定路径
        
        Args:
            report: 报告数据字典
        
        Returns:
            包含图表文件路径的字典
        """
        try:
            import time
            import matplotlib.pyplot as plt
            import os
            
            # 设置matplotlib中文字体支持
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial Unicode MS']  # 中文字体
            plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
            plt.rcParams['font.family'] = 'sans-serif'  # 设置字体族
            
            # 使用与其他报告图表相同的时间戳格式
            timestamp = report['timestamp']
            chart_paths = {}
            
            # 1. 生成网格区域特征统计直方图
            if 'patch_statistics' in report and report['patch_statistics']:
                try:
                    # 获取统计数据
                    patch_stats = report['patch_statistics']
                    
                    # 创建一个临时的图像文件存储直方图
                    plt.figure(figsize=(8, 10))
                    
                    # 绘制区域亮度直方图（使用均值：方差丢失了亮度的绝对水平信息，相同方差的区域可能一个是亮区一个是暗区）
                    plt.subplot(3, 1, 1)
                    plt.title('区域亮度分布')
                    mean_bins = patch_stats.get('mean_bin_edges', [])
                    normal_means = patch_stats.get('normal_means', [])
                    anomaly_means = patch_stats.get('anomaly_means', [])
                    
                    if normal_means or anomaly_means:
                        # 使用相同的bin设置来保证正常和异常区域的直方图可比较
                        bin_count = 20
                        min_val = min(normal_means + anomaly_means) if normal_means + anomaly_means else 0
                        max_val = max(normal_means + anomaly_means) if normal_means + anomaly_means else 1
                        bin_range = (min_val, max_val)
                        
                        # 分别绘制正常和异常区域的直方图
                        if normal_means:
                            plt.hist(normal_means, bins=bin_count, range=bin_range, alpha=0.7, color='green', 
                                    density=True, label='正常区域', edgecolor='black', linewidth=0.5)
                        
                        if anomaly_means:
                            plt.hist(anomaly_means, bins=bin_count, range=bin_range, alpha=0.7, color='red', 
                                    density=True, label='异常区域', edgecolor='black', linewidth=0.5)
                        
                        plt.legend()
                    elif len(mean_bins) >= 2:
                        # 如果没有按正常/异常分类的数据，则使用总体数据
                        bin_centers = [(mean_bins[i] + mean_bins[i+1])/2 for i in range(len(mean_bins)-1)]
                        hist_values = patch_stats.get('mean_histogram', [])
                        
                        # 将直方图数据转换为出现频率
                        total_regions = sum(hist_values)
                        if total_regions > 0:
                            frequency = [count / total_regions for count in hist_values]
                        else:
                            frequency = hist_values
                        
                        # 区分正常和异常区域，显示实际分布的叠加效果而非完全分离
                        plt.bar(bin_centers, frequency, width=(mean_bins[1]-mean_bins[0])*0.8, 
                            color='lightgray', alpha=0.7, label='总体分布')
                        plt.legend()
                    else:
                        plt.text(0.5, 0.5, '无均值数据', ha='center', va='center')
                    
                    plt.grid(True, alpha=0.3)
                    plt.xlabel('亮度值')
                    plt.ylabel('出现频率')
                    
                    # 绘制区域纹理复杂度直方图（使用方差：不同纹理复杂度的区域可能有相同的均值，无法区分平滑区域和复杂但亮度平衡的纹理区域）
                    plt.subplot(3, 1, 2)
                    plt.title('区域纹理复杂度分布')
                    var_bins = patch_stats.get('variance_bin_edges', [])
                    normal_variances = patch_stats.get('normal_variances', [])
                    anomaly_variances = patch_stats.get('anomaly_variances', [])
                    
                    if normal_variances or anomaly_variances:
                        # 使用相同的bin设置来保证正常和异常区域的直方图可比较
                        bin_count = 20
                        min_val = min(normal_variances + anomaly_variances) if normal_variances + anomaly_variances else 0
                        max_val = max(normal_variances + anomaly_variances) if normal_variances + anomaly_variances else 1
                        bin_range = (min_val, max_val)
                        
                        # 分别绘制正常和异常区域的直方图
                        if normal_variances:
                            plt.hist(normal_variances, bins=bin_count, range=bin_range, alpha=0.7, color='green', 
                                    density=True, label='正常区域', edgecolor='black', linewidth=0.5)
                        
                        if anomaly_variances:
                            plt.hist(anomaly_variances, bins=bin_count, range=bin_range, alpha=0.7, color='red', 
                                    density=True, label='异常区域', edgecolor='black', linewidth=0.5)
                        
                        plt.legend()
                    elif len(var_bins) >= 2:
                        # 如果没有按正常/异常分类的数据，则使用总体数据
                        bin_centers = [(var_bins[i] + var_bins[i+1])/2 for i in range(len(var_bins)-1)]
                        hist_values = patch_stats.get('variance_histogram', [])
                        
                        # 将直方图数据转换为出现频率
                        total_regions = sum(hist_values)
                        if total_regions > 0:
                            frequency = [count / total_regions for count in hist_values]
                        else:
                            frequency = hist_values
                        
                        # 显示总体分布而非完全分离的正常/异常区域
                        plt.bar(bin_centers, frequency, width=(var_bins[1]-var_bins[0])*0.8, 
                            color='lightgray', alpha=0.7, label='总体分布')
                        plt.legend()
                    else:
                        plt.text(0.5, 0.5, '无方差数据', ha='center', va='center')
                    
                    plt.grid(True, alpha=0.3)
                    plt.xlabel('纹理复杂度值')
                    plt.ylabel('出现频率')
                    
                    # 绘制区域边缘密度直方图（使用Sobel边缘检测算子计算边缘密度）
                    plt.subplot(3, 1, 3)
                    plt.title('区域边缘密度分布')
                    edge_bins = patch_stats.get('edges_bin_edges', [])
                    normal_edges = patch_stats.get('normal_edges', [])
                    anomaly_edges = patch_stats.get('anomaly_edges', [])
                    
                    if normal_edges or anomaly_edges:
                        # 使用相同的bin设置来保证正常和异常区域的直方图可比较
                        bin_count = 20
                        min_val = min(normal_edges + anomaly_edges) if normal_edges + anomaly_edges else 0
                        max_val = max(normal_edges + anomaly_edges) if normal_edges + anomaly_edges else 1
                        bin_range = (min_val, max_val)
                        
                        # 分别绘制正常和异常区域的直方图
                        if normal_edges:
                            plt.hist(normal_edges, bins=bin_count, range=bin_range, alpha=0.7, color='green', 
                                    density=True, label='正常区域', edgecolor='black', linewidth=0.5)
                        
                        if anomaly_edges:
                            plt.hist(anomaly_edges, bins=bin_count, range=bin_range, alpha=0.7, color='red', 
                                    density=True, label='异常区域', edgecolor='black', linewidth=0.5)
                        
                        plt.legend()
                    elif len(edge_bins) >= 2:
                        # 如果没有按正常/异常分类的数据，则使用总体数据
                        bin_centers = [(edge_bins[i] + edge_bins[i+1])/2 for i in range(len(edge_bins)-1)]
                        hist_values = patch_stats.get('edges_histogram', [])
                        
                        # 将直方图数据转换为出现频率
                        total_regions = sum(hist_values)
                        if total_regions > 0:
                            frequency = [count / total_regions for count in hist_values]
                        else:
                            frequency = hist_values
                        
                        # 显示总体分布
                        plt.bar(bin_centers, frequency, width=(edge_bins[1]-edge_bins[0])*0.8, 
                            color='lightgray', alpha=0.7, label='总体分布')
                        plt.legend()
                    else:
                        plt.text(0.5, 0.5, '无边缘密度数据', ha='center', va='center')
                    
                    plt.grid(True, alpha=0.3)
                    plt.xlabel('边缘密度值')
                    plt.ylabel('出现频率')
                    
                    # 保存直方图文件之前设置tight_layout
                    plt.tight_layout()
                    
                    # 保存直方图文件
                    os.makedirs(self.report_path, exist_ok=True)
                    histogram_path = os.path.join(self.report_path, f"grid_histogram_{timestamp}.png")
                    plt.savefig(histogram_path)
                    plt.close()
                    
                    chart_paths['histogram_chart'] = histogram_path
                    print(f"区域特征直方图已保存: {histogram_path}")
                    
                except Exception as e:
                    print(f"生成区域统计图表时出错: {str(e)}")
            
            # 2. 生成缺陷类型分布饼图
            texture_counts = report['texture_analysis']['texture_counts']
            if texture_counts:
                try:
                    # 创建缺陷类型分布的饼图
                    plt.figure(figsize=(7, 5))
                    labels = list(texture_counts.keys())
                    sizes = list(texture_counts.values())
                    colors = ['#1976D2', '#4CAF50', '#FF9800', '#9C27B0', '#F44336', '#00BCD4', '#FFEB3B'][:len(labels)]
                    
                    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', 
                            shadow=False, startangle=90, textprops={'fontsize': 10})
                    plt.axis('equal')
                    plt.title('缺陷类型分布', fontsize=12)
                    
                    # 保存饼图文件
                    os.makedirs(self.report_path, exist_ok=True)
                    pie_chart_path = os.path.join(self.report_path, f"texture_pie_{timestamp}.png")
                    plt.savefig(pie_chart_path, dpi=120, bbox_inches='tight')
                    plt.close()
                    
                    chart_paths['pie_chart'] = pie_chart_path
                    print(f"缺陷类型饼图已保存: {pie_chart_path}")
                    
                except Exception as e:
                    print(f"生成缺陷类型饼图时出错: {str(e)}")
            
            return chart_paths
            
        except Exception as e:
            print(f"生成统计图表时出错: {str(e)}")
            return {}


def generate_pdf_report(report_data, report_path, chart_file=None, histogram_chart=None, pie_chart=None, output_filename=None):
    """
    生成PDF格式的缺陷分析报告
    
    Args:
        report_data: 报告数据字典
        report_path: 报告保存路径
        chart_file: 缺陷位置分布图路径
        histogram_chart: 网格特征直方图路径
        pie_chart: 缺陷类型分布饼图路径
        output_filename: 指定的输出文件路径，如果提供则直接使用该路径
    
    Returns:
        PDF报告文件路径，如果生成失败则返回None
    """
    if not HAS_REPORTLAB:
        print("未安装reportlab库，无法生成PDF报告")
        return None
        
    try:
        # 创建中文支持
        try:
            # 尝试注册中文字体
            pdfmetrics.registerFont(TTFont('SimSun', 'simsun.ttc'))
            pdfmetrics.registerFont(TTFont('SimHei', 'simhei.ttf'))
            cn_font_name = 'SimSun'
        except:
            # 如果中文字体注册失败，使用默认字体
            cn_font_name = 'Helvetica'
            print("未找到中文字体，使用默认字体")
            
        # 创建自定义样式
        styles = getSampleStyleSheet()
        
        # 修改样式名称，避免冲突
        styles.add(ParagraphStyle(
            name='ReportTitle',  # 改为ReportTitle避免与Title冲突
            fontName=cn_font_name,
            fontSize=18,
            alignment=1,  # 居中
            spaceAfter=12
        ))
        styles.add(ParagraphStyle(
            name='ReportHeading1',  # 改为ReportHeading1避免与Heading1冲突
            fontName=cn_font_name,
            fontSize=16,
            spaceAfter=10
        ))
        styles.add(ParagraphStyle(
            name='ReportHeading2',  # 改为ReportHeading2避免与Heading2冲突
            fontName=cn_font_name,
            fontSize=14,
            spaceAfter=12,  # 增加底部间距
            spaceBefore=12  # 增加顶部间距
        ))
        styles.add(ParagraphStyle(
            name='ReportNormal',  # 改为ReportNormal避免与Normal冲突
            fontName=cn_font_name,
            fontSize=12,
            leading=16
        ))
        # 添加图片说明样式
        styles.add(ParagraphStyle(
            name='ImageCaption',
            fontName=cn_font_name,
            fontSize=10,  # 较小的字体
            alignment=1,  # 居中
            spaceAfter=20,  # 增加更多的底部间距
            textColor=colors.gray
        ))
        # 添加斜体样式
        styles.add(ParagraphStyle(
            name='ReportItalic',
            fontName=cn_font_name,
            fontSize=10,
            leading=14,
            italic=True,  # 斜体
            textColor=colors.darkgrey
        ))
        # 添加注释样式
        styles.add(ParagraphStyle(
            name='ReportNote',
            fontName=cn_font_name,
            fontSize=9,
            leading=12,
            italic=True,
            textColor=colors.grey
        ))
        # 添加粗体样式
        styles.add(ParagraphStyle(
            name='ReportBold',
            fontName=cn_font_name,
            fontSize=12,
            leading=16,
            fontWeight='bold'  # 粗体
        ))
        
        # 确保报告目录存在
        os.makedirs(report_path, exist_ok=True)
        timestamp = report_data['timestamp']
        
        # 确定PDF文件保存路径
        if output_filename:
            pdf_filename = output_filename
        else:
            pdf_filename = os.path.join(report_path, f"defect_analysis_report_{timestamp}.pdf")
        
        # 创建PDF文档
        doc = SimpleDocTemplate(
            pdf_filename,
            pagesize=A4,
            rightMargin=1*cm,
            leftMargin=1*cm,
            topMargin=2*cm,
            bottomMargin=2*cm
        )
        
        # 准备报告内容
        content = []
        
        # 标题
        content.append(Paragraph(f"缺陷分析报告 - {report_data['detect_group']}", styles['ReportTitle']))
        content.append(Spacer(1, 0.5*cm))
        
        # 基本信息
        content.append(Paragraph("1. 基本信息", styles['ReportHeading1']))
        content.append(Spacer(1, 0.2*cm))
        
        # 格式化时间戳为正规日期格式
        try:
            date_obj = datetime.strptime(report_data['timestamp'], "%Y%m%d_%H%M%S")
            time_str = date_obj.strftime("%Y-%m-%d %H:%M:%S")
        except:
            time_str = report_data['timestamp']
            
        # 基本信息表格
        basic_data = [
            ["检测组", report_data['detect_group']],
            ["总图像数", str(report_data['total_images'])],
            ["缺陷图像数", str(report_data['defect_images'])],
            ["缺陷位置总数", str(report_data['defect_positions'])],
            ["分析时间", time_str]
        ]
        
        basic_table = Table(basic_data, colWidths=[4*cm, 10*cm])
        basic_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), cn_font_name),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        
        content.append(basic_table)
        content.append(Spacer(1, 0.5*cm))
        
        # 缺陷位置分析
        content.append(Paragraph("2. 缺陷位置分析", styles['ReportHeading1']))
        content.append(Spacer(1, 0.2*cm))
        
        # 添加缺陷位置描述
        clusters = report_data['position_clusters']['clusters']
        noise_count = report_data['position_clusters']['noise']
        total_defects = report_data['defect_positions']
        
        if clusters:
            # 生成分布描述
            if len(clusters) == 1:
                distribution_pattern = "缺陷高度集中在一个区域"
            elif len(clusters) <= 3:
                distribution_pattern = f"缺陷主要集中在{len(clusters)}个区域"
            else:
                distribution_pattern = f"缺陷分布在{len(clusters)}个不同区域"
                
            # 计算聚类包含的缺陷比例
            clustered_defects = sum([c['count'] for c in clusters])
            clustered_ratio = clustered_defects / total_defects if total_defects > 0 else 0
            
            if clustered_ratio > 0.8:
                concentration = "非常集中"
            elif clustered_ratio > 0.6:
                concentration = "较为集中"
            elif clustered_ratio > 0.4:
                concentration = "分布均匀"
            else:
                concentration = "较为分散"
                
            content.append(Paragraph(f"分布概况：{distribution_pattern}，整体分布{concentration}。", styles['ReportNormal']))
            
            # 描述主要聚类
            if clusters:
                max_cluster = clusters[0]  # 已按大小排序
                center_x, center_y = max_cluster['center']
                content.append(Paragraph(
                    f"主要聚类：最大的聚类区域位于坐标({center_x:.3f}, {center_y:.3f})附近，包含{max_cluster['count']}个缺陷点，"
                    f"占总缺陷的{(max_cluster['count']/total_defects*100):.1f}%。", 
                    styles['ReportNormal']
                ))
                
            # 描述噪声点情况
            if noise_count > 0:
                noise_ratio = noise_count / total_defects if total_defects > 0 else 0
                if noise_ratio > 0.3:
                    noise_desc = "大量"
                elif noise_ratio > 0.1:
                    noise_desc = "部分"
                else:
                    noise_desc = "少量"
                    
                content.append(Paragraph(
                    f"离散缺陷：存在{noise_desc}离散缺陷点（{noise_count}个，占比{noise_ratio*100:.1f}%），这些点未形成明显聚类。",
                    styles['ReportNormal']
                ))
        
        content.append(Spacer(1, 0.3*cm))
        
        # 添加缺陷位置热图
        if chart_file and os.path.exists(chart_file):
            try:
                img = Image(chart_file, width=15*cm, height=15*cm)
                content.append(img)
                content.append(Paragraph("图1. 缺陷位置分布热图（颜色越亮表示缺陷出现频率越高，绿色圆点表示聚类中心）", styles['ImageCaption']))
            except Exception as e:
                content.append(Paragraph(f"加载缺陷位置热图失败: {str(e)}", styles['ReportNormal']))
        
        # 聚类分析表格
        content.append(Paragraph("2.1 聚类分析结果", styles['ReportHeading2']))
        content.append(Spacer(1, 0.2*cm))
        
        content.append(Paragraph(f"聚类数量: {len(clusters)}", styles['ReportNormal']))
        if clusters:
            content.append(Paragraph(f"最大聚类包含: {clusters[0]['count']}个缺陷", styles['ReportNormal']))
            content.append(Paragraph("前3个聚类:", styles['ReportNormal']))
            
            # 创建聚类表格
            cluster_data = [["聚类ID", "中心位置", "半径", "缺陷数量"]]
            for i, cluster in enumerate(clusters[:3]):
                cluster_data.append([
                    f"聚类 {i+1}",
                    f"({cluster['center'][0]:.2f}, {cluster['center'][1]:.2f})",
                    f"{cluster['radius']:.3f}",
                    str(cluster['count'])
                ])
                
            cluster_table = Table(cluster_data, colWidths=[3*cm, 5*cm, 3*cm, 3*cm])
            cluster_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, -1), cn_font_name),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            
            content.append(cluster_table)
            content.append(Spacer(1, 0.3*cm))
            
        content.append(Spacer(1, 0.5*cm))
        
        # 区域特征统计分析
        if 'patch_statistics' in report_data and report_data['patch_statistics']:
            content.append(Paragraph("3. 区域特征统计分析", styles['ReportHeading1']))
            content.append(Spacer(1, 0.2*cm))
            
            patch_stats = report_data['patch_statistics']
            grid_size = patch_stats.get('patch_size', 8)

            
            content.append(Paragraph(
                f"区域划分: {grid_size}×{grid_size}（图像被均匀划分为{grid_size*grid_size}个区域）",
                styles['ReportNormal']
            ))
            content.append(Paragraph(f"统计区域总数: {len(patch_stats.get('mean', []))}", styles['ReportNormal']))
            content.append(Paragraph(
                f"各区域亮度均值的平均值: {patch_stats.get('mean_avg', 0):.2f}（图像整体亮度水平）",
                styles['ReportNormal']
            ))
            content.append(Paragraph(
                f"各区域纹理复杂度方差的平均值: {patch_stats.get('variance_avg', 0):.2f}（图像整体纹理复杂度）",
                styles['ReportNormal']
            ))
            content.append(Paragraph(
                f"各区域边缘密度的平均值: {patch_stats.get('edges_avg', 0):.4f}（图像整体边缘特征强度）",
                styles['ReportNormal']
            ))
            
            content.append(Spacer(1, 0.3*cm))
            
            # 添加异常区域与正常区域对比分析
            if 'patch_statistics' in report_data and report_data['patch_statistics']:
                patch_stats = report_data['patch_statistics']
                if 'anomaly_regions' in patch_stats and 'normal_regions' in patch_stats:
                    anomaly_regions = patch_stats['anomaly_regions']
                    normal_regions = patch_stats['normal_regions']
                    
                    # 总区域数据
                    total_regions = anomaly_regions.get('count', 0) + normal_regions.get('count', 0)
                    anomaly_percent = (anomaly_regions.get('count', 0) / total_regions * 100) if total_regions > 0 else 0
                    
                    content.append(Paragraph("3.1 原图纹理异常分析", styles['ReportHeading2']))
                    content.append(Paragraph("(基于热图选择异常区域，在原图上进行纹理特征分析)", styles['ReportItalic']))
                    content.append(Spacer(1, 0.3*cm))
                    
                    # 创建表格比较异常区域和正常区域
                    comparison_data = [
                        ["特征", "异常区域", "正常区域", "差异率"],
                        ["区域数量", f"{anomaly_regions.get('count', 0)} ({anomaly_percent:.1f}%)", 
                         f"{normal_regions.get('count', 0)} ({100-anomaly_percent:.1f}%)", "-"]
                    ]
                    
                    # 亮度均值
                    anomaly_mean = anomaly_regions.get('mean_avg', 0)
                    normal_mean = normal_regions.get('mean_avg', 0)
                    mean_diff = ((anomaly_mean - normal_mean) / normal_mean * 100) if normal_mean > 0 else 0
                    comparison_data.append(["亮度均值", f"{anomaly_mean:.2f}", f"{normal_mean:.2f}", f"{mean_diff:+.1f}%"])
                    
                    # 纹理复杂度（方差）
                    anomaly_var = anomaly_regions.get('variance_avg', 0)
                    normal_var = normal_regions.get('variance_avg', 0)
                    var_diff = ((anomaly_var - normal_var) / normal_var * 100) if normal_var > 0 else 0
                    comparison_data.append(["纹理复杂度方差", f"{anomaly_var:.2f}", f"{normal_var:.2f}", f"{var_diff:+.1f}%"])
                    
                    # 边缘密度
                    anomaly_edge = anomaly_regions.get('edges_avg', 0)
                    normal_edge = normal_regions.get('edges_avg', 0)
                    edge_diff = ((anomaly_edge - normal_edge) / normal_edge * 100) if normal_edge > 0 else 0
                    comparison_data.append(["边缘密度", f"{anomaly_edge:.4f}", f"{normal_edge:.4f}", f"{edge_diff:+.1f}%"])
                    
                    # 创建表格
                    comparison_table = Table(comparison_data, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
                    comparison_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('FONTNAME', (0, 0), (-1, -1), cn_font_name),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('PADDING', (0, 0), (-1, -1), 6),
                    ]))
                    
                    content.append(comparison_table)
                    content.append(Spacer(1, 0.5*cm))
                    
                    # 添加异常区域特征解读
                    content.append(Paragraph("3.2 异常区域特征解读:", styles['ReportHeading2']))
                    content.append(Spacer(1, 0.3*cm))
                    
                    # 亮度差异解读
                    if abs(mean_diff) > 15:
                        brightness_desc = f"异常区域亮度{'明显高于' if mean_diff > 0 else '明显低于'}正常区域（差异{abs(mean_diff):.1f}%），表明{'存在高亮异常' if mean_diff > 0 else '可能有暗区缺陷'}。"
                    elif abs(mean_diff) > 5:
                        brightness_desc = f"异常区域亮度{'略高于' if mean_diff > 0 else '略低于'}正常区域（差异{abs(mean_diff):.1f}%）。"
                    else:
                        brightness_desc = "异常区域与正常区域亮度相近，缺陷可能不表现为亮度变化。"
                    
                    # 纹理复杂度解读
                    if abs(var_diff) > 30:
                        texture_desc = f"异常区域纹理复杂度{'明显高于' if var_diff > 0 else '明显低于'}正常区域（差异{abs(var_diff):.1f}%），表明{'存在纹理断裂或杂乱' if var_diff > 0 else '可能有纹理缺失或平滑区域'}。"
                    elif abs(var_diff) > 10:
                        texture_desc = f"异常区域纹理复杂度{'略高于' if var_diff > 0 else '略低于'}正常区域（差异{abs(var_diff):.1f}%）。"
                    else:
                        texture_desc = "异常区域与正常区域纹理复杂度相近。"
                    
                    # 边缘密度解读
                    if abs(edge_diff) > 40:
                        edge_desc = f"异常区域边缘密度{'明显高于' if edge_diff > 0 else '明显低于'}正常区域（差异{abs(edge_diff):.1f}%），表明{'存在明显边缘或轮廓特征' if edge_diff > 0 else '可能有边缘缺失或模糊'}。"
                    elif abs(edge_diff) > 15:
                        edge_desc = f"异常区域边缘密度{'略高于' if edge_diff > 0 else '略低于'}正常区域（差异{abs(edge_diff):.1f}%）。"
                    else:
                        edge_desc = "异常区域与正常区域边缘密度相近。"
                    
                    content.append(Paragraph(brightness_desc, styles['ReportNormal']))
                    content.append(Paragraph(texture_desc, styles['ReportNormal']))
                    content.append(Paragraph(edge_desc, styles['ReportNormal']))
                    
                    # 综合解释
                    content.append(Paragraph("3.3 综合分析:", styles['ReportHeading2']))
                    content.append(Spacer(1, 0.3*cm))
                    
                    if abs(mean_diff) > 15 or abs(var_diff) > 30 or abs(edge_diff) > 40:
                        analysis = "异常区域与正常区域存在显著差异，很可能存在实际缺陷。"
                    elif abs(mean_diff) > 5 or abs(var_diff) > 10 or abs(edge_diff) > 15:
                        analysis = "异常区域与正常区域存在一定差异，可能存在轻微缺陷。"
                    else:
                        analysis = "异常区域与正常区域差异不明显，可能是热图误检或缺陷特征不明显。"
                    content.append(Paragraph(analysis, styles['ReportNormal']))
                    content.append(Spacer(1, 0.5*cm))
                    
                    # 添加区域特征直方图
                    if histogram_chart and os.path.exists(histogram_chart):
                        content.append(Paragraph("3.4 图像区域特征分布", styles['ReportHeading2']))
                        content.append(Spacer(1, 0.3*cm))
                        
                        try:
                            img = Image(histogram_chart, width=15*cm, height=15*cm)
                            content.append(img)
                            content.append(Paragraph("图2. 基于原始图像的区域特征直方图（显示不同区域的亮度、纹理复杂度和边缘密度分布）", styles['ImageCaption']))
                        except Exception as e:
                            content.append(Paragraph(f"加载区域特征直方图失败: {str(e)}", styles['ReportNormal']))
                        
                        content.append(Paragraph("直方图解释:", styles['ReportNormal']))
                        content.append(Paragraph("1. 亮度分布直方图：用于区分亮度异常导致的缺陷，如过曝、过暗或局部高反差区域。其中绿色表示实际正常区域的亮度分布，红色表示实际异常区域的亮度分布", styles['ReportNormal']))
                        content.append(Paragraph("2. 纹理复杂度分布直方图：用于区分纹理异常导致的缺陷，如纹理断裂、杂乱或缺失。其中绿色表示实际正常区域的纹理复杂度分布，红色表示实际异常区域的纹理复杂度分布", styles['ReportNormal']))
                        content.append(Paragraph("3. 边缘密度分布直方图：用于识别边缘异常，如裂纹、划痕或轮廓缺失等几何特征缺陷。其中绿色表示实际正常区域的边缘特征分布，红色表示实际异常区域的边缘特征分布", styles['ReportNormal']))
                        content.append(Paragraph("注：颜色划分是基于热图检测结果确定的，而非人工设定的阈值。横坐标表示特征值，纵坐标表示出现频率。", styles['ReportItalic']))
            
            content.append(Spacer(1, 0.5*cm))
        
        # 缺陷类型分析
        content.append(Paragraph("4. 缺陷类型分析", styles['ReportHeading1']))
        content.append(Spacer(1, 0.2*cm))
        
        texture_counts = report_data['texture_analysis']['texture_counts']
        if texture_counts:
            # 添加缺陷类型饼图
            if pie_chart and os.path.exists(pie_chart):
                try:
                    img = Image(pie_chart, width=12*cm, height=10*cm)
                    content.append(img)
                    content.append(Paragraph("图3. 缺陷类型分布饼图", styles['ImageCaption']))
                except Exception as e:
                    content.append(Paragraph(f"加载缺陷类型饼图失败: {str(e)}", styles['ReportNormal']))
            
            # 获取主要缺陷类型
            main_texture = max(texture_counts.items(), key=lambda x: x[1])[0]
            content.append(Paragraph(f"主要缺陷类型: {main_texture}", styles['ReportNormal']))
            content.append(Spacer(1, 0.2*cm))
            
            # 创建缺陷分布表格
            content.append(Paragraph("缺陷类型分布:", styles['ReportNormal']))
            texture_data = [["主要类型", "缺陷数量", "样本数量", "详细类型"]]
            
            # 获取样本主要缺陷类型统计
            sample_main_type_counts = report_data['texture_analysis'].get('sample_main_type_counts', {})
            
            for texture, count in texture_counts.items():
                # 获取详细类型描述
                type_desc = report_data['texture_analysis'].get('type_description', {}).get(texture, "")
                # 获取该类型的样本数量
                sample_count = sample_main_type_counts.get(texture, 0)
                texture_data.append([texture, str(count), f"{sample_count}个样本", type_desc])
                
            texture_table = Table(texture_data, colWidths=[3*cm, 2*cm, 2*cm, 7*cm])
            texture_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, -1), cn_font_name),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (3, 1), (3, -1), 'LEFT'),  # 详细类型列左对齐
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            
            content.append(texture_table)
            content.append(Spacer(1, 0.5*cm))
        
        # 结论部分
        content.append(Paragraph("5. 分析结论", styles['ReportHeading1']))
        content.append(Spacer(1, 0.2*cm))
        
        # 根据数据生成详细结论
        conclusions = []
        recommendations = []
        
        # 缺陷分布结论
        if clusters:
            # 计算主要聚类区域包含的缺陷比例
            total_defects = sum([c['count'] for c in clusters])
            main_cluster_ratio = clusters[0]['count'] / total_defects if total_defects > 0 else 0
            
            if len(clusters) == 1:
                conclusions.append(f"1. 缺陷高度集中，存在明显的单点问题区域（占比{main_cluster_ratio*100:.1f}%），表明产品在特定位置存在固定缺陷")
                recommendations.append("• 建议重点检查该区域的生产工艺参数和设备状态")
                recommendations.append("• 可能需要调整模具或工装夹具的相关部件")
            elif len(clusters) <= 3:
                conclusions.append(f"1. 缺陷集中在{len(clusters)}个区域，主要区域占比{main_cluster_ratio*100:.1f}%，表明可能存在多个工艺缺陷点")
                recommendations.append("• 建议分别检查这几个区域的生产工艺，寻找共性问题")
                recommendations.append("• 可能需要检查多个工序或多个加工单元")
            else:
                conclusions.append(f"1. 缺陷分散在{len(clusters)}个不同区域，分布较为均匀，表明可能存在系统性的工艺问题")
                recommendations.append("• 建议全面检查生产工艺流程，可能存在基础工艺参数问题")
                recommendations.append("• 检查原料品质、环境条件等全局因素")
        
        # 缺陷类型分析结论
        if texture_counts:
            # 获取严重程度排序的缺陷类型
            severity_order = {
                "严重损坏": 4,
                "中度缺陷": 3,
                "轻度异常": 2,
                "轻微污染": 1
            }
            
            # 按照严重程度排序
            sorted_textures = sorted(texture_counts.items(), key=lambda x: severity_order.get(x[0], 0), reverse=True)
            main_texture = sorted_textures[0][0]  # 最严重的缺陷类型
            main_texture_count = sorted_textures[0][1]
            texture_ratio = main_texture_count / sum(texture_counts.values())
            
            # 收集所有出现的缺陷类型
            all_defect_types = []
            for texture_type, _ in sorted_textures:
                if texture_type in report_data['texture_analysis'].get('type_description', {}):
                    type_desc = report_data['texture_analysis']['type_description'][texture_type]
                    if "包括" in type_desc:
                        detail_types_text = type_desc.replace("（包括：", "").replace("）", "")
                        detail_types_list = detail_types_text.split(", ")
                        for detail_type in detail_types_list:
                            if "个" in detail_type and int(detail_type.split("个")[0]) > 0:
                                all_defect_types.append(detail_type.split("个")[1])
            
            # 根据主要缺陷类型生成结论
            if main_texture == "严重损坏":
                defects_str = "、".join(all_defect_types[:3]) if all_defect_types else "裂缝、大缺口等"
                conclusions.append(f"2. 样本中存在严重损坏类型的缺陷（占比{texture_ratio*100:.1f}%），如{defects_str}")
                recommendations.append("• 建议立即停机排查，检查加工设备和模具状态")
                recommendations.append("• 对设备进行维护保养，消除可能的异常振动或过载")
                recommendations.append("• 检查原材料质量是否符合要求")
            elif main_texture == "中度缺陷":
                defects_str = "、".join(all_defect_types[:3]) if all_defect_types else "划痕、小缺口等"
                conclusions.append(f"2. 样本中主要为中度缺陷（占比{texture_ratio*100:.1f}%），包括{defects_str}")
                recommendations.append("• 需要对生产工艺进行针对性调整")
                recommendations.append("• 检查产品在传输过程中是否受到不当接触或碰撞")
                recommendations.append("• 优化工装夹具或传送设备以减少产品表面磨损")
            elif main_texture == "轻度异常":
                defects_str = "、".join(all_defect_types[:3]) if all_defect_types else "小面积异常、亮斑等"
                conclusions.append(f"2. 样本中主要为轻度异常（占比{texture_ratio*100:.1f}%），表现为{defects_str}")
                recommendations.append("• 建议对生产参数进行微调，如温度、压力或速度等")
                recommendations.append("• 检查产品表面清洁处理和涂层工艺")
                recommendations.append("• 调整光源或检测环境以排除误检可能性")
            elif main_texture == "轻微污染":
                defects_str = "、".join(all_defect_types[:3]) if all_defect_types else "小面积污染、微尘等"
                conclusions.append(f"2. 样本中主要为轻微污染（占比{texture_ratio*100:.1f}%），主要是{defects_str}")
                recommendations.append("• 建议检查生产环境的洁净度和除尘系统")
                recommendations.append("• 优化产品清洁工序和包装流程")
                recommendations.append("• 检查是否存在静电吸附问题导致表面污染")
            else:
                conclusions.append(f"2. 缺陷类型以{main_texture}为主（占比{texture_ratio*100:.1f}%）")
                recommendations.append("• 建议针对此类缺陷进行专项改进")
            
            # 如果存在多种缺陷类型，添加综合分析
            if len(sorted_textures) > 1 and sorted_textures[1][1] > total_defects * 0.2:
                second_texture = sorted_textures[1][0]
                second_ratio = sorted_textures[1][1] / sum(texture_counts.values())
                conclusions.append(f"   同时还存在较多的{second_texture}类型缺陷（占比{second_ratio*100:.1f}%），表明生产过程中可能存在多种问题")
                recommendations.append(f"• 同时关注{second_texture}类型缺陷的成因，可能需要多方面改进")
        
        # 区域特征结论
        if 'patch_statistics' in report_data and report_data['patch_statistics']:
            patch_stats = report_data['patch_statistics']
            edge_avg = patch_stats.get('edges_avg', 0)
            texture_variance = patch_stats.get('variance_avg', 0)
            brightness_mean = patch_stats.get('mean_avg', 0)
            
            feature_conclusion = "3. "
            
            # 基于边缘密度分析
            if edge_avg > 0.3:
                feature_conclusion += f"图像边缘密度较高（{edge_avg:.4f}），表明检测对象表面存在较多边缘特征，"
                if texture_variance > 100:
                    feature_conclusion += "结合较高的纹理复杂度，可能是划痕或裂纹类缺陷"
                    recommendations.append("• 建议检查加工工具是否有损伤或磨损")
                else:
                    feature_conclusion += "可能是细小的表面裂纹或刻痕"
                    recommendations.append("• 建议检查模具表面状态和脱模工艺")
            elif edge_avg > 0.1:
                feature_conclusion += f"图像边缘密度适中（{edge_avg:.4f}），表明检测对象表面存在一定的边缘特征，"
                if brightness_mean > 180:
                    feature_conclusion += "结合较高的亮度水平，可能是表面微小凹凸或轻微磨损"
                    recommendations.append("• 建议优化表面处理工艺，如抛光或打磨参数")
                else:
                    feature_conclusion += "可能是轻微的表面不规则或纹理变化"
                    recommendations.append("• 建议检查原料均匀性和加工参数一致性")
            else:
                feature_conclusion += f"图像边缘密度较低（{edge_avg:.4f}），表明检测对象表面较为平滑，"
                if brightness_mean > 190:
                    feature_conclusion += "但亮度较高，缺陷可能以亮斑或反光异常为主"
                    recommendations.append("• 建议检查表面涂层均匀性和光源条件")
                else:
                    feature_conclusion += "缺陷可能以颜色或亮度异常为主"
                    recommendations.append("• 建议检查材料成分和加工温度控制")
            
            conclusions.append(feature_conclusion)
        
        # 添加结论和建议
        content.append(Paragraph("5.1 缺陷分析结论", styles['ReportHeading2']))
        for conclusion in conclusions:
            content.append(Paragraph(conclusion, styles['ReportNormal']))
            content.append(Spacer(1, 0.2*cm))
        
        content.append(Paragraph("5.2 改进建议", styles['ReportHeading2']))
        for recommendation in recommendations:
            content.append(Paragraph(recommendation, styles['ReportNormal']))
            content.append(Spacer(1, 0.1*cm))
        
        content.append(Spacer(1, 0.5*cm))
        disclaimer = "注: 本报告中的分析结论和建议基于当前样本数据，实际生产问题可能更为复杂，请结合具体情况进行判断。"
        content.append(Paragraph(disclaimer, styles['ReportNote']))
        
        # 生成PDF
        doc.build(content)
        return pdf_filename
        
    except Exception as e:
        error_msg = f"生成PDF报告时出错: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return None

