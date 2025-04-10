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
    缺陷纹理分析器，用于分析检测结果热图中的缺陷位置和纹理特征
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
        self.texture_features = []  # 存储纹理特征
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
        直接加载指定路径中的所有热图图像
        
        Args:
            threshold: 不再使用，保留参数以兼容接口
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
            image_files = [f for f in os.listdir(self.result_path) 
                          if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')) and '_3.' in f]
            
            # 如果找不到热图，则获取所有图像文件
            if not image_files:
                print("未找到热图文件，尝试加载所有图像文件")
                image_files = [f for f in os.listdir(self.result_path) 
                              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]
            
            # 如果还是找不到图像，使用更宽松的匹配
            if not image_files:
                print("使用宽松匹配搜索图像文件")
                image_files = []
                for f in os.listdir(self.result_path):
                    try:
                        if os.path.isfile(join_path(self.result_path, f)):
                            # 尝试读取文件看是否为图像
                            img = cv2.imread(join_path(self.result_path, f), cv2.IMREAD_UNCHANGED)
                            if img is not None:
                                image_files.append(f)
                    except Exception as e:
                        print(f"检查文件 {f} 时出错: {str(e)}")
        
            self.image_count = len(image_files)
            print(f"找到 {self.image_count} 个图像文件")
            
            if self.image_count == 0:
                self.update_progress(30, "未找到图像文件")
                return 0
            
            if not config.DETECT_LIST:
                # 尝试加载detect_list.json获取得分信息
                detect_list_path = join_path(self.detect_path, 'detect_list.json')
                if os.path.exists(detect_list_path):
                    try:
                        config.DETECT_LIST = json.load(open(detect_list_path))
                        print(f"加载了 {len(config.DETECT_LIST)} 个检测结果记录")
                    except Exception as e:
                        print(f"读取detect_list.json出错: {str(e)}")
            
            # 找出得分最高的样本
            best_score = -1
            self.best_sample = None
            for item in config.DETECT_LIST:
                score = item.get('score')
                if isinstance(score, str):
                    try:
                        score = float(score)
                    except:
                        score = 0
                
                if score > best_score:
                    best_score = score
                    self.best_sample = item.get('origin_name')
            
            if self.best_sample:
                print(f"得分最高的样本是: {self.best_sample}, 得分: {best_score}")
                # 尝试找到样本原图路径
                potential_path = join_path(config.SAMPLE_PATH, self.detect_group, self.best_sample)
                if os.path.exists(potential_path):
                    self.best_sample_path = potential_path
                    print(f"找到最佳样本原图路径: {self.best_sample_path}")
            
            # 处理每个图像
            for i, image_file in enumerate(image_files):
                image_path = join_path(self.result_path, image_file)
                print(f"处理图像: {image_path}")
                
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
                
                # 假设所有热图都是缺陷图像
                self.defect_images.append({
                    'name': image_file,
                    'heatmap_path': image_path
                })
                
                # 更新进度
                if i % 5 == 0:  # 每5张图像更新一次进度
                    progress = int((i + 1) / len(image_files) * 30)  # 总进度的30%用于加载图像
                    self.update_progress(progress, f"加载图像 {i+1}/{len(image_files)}...")
            
            self.update_progress(30, f"已加载图像: {len(self.defect_images)}张")
            return len(self.defect_images)
        
        except Exception as e:
            error_msg = f"加载图像文件时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.update_progress(30, f"加载图像出错: {str(e)}")
            raise RuntimeError(error_msg)
    
    def extract_defect_features(self, grid_size=8):
        """
        从热图中提取缺陷特征和位置，同时进行图像网格统计分析
        
        Args:
            grid_size: 网格划分数量，将图像均匀划分为grid_size×grid_size个区域，默认为8×8网格
        """
        try:
            self.update_progress(30, "开始提取缺陷特征...")
            self.heatmap_data = []
            self.defect_positions = []
            self.texture_features = []
            
            # 初始化网格统计数组
            grid_means = []
            grid_variances = []
            grid_edges = []  # 存储边缘检测结果
            
            for img_idx, img_info in enumerate(self.defect_images):
                # 读取热图
                heatmap_path = img_info['heatmap_path']
                print(f"读取图像: {heatmap_path}")
                
                heatmap = cv2.imread(heatmap_path)
                if heatmap is None:
                    print(f"无法读取图像: {heatmap_path}")
                    continue
                    
                # 输出图像形状以进行调试
                print(f"图像形状: {heatmap.shape}")
                
                # 转换为灰度图
                heatmap_gray = cv2.cvtColor(heatmap, cv2.COLOR_BGR2GRAY)
                
                # 计算Sobel边缘
                sobel_x = cv2.Sobel(heatmap_gray, cv2.CV_64F, 1, 0, ksize=3)
                sobel_y = cv2.Sobel(heatmap_gray, cv2.CV_64F, 0, 1, ksize=3)
                # 计算梯度幅度
                sobel_mag = cv2.magnitude(sobel_x, sobel_y)
                # 归一化到0-255范围
                sobel_mag = cv2.normalize(sobel_mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
                # 应用阈值获取边缘掩码
                _, edge_mask = cv2.threshold(sobel_mag, 50, 1, cv2.THRESH_BINARY)
                
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
                            'mean': mean_val,
                            'std': std_val,
                            'max': max_val,
                            'gradient': grad_mean,
                            'area': area
                        })
                
                # 输出有效轮廓数量
                print(f"有效轮廓数量: {contour_count}")
                
                # 存储热图数据
                self.heatmap_data.append({
                    'image': img_info['name'],
                    'heatmap': heatmap_norm
                })
                
                # 分析图像网格
                try:
                    # 获取图像尺寸
                    height, width = heatmap_gray.shape
                    
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
                    
                    # 分析每个网格区域
                    for row in range(grid_size):
                        for col in range(grid_size):
                            # 确保不越界
                            if row*cell_height >= height or col*cell_width >= width:
                                continue
                                
                            # 提取当前网格区域
                            y_start = row * cell_height
                            y_end = min((row+1) * cell_height, height)
                            x_start = col * cell_width
                            x_end = min((col+1) * cell_width, width)
                            
                            cell = heatmap_gray[y_start:y_end, x_start:x_end]
                            edge_cell = edge_mask[y_start:y_end, x_start:x_end]
                            
                            # 计算均值和方差
                            cell_mean = np.mean(cell)
                            cell_variance = np.var(cell)
                            
                            # 计算边缘密度（边缘像素占比）
                            edge_density = np.sum(edge_cell) / edge_cell.size
                            
                            # 存储结果
                            grid_means.append(cell_mean)
                            grid_variances.append(cell_variance)
                            grid_edges.append(edge_density)
                except Exception as e:
                    print(f"处理图像 {img_info['name']} 的网格区域时出错: {str(e)}")
                
                # 更新进度
                progress = 30 + int((img_idx + 1) / len(self.defect_images) * 30)  # 30%-60%的进度用于特征提取
                self.update_progress(progress, f"提取缺陷特征 {img_idx+1}/{len(self.defect_images)}...")
            
            # 生成网格统计结果
            self.patch_statistics = {
                'patch_size': grid_size,  # 保持字段名兼容，实际表示网格划分数量
                'mean': grid_means,
                'variance': grid_variances,
                'edges': grid_edges,  # 添加边缘密度数据
                'mean_bins': 20,  # 直方图bin数
                'variance_bins': 20,
                'edges_bins': 20,
                'mean_histogram': np.histogram(grid_means, bins=20)[0].tolist() if grid_means else [],
                'variance_histogram': np.histogram(grid_variances, bins=20)[0].tolist() if grid_variances else [],
                'edges_histogram': np.histogram(grid_edges, bins=20)[0].tolist() if grid_edges else [],
                'mean_bin_edges': np.histogram(grid_means, bins=20)[1].tolist() if grid_means else [],
                'variance_bin_edges': np.histogram(grid_variances, bins=20)[1].tolist() if grid_variances else [],
                'edges_bin_edges': np.histogram(grid_edges, bins=20)[1].tolist() if grid_edges else [],
                'mean_avg': np.mean(grid_means) if grid_means else 0,
                'variance_avg': np.mean(grid_variances) if grid_variances else 0,
                'edges_avg': np.mean(grid_edges) if grid_edges else 0
            }
            
            self.update_progress(60, f"已提取缺陷特征: {len(self.defect_positions)}个，分析了{len(grid_means)}个网格区域")
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
    
    def analyze_texture_patterns(self):
        """
        分析纹理模式，统计不同类型的纹理特征
        """
        try:
            self.update_progress(70, "开始分析纹理模式...")
            
            if not self.texture_features:
                print("没有纹理特征数据可供分析")
                return {
                    'texture_counts': {},
                    'dominant_position_textures': {},
                    'texture_details': []
                }
                
            print(f"分析纹理模式，特征数量: {len(self.texture_features)}")
            # 使用梯度大小对纹理进行分类
            gradient_thresholds = [10, 30, 50]
            texture_types = ['平滑', '轻微纹理', '中等纹理', '强烈纹理']
            
            # 对纹理进行分类
            texture_categories = []
            for feature in self.texture_features:
                gradient = feature['gradient']
                
                # 根据梯度确定类别
                category_idx = sum(gradient > threshold for threshold in gradient_thresholds)
                category = texture_types[category_idx]
                
                texture_categories.append({
                    'image': feature['image'],
                    'position': feature['position'],
                    'texture_type': category,
                    'texture_value': gradient
                })
            
            # 统计各类纹理的数量
            texture_counts = Counter([item['texture_type'] for item in texture_categories])
            print(f"纹理类型分布: {dict(texture_counts)}")
            
            # 按照位置统计纹理类型
            position_textures = defaultdict(list)
            for item in texture_categories:
                # 将位置离散化为网格
                grid_x = int(item['position'][0] * 5)  # 5x5网格
                grid_y = int(item['position'][1] * 5)
                position_key = f"{grid_x}_{grid_y}"
                
                position_textures[position_key].append(item['texture_type'])
            
            # 每个位置的主要纹理类型
            dominant_textures = {}
            for pos, textures in position_textures.items():
                counts = Counter(textures)
                dominant_textures[pos] = counts.most_common(1)[0][0]
            
            texture_analysis = {
                'texture_counts': dict(texture_counts),
                'dominant_position_textures': dominant_textures,
                'texture_details': texture_categories
            }
            
            self.update_progress(80, "纹理分析完成")
            return texture_analysis
            
        except Exception as e:
            error_msg = f"纹理分析时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.update_progress(80, f"纹理分析出错: {str(e)}")
            raise RuntimeError(error_msg)
    
    def generate_report(self):
        """
        生成缺陷分析报告
        """
        try:
            self.update_progress(80, "开始生成报告...")
            
            # 检查是否有足够的数据
            if not self.defect_positions or not self.texture_features:
                error_msg = "没有足够的缺陷数据用于分析"
                print(error_msg)
                raise ValueError(error_msg)
                
            # 执行聚类
            if self.cluster_results is None:
                self.cluster_defect_positions()
                
            # 分析纹理模式
            texture_analysis = self.analyze_texture_patterns()
            
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
                
            # 生成可视化报告
            chart_path = self._generate_visualization(report, report['timestamp'])
            
            self.update_progress(100, "报告生成完成")
            
            return {
                'report_file': report_file,
                'chart_file': chart_path,
                'report_data': report
            }
            
        except Exception as e:
            error_msg = f"生成报告时出错: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            self.update_progress(100, f"生成报告出错: {str(e)}")
            raise RuntimeError(error_msg)

    def _generate_visualization(self, report, timestamp):
        """
        生成可视化报告
        
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
                
            # 平滑热力图
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
                ax.plot(x, y, 'go', markersize=10, alpha=0.7)
                ax.annotate(f"C{i+1}: {count}个", 
                            xy=(x, y), 
                            xytext=(x+10, y+10),
                            color='white',
                            fontweight='bold',
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
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, f"Error generating report: {str(e)}", 
                   ha='center', va='center', fontsize=12)
            ax.axis('off')
            fig_path = join_path(self.report_path, f"defect_analysis_error_{timestamp}.png")
            plt.savefig(fig_path, dpi=100)
            plt.close()
            return fig_path


def analyze_defect_textures(detect_path, detect_group, threshold=0.5, eps=0.1, min_samples=3, grid_size=8, progress_callback=None):
    """
    分析缺陷纹理并生成报告
    
    Args:
        detect_path: 检测样本根目录路径
        detect_group: 检测样本组名称
        threshold: 缺陷阈值(已不再使用，保留参数兼容性)
        eps: DBSCAN聚类的邻域半径参数
        min_samples: DBSCAN聚类的最小样本数参数
        grid_size: 网格划分数量，将图像均匀划分为grid_size×grid_size个区域
        progress_callback: 进度回调函数，接收进度值(0-100)和进度消息
    
    Returns:
        报告信息字典，包含report_file, chart_file和report_data
    """
    # 设置Matplotlib使用非交互式后端，避免线程问题
    import matplotlib
    matplotlib.use('Agg')  # 使用非交互式后端
    
    try:
        print(f"开始分析: 路径={detect_path}, 组={detect_group}, 网格划分={grid_size}×{grid_size}")
        
        # 创建分析器
        analyzer = DefectTextureAnalyzer(detect_path, detect_group)
        
        # 设置进度回调
        if progress_callback:
            analyzer.set_progress_callback(progress_callback)
        
        # 加载缺陷图像
        defect_count = analyzer.load_defect_images(threshold)
        if defect_count == 0:
            error_msg = "未找到图像，无法进行分析"
            print(error_msg)
            if progress_callback:
                progress_callback(100, error_msg)
            return None
            
        # 提取缺陷特征
        feature_count = analyzer.extract_defect_features(grid_size)
        if feature_count == 0:
            error_msg = "未能提取到有效的缺陷特征"
            print(error_msg)
            if progress_callback:
                progress_callback(100, error_msg)
            return None
            
        # 聚类分析
        analyzer.cluster_defect_positions(eps, min_samples)
        
        # 生成报告
        report_info = analyzer.generate_report()
        
        # 生成统计图表
        if report_info:
            chart_paths = generate_statistical_charts(report_info['report_data'], analyzer.report_path)
            if chart_paths:
                report_info.update(chart_paths)
                
            # 更新进度到100%
            if progress_callback:
                progress_callback(100, "分析完成")
        
        return report_info
        
    except Exception as e:
        error_msg = f"分析缺陷纹理时出错: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        if progress_callback:
            progress_callback(100, f"分析缺陷纹理时出错: {str(e)}")
        raise


def generate_statistical_charts(report_data, report_path):
    """
    生成统计图表并保存到指定路径
    
    Args:
        report_data: 报告数据字典
        report_path: 报告保存路径
    
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
        timestamp = report_data['timestamp']
        chart_paths = {}
        
        # 1. 生成网格区域特征统计直方图
        if 'patch_statistics' in report_data and report_data['patch_statistics']:
            try:
                # 获取统计数据
                patch_stats = report_data['patch_statistics']
                grid_size = patch_stats.get('patch_size', 8)
                
                # 创建一个临时的图像文件存储直方图
                plt.figure(figsize=(8, 10))
                
                # 绘制均值分布直方图
                plt.subplot(3, 1, 1)
                plt.title('区域亮度分布')
                mean_bins = patch_stats.get('mean_bin_edges', [])
                if len(mean_bins) >= 2:
                    bin_centers = [(mean_bins[i] + mean_bins[i+1])/2 for i in range(len(mean_bins)-1)]
                    plt.bar(bin_centers, patch_stats.get('mean_histogram', []), width=(mean_bins[1]-mean_bins[0])*0.8)
                else:
                    plt.text(0.5, 0.5, '无均值数据', ha='center', va='center')
                
                plt.grid(True, alpha=0.3)
                plt.xlabel('均值（亮度）')
                plt.ylabel('区域数量')
                
                # 绘制方差分布直方图
                plt.subplot(3, 1, 2)
                plt.title('区域纹理复杂度分布')
                var_bins = patch_stats.get('variance_bin_edges', [])
                if len(var_bins) >= 2:
                    bin_centers = [(var_bins[i] + var_bins[i+1])/2 for i in range(len(var_bins)-1)]
                    plt.bar(bin_centers, patch_stats.get('variance_histogram', []), width=(var_bins[1]-var_bins[0])*0.8)
                else:
                    plt.text(0.5, 0.5, '无方差数据', ha='center', va='center')
                
                plt.grid(True, alpha=0.3)
                plt.xlabel('方差（纹理复杂度）')
                plt.ylabel('区域数量')
                
                # 绘制边缘密度直方图
                plt.subplot(3, 1, 3)
                plt.title('区域边缘密度分布（Sobel算子）')
                edge_bins = patch_stats.get('edges_bin_edges', [])
                if len(edge_bins) >= 2:
                    bin_centers = [(edge_bins[i] + edge_bins[i+1])/2 for i in range(len(edge_bins)-1)]
                    plt.bar(bin_centers, patch_stats.get('edges_histogram', []), width=(edge_bins[1]-edge_bins[0])*0.8, color='orange')
                else:
                    plt.text(0.5, 0.5, '无边缘密度数据', ha='center', va='center')
                
                plt.grid(True, alpha=0.3)
                plt.xlabel('边缘密度（边缘像素占比）')
                plt.ylabel('区域数量')
                
                plt.tight_layout()
                
                # 保存直方图文件
                os.makedirs(report_path, exist_ok=True)
                histogram_path = os.path.join(report_path, f"grid_histogram_{timestamp}.png")
                plt.savefig(histogram_path)
                plt.close()
                
                chart_paths['histogram_chart'] = histogram_path
                print(f"区域特征直方图已保存: {histogram_path}")
                
            except Exception as e:
                print(f"生成区域统计图表时出错: {str(e)}")
        
        # 2. 生成纹理类型分布饼图
        texture_counts = report_data['texture_analysis']['texture_counts']
        if texture_counts:
            try:
                # 创建纹理类型分布的饼图
                plt.figure(figsize=(7, 5))
                labels = list(texture_counts.keys())
                sizes = list(texture_counts.values())
                colors = ['#1976D2', '#4CAF50', '#FF9800', '#9C27B0', '#F44336', '#00BCD4', '#FFEB3B'][:len(labels)]
                
                plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', 
                        shadow=False, startangle=90, textprops={'fontsize': 10})
                plt.axis('equal')
                plt.title('纹理类型分布', fontsize=12)
                
                # 保存饼图文件
                os.makedirs(report_path, exist_ok=True)
                pie_chart_path = os.path.join(report_path, f"texture_pie_{timestamp}.png")
                plt.savefig(pie_chart_path, dpi=120, bbox_inches='tight')
                plt.close()
                
                chart_paths['pie_chart'] = pie_chart_path
                print(f"纹理类型饼图已保存: {pie_chart_path}")
                
            except Exception as e:
                print(f"生成纹理类型饼图时出错: {str(e)}")
        
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
        pie_chart: 纹理分布饼图路径
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
            spaceAfter=8
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
                f"区域均值的平均值: {patch_stats.get('mean_avg', 0):.2f}（图像整体亮度水平）",
                styles['ReportNormal']
            ))
            content.append(Paragraph(
                f"区域方差的平均值: {patch_stats.get('variance_avg', 0):.2f}（图像整体纹理复杂度）",
                styles['ReportNormal']
            ))
            content.append(Paragraph(
                f"区域边缘密度平均值: {patch_stats.get('edges_avg', 0):.4f}（图像整体边缘特征强度）",
                styles['ReportNormal']
            ))
            
            content.append(Spacer(1, 0.3*cm))
            
            # 添加区域特征直方图
            if histogram_chart and os.path.exists(histogram_chart):
                try:
                    img = Image(histogram_chart, width=15*cm, height=15*cm)
                    content.append(img)
                    content.append(Paragraph("图2. 区域特征直方图（显示图像不同区域的亮度、纹理复杂度和边缘密度分布）", styles['ImageCaption']))
                    
                    content.append(Paragraph("直方图解释:", styles['ReportNormal']))
                    content.append(Paragraph("1. 均值分布表示图像不同区域的亮度分布情况，可识别出暗区和亮区的比例", styles['ReportNormal']))
                    content.append(Paragraph("2. 方差分布表示图像不同区域的纹理复杂度，高方差区域通常包含复杂纹理", styles['ReportNormal']))
                    content.append(Paragraph("3. 边缘密度分布表示图像不同区域的边缘特征占比，高值区域通常包含明显的缺陷边界", styles['ReportNormal']))
                    
                except Exception as e:
                    content.append(Paragraph(f"加载区域特征直方图失败: {str(e)}", styles['ReportNormal']))
            
            content.append(Spacer(1, 0.5*cm))
        
        # 纹理分析
        content.append(Paragraph("4. 纹理分析", styles['ReportHeading1']))
        content.append(Spacer(1, 0.2*cm))
        
        texture_counts = report_data['texture_analysis']['texture_counts']
        if texture_counts:
            # 添加纹理类型饼图
            if pie_chart and os.path.exists(pie_chart):
                try:
                    img = Image(pie_chart, width=12*cm, height=10*cm)
                    content.append(img)
                    content.append(Paragraph("图3. 纹理类型分布饼图", styles['ImageCaption']))
                except Exception as e:
                    content.append(Paragraph(f"加载纹理类型饼图失败: {str(e)}", styles['ReportNormal']))
            
            # 获取主要纹理类型
            main_texture = max(texture_counts.items(), key=lambda x: x[1])[0]
            content.append(Paragraph(f"主要纹理类型: {main_texture}", styles['ReportNormal']))
            content.append(Spacer(1, 0.2*cm))
            
            # 创建纹理分布表格
            content.append(Paragraph("纹理类型分布:", styles['ReportNormal']))
            texture_data = [["纹理类型", "数量"]]
            for texture, count in texture_counts.items():
                texture_data.append([texture, str(count)])
                
            texture_table = Table(texture_data, colWidths=[8*cm, 6*cm])
            texture_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, -1), cn_font_name),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            
            content.append(texture_table)
            content.append(Spacer(1, 0.5*cm))
        
        # 结论部分
        content.append(Paragraph("5. 分析结论", styles['ReportHeading1']))
        content.append(Spacer(1, 0.2*cm))
        
        # 根据数据生成简单的结论
        conclusions = []
        
        # 缺陷分布结论
        if clusters:
            if len(clusters) == 1:
                conclusions.append("1. 缺陷高度集中，存在明显的单点问题区域，建议重点检查该区域的生产工艺")
            elif len(clusters) <= 3:
                conclusions.append(f"1. 缺陷集中在{len(clusters)}个区域，表明可能存在多个工艺缺陷点")
            else:
                conclusions.append(f"1. 缺陷分散在{len(clusters)}个不同区域，表明可能存在系统性的工艺问题")
        
        # 纹理分析结论
        if texture_counts:
            main_texture = max(texture_counts.items(), key=lambda x: x[1])[0]
            texture_ratio = max(texture_counts.values()) / sum(texture_counts.values())
            
            if texture_ratio > 0.7:
                conclusions.append(f"2. 缺陷纹理以{main_texture}为主（占比{texture_ratio*100:.1f}%），表明存在特定类型的缺陷模式")
            else:
                conclusions.append(f"2. 缺陷纹理类型多样，但{main_texture}相对较多，建议进一步分析各类纹理的成因")
        
        # 区域特征结论
        if 'patch_statistics' in report_data and report_data['patch_statistics']:
            patch_stats = report_data['patch_statistics']
            edge_avg = patch_stats.get('edges_avg', 0)
            
            if edge_avg > 0.3:
                conclusions.append("3. 图像边缘密度较高，表明检测对象表面存在较多边缘特征，可能是划痕或裂纹类缺陷")
            elif edge_avg > 0.1:
                conclusions.append("3. 图像边缘密度适中，表明检测对象表面存在一定的边缘特征，可能是轻微的表面不规则")
            else:
                conclusions.append("3. 图像边缘密度较低，表明检测对象表面较为平滑，缺陷可能以颜色或亮度异常为主")
        
        # 添加结论
        for conclusion in conclusions:
            content.append(Paragraph(conclusion, styles['ReportNormal']))
            content.append(Spacer(1, 0.2*cm))
        
        # 生成PDF
        doc.build(content)
        return pdf_filename
        
    except Exception as e:
        error_msg = f"生成PDF报告时出错: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return None


if __name__ == "__main__":
    
    # 示例路径和参数
    detect_path = "B:/Development/GraduationDesign/app/test/detect_result"
    detect_group = "test_group"
    threshold = 0.5
    
    # 定义简单的进度回调函数
    def print_progress(value, message):
        print(f"进度: {value}% - {message}")
    
    # 运行分析
    try:
        report_info = analyze_defect_textures(
            detect_path, 
            detect_group, 
            threshold, 
            progress_callback=print_progress
        )
        
        if report_info:
            print(f"报告文件: {report_info['report_file']}")
            print(f"图表文件: {report_info['chart_file']}")
    except Exception as e:
        print(f"错误: {str(e)}")
