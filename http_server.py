import os
import time
import requests
import config
from typing import Optional
from PySide6.QtWidgets import QMessageBox
from utils import ProgressDialog, is_image, join_path, show_message_box


class HttpServer:        
    # -------------------- 模型操作 --------------------
    def add_model(self, model):
        """
        添加模型
        
        Args:
            model: {
                "name": 模型名称,
                "input_h": 输入高度,
                "input_w": 输入宽度,
                "end_acc": 结束精度,
                "layers": 层数列表_形如[layer1, ...],
                "patchsize": 补丁大小,
                "embed_dimension": 嵌入维度
            }
            
        Returns:
            新建模型的ID
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/add_model"
        try:
            response = requests.post(url, json=model)
            if response.status_code == 200:
                print(f"添加模型: {model['name']} -> {url}")
                return response.json()
            else:
                raise Exception(f"添加模型失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"添加模型失败: {str(e)}")
            raise
    
    def delete_model(self, model_id):
        """
        删除模型
        
        Args:
            model_id: 模型ID
            
        Returns:
            删除结果
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/delete_model/{model_id}"
        try:
            response = requests.delete(url)
            if response.status_code == 200:
                print(f"删除模型: {model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"删除模型失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"删除模型失败: {str(e)}")
            raise
    
    def list_model(self):
        """
        获取模型列表
        
        Returns:
            模型列表：[{
                'id': 模型ID,
                'input_h': 输入高度,
                'input_w': 输入宽度,
                'end_acc': 结束精度,
                'embed_dimension': 嵌入维度,
                'patchsize': 补丁大小,
                'name': 模型名称,
                'layers': 层数列表,
                'status': 状态，0是新建的 1是已经训练中 2是训练结束 3是推理中，推理结束回到原状态
            }]
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/list_model"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print(f"获取模型列表: {url}")
                return response.json()
            else:
                raise Exception(f"获取模型列表失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取模型列表失败: {str(e)}")
            raise
    
    def train_info(self, model_id):
        """
        获取模型训练完成后的图像列表
        
        Args:
            model_id: 模型ID
            
        Returns:
            已训练的图像列表 ['image1.jpg', 'image2.jpg', ...]
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/train_info/{model_id}"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                print(f"获取已训练的图像列表: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"获取已训练的图像列表失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取已训练的图像列表失败: {str(e)}")
            raise
    
    def infer_info(self, model_id):
        """
        获取模型推理完成后的图像列表（相当于infer_process的最终状态）
        
        Args:
            model_id: 模型ID
            
        Returns: 
            已推理的图像列表：[{
                'img_result_filename': 推理结果文件名,
                'id': 所属的样本组ID,
                'bm_score': 边界框得分,
                'score': 得分,
                'model_id': 模型ID,
                'img_filename': 图像文件名
            }]
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/infer_info/{model_id}"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                print(f"获取已推理的图像列表: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"获取已推理的图像列表失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取已推理的图像列表失败: {str(e)}")
            raise
    
    def train_process(self, model_id):
        """
        获取模型训练实时信息
        
        Args:
            model_id: 模型ID
            
        Returns:
            训练信息 {
                "p_true": 真实样本概率,
                "p_fake": 生成样本概率,
                "loss": 损失,
                "epoch": 当前训练轮数,
                "distance_loss": 距离损失,
                "begin_time": 开始时间,
                "end_time": 结束时间
            }
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/train_process/{model_id}"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                print(f"获取模型训练信息: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"获取模型训练信息失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取模型训练信息失败: {str(e)}")
            raise
    
    def infer_process(self, model_id):
        """
        获取模型推理实时信息
        
        Args:
            model_id: 模型ID
            
        Returns:
            推理信息：{
                'inferPercentage': 推理进度,
                'have_infer_img_list': [{
                    'name': 图像文件名,
                    'score': 得分
                }]
            }
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/infer_process/{model_id}"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                print(f"获取模型推理信息: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"获取模型推理信息失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取模型推理信息失败: {str(e)}")
            raise
    
    def train_model(self, model_id, group_id):
        """
        训练模型
        
        Args:
            model_id: 模型ID
            group_id: 样本组ID
            
        Returns:
            训练任务提交结果
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/train_model/{model_id}"
        try:
            params = {'group_id': group_id}
            response = requests.post(url, params=params)
            if response.status_code == 200:
                print(f"开始训练模型: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"开始训练模型失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"开始训练模型失败: {str(e)}")
            raise

    def finish_model(self, model_id):
        """
        结束模型训练
        
        Args:
            model_id: 模型ID
            
        Returns:
            结束训练结果
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/finish_model/{model_id}"
        try:
            response = requests.post(url)
            if response.status_code == 200:
                print(f"结束模型训练: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"结束模型训练失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"结束模型训练失败: {str(e)}")
            raise

    def infer_model(self, model_id, group_id):
        """
        使用模型进行推理
        
        Args:
            model_id: 模型ID
            group_id: 样本组ID
            
        Returns:
            推理任务提交结果
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/infer_model/{model_id}"
        try:
            params = {'group_id': group_id}
            response = requests.post(url, params=params)
            if response.status_code == 200:
                print(f"开始模型推理: 模型ID={model_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"开始模型推理失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"开始模型推理失败: {str(e)}")
            raise

    # -------------------- 样本组操作 --------------------
        
    def upload_sample(self, file_path, group_id: Optional[int]):
        """
        通过HTTP接口上传单个文件
        
        Args:
            file_path: 文件路径
            group_id: 组ID，可选
        
        Returns:
            上传文件的文件名
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/upload_sample"
        try:
            with open(file_path, 'rb') as f:
                filename = os.path.basename(file_path)
                files = {'file': (filename, f, 'image/jpeg')}
                # 添加组ID参数作为URL参数，而不是表单数据
                params = {'group_id': group_id}
                response = requests.post(url, files=files, params=params)
                if response.status_code == 200:
                    print(f"上传文件: {file_path} -> {url}")
                    return response.json()["filename"]
                else:
                    raise Exception(f"上传文件失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"上传文件失败: {str(e)}")
            raise

    def get_sample_list(self, group_id):
        """
        获取指定组的样本名列表
        
        Args:
            group_id: 组ID
            
        Returns:
            样本名称列表
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/get_sample_list/{group_id}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print(f"获取样本列表: {url}")
                return response.json()
            else:
                raise Exception(f"获取样本列表失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取样本列表失败: {str(e)}")
            raise

    def download_sample(self, filename):
        """
        下载样本文件
        
        Args:
            filename: 文件名
            
        Returns:
            文件内容的二进制数据
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/download_sample"
        try:
            response = requests.get(url, json={"filename": filename})
            if response.status_code == 200:
                print(f"下载样本: {filename} -> {url}")
                return response.content  # 返回二进制内容而不是JSON
            else:
                raise Exception(f"下载样本失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"下载样本失败: {str(e)}")
            raise
            
    def save_downloaded_sample(self, filename, save_path):
        """
        下载样本并保存到指定路径
        
        Args:
            filename: 文件名
            save_path: 保存路径
            
        Returns:
            保存文件的完整路径
        """
        content = self.download_sample(filename)
        full_path = join_path(save_path, filename)
        # 确保目录存在，写入
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'wb') as f:
            f.write(content)
        return full_path

    def add_group(self, group_name):
        """
        添加组
        
        Args:
            group_name: 组名
            
        Returns:
            新建组的ID
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/add_group"
        try:
            response = requests.post(url, json={"group_name": group_name})
            if response.status_code == 200:
                print(f"添加组: {group_name} -> {url}")
                return response.json()
            else:
                raise Exception(f"添加组失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"添加组失败: {str(e)}")
            raise

    def delete_group(self, group_id):
        """
        删除组
        
        Args:
            group_id: 组ID
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/delete_group/{group_id}"
        try:
            response = requests.delete(url)
            if response.status_code == 200:
                print(f"删除组: {group_id} -> {url}")
                return response.json()
            else:
                raise Exception(f"删除组失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"删除组失败: {str(e)}")
            raise
    
    def get_group_list(self):
        """
        获取所有组的列表
        
        Returns:
            组列表：[{
                "id": 组ID,
                "group_name": 组名
            }]
        """
        url = f"http://{config.HOSTNAME}:{config.PORT}/get_group_list"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                print(f"获取组列表: {url}")
                return response.json()
            else:
                raise Exception(f"获取组列表失败: HTTP错误: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"获取组列表失败: {str(e)}")
            raise

    def get_group_id(self, group_name):
        """
        根据组名获取组ID
        """
        group_list = self.get_group_list()
        for group in group_list:
            if group.get("group_name") == group_name:
                print(f"组名匹配成功: {group_name} -> {group.get('id')}")
                return group.get("id")
        print(f"http_server无该样本组: {group_list}")
        return None
            

        
def test_sample_api():
    """
    简单测试脚本，测试HTTP服务器API
    测试流程: add_group -> get_group_list -> upload_sample -> get_sample_list -> 
            download_sample -> get_sample_list -> delete_group -> get_group_list
    """

    # 初始化 HttpServer
    server = HttpServer()

    # 0. 准备测试图片
    test_dir = "B:/Development/GraduationDesign/app/test"

    image_dir = join_path(test_dir, "img2")
    test_images = os.listdir(image_dir)

    print("======= 开始测试 HttpServer API =======")

    # 1. 添加组
    print("\n1. 测试添加组")
    group_name = f"测试组-{int(time.time())}"
    group_id = server.add_group(group_name)
    print(f"创建组成功: 名称={group_name}, ID={group_id}")

    # 2. 获取组列表
    print("\n2. 测试获取组列表")
    groups = server.get_group_list()
    print(f"组列表: {groups}")

    # 3. 上传样本
    print(f"\n3. 测试上传样本到组 {group_id}")
    for image in test_images:
        try:
            uploaded_filename = server.upload_sample(join_path(image_dir, image), group_id)
            print(f"上传成功，服务器文件名: {uploaded_filename}")
        except Exception as e:
            print(f"上传失败: {str(e)}")

    # 4. 获取样本列表
    print(f"\n4. 测试获取组 {group_id} 的样本列表")
    samples = server.get_sample_list(group_id)
    print(f"样本列表: {samples}")

    # 5. 下载样本
    print(f"\n5. 测试下载样本 {uploaded_filename}")
    download_dir = os.path.join(test_dir, "downloads")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    for sample in samples:
        downloaded_path = server.save_downloaded_sample(sample, download_dir)
        print(f"下载成功，保存路径: {downloaded_path}")

    # 6. 再次获取样本列表
    print(f"\n6. 再次测试获取组 {group_id} 的样本列表")
    samples = server.get_sample_list(group_id)
    print(f"样本列表: {samples}")

    # 7. 删除组
    print(f"\n7. 测试删除组 {group_id}")
    result = server.delete_group(group_id)
    print(f"删除组结果: {result}")

    # 8. 再次获取组列表
    print("\n8. 再次测试获取组列表")
    groups = server.get_group_list()
    print(f"组列表: {groups}")

    print("\n======= 测试完成 =======") 

def test_model_api():
    """
    测试模型操作相关的API:
    add_model -> list_model -> train_model -> train_info -> train_process -> infer_model -> infer_info -> infer_process -> delete_model -> list_model
    """

    # 初始化 HttpServer
    server = HttpServer()

    # 0. 准备样本
    test_dir = "B:/Development/GraduationDesign/app/test"
    image_dir = join_path(test_dir, "img")
    test_images = os.listdir(image_dir)[:2]
    # 添加组
    group_name = f"测试组-{int(time.time())}"
    group_id = server.add_group(group_name)
    print(f"创建组成功: 名称={group_name}, ID={group_id}")
    # 上传样本
    print(f"\n2. 上传样本到组 {group_id}")
    for image in test_images:
        try:
            server.upload_sample(join_path(image_dir, image), group_id)
        except Exception as e:
            print(f"上传失败: {str(e)}")

    print("======= 开始测试模型操作API =======")

    # 1. 添加模型
    print("\n1. 测试添加模型")
    model_name = f"测试模型-{int(time.time())}"
    layers = "['layer1', 'layer2', 'layer3']"  # 使用前3层特征
    patchsize = 32  # 中等补丁大小
    embed_dimension = 1024  # 中高嵌入维度

    model_id = server.add_model({
        "name": model_name,
        "input_h": 256,
        "input_w": 256,
        "end_acc": 0.95,
        "layers": layers,
        "patchsize": patchsize,
        "embed_dimension": embed_dimension
    })
    print(f"创建模型成功: 名称={model_name}, ID={model_id}")

    # 2. 获取模型列表
    print("\n2. 测试获取模型列表")
    models = server.list_model()
    print(f"模型列表: {models}")
    # 检查新模型是否在列表中
    model_exists = False
    for model in models:
        if model.get("name") == model_name:
            model_id = model.get("id")
            model_exists = True
            break
    if model_exists:
        print(f"在列表中找到新模型，ID: {model_id}")
    else:
        print("警告: 未在列表中找到新添加的模型")
        exit(1)

    # 3. 开始训练模型
    print(f"\n3. 测试开始训练模型 (模型ID: {model_id}, 组ID: {group_id})")
    try:
        train_result = server.train_model(model_id, group_id)
        print(f"----- 开始训练: {train_result} -----")
    except Exception as e:
        print(f"开始训练失败: {str(e)}")

    # 4/5. 获取训练进度，以及训练实时信息
    print(f"\n4/5. 测试获取训练进度，以及训练实时信息 (模型ID: {model_id})")
    # 循环查询训练进度
    while True:
        try:
            # 等待5秒后再次查询
            time.sleep(5)
            train_info = server.train_info(model_id) # 已训练的图像列表，通过其数量除以测试图片总数，得到训练进度
            print(f"已训练的图像列表: {train_info}")
            train_process = server.train_process(model_id)
            print(f"训练实时信息: {train_process}")
            # 如果训练完成，退出循环
            list_model = server.list_model()
            for model in list_model:
                if model.get("id") == model_id:
                    break
            if model.get("status") == 2:
                print(f"\n----- 模型训练结束 (模型ID: {model_id})-----")
                break
        except Exception as e:
            print(f"获取训练信息失败: {str(e)}")
            break

    # 6. 结束训练
    # try:
    #     finish_result = server.finish_model(model_id)
    #     print(f"结束训练: {finish_result}")
    # except Exception as e:
    #     print(f"结束训练失败: {str(e)}")

    # 7. 开始模型推理
    print(f"\n7. 测试开始模型推理 (模型ID: {model_id}, 组ID: {group_id})")
    try:
        infer_result = server.infer_model(model_id, group_id)
        print(f"----- 开始推理: {infer_result} -----")
    except Exception as e:
        print(f"开始推理失败: {str(e)}")

    # 8/9. 获取推理进度，以及推理实时信息
    print(f"\n8/9. 测试获取推理进度，以及推理实时信息 (模型ID: {model_id})")
    # 循环查询推理进度
    while True:
        try:
            # 等待1秒后再次查询
            time.sleep(1)
            infer_info = server.infer_info(model_id)
            print(f"已推理的图像列表: {infer_info}")
            infer_process = server.infer_process(model_id)
            print(f"推理信息: {infer_process}")
            # 如果推理完成，退出循环
            list_model = server.list_model()
            for model in list_model:
                if model.get("id") == model_id:
                    break
            if model.get("status") == 2:
                print(f"\n----- 模型推理结束 (模型ID: {model_id})-----")
                break
        except Exception as e:
            print(f"获取推理信息失败: {str(e)}")
            break

    # 10. 删除模型和组
    print(f"\n10. 测试删除模型 (模型ID: {model_id})")
    try:
        result = server.delete_model(model_id)
        print(f"删除模型结果: {result}")
        result = server.delete_group(group_id)
        print(f"删除组结果: {result}")
    except Exception as e:
        print(f"删除模型失败: {str(e)}")

    # 11. 再次获取模型列表
    print("\n11. 再次测试获取模型列表")
    models = server.list_model()
    print(f"模型列表: {models}")
    # 检查模型是否已被删除
    model_exists = False
    for model in models:
        if model.get("id") == model_id:
            model_exists = True
            break
    if model_exists:
        print("警告: 模型删除可能失败，模型仍在列表中")
    else:
        print("模型已成功删除")
        
    print("\n======= 测试完成 =======")


class UploadSampleGroup_HTTP:
    """
    上传样本组到服务器的线程
    """
    def __init__(self, ui):
        self.group_path = join_path(config.SAMPLE_PATH, config.SAMPLE_GROUP, config.SAMPLE_LABEL_TRAIN_GOOD) 
        self.ui = ui

    def run(self):
        # 创建进度条
        progressDialog = ProgressDialog(self.ui, {
            "title": "上传样本",
            "text": "正在上传样本组..."
        })
        progressDialog.show()
        # 获取当前样本组中的所有图片文件
        files = [f for f in os.listdir(self.group_path) if is_image(f)]
        total_files = len(files)
        if total_files == 0:
            show_message_box("警告", "样本组为空，请导入样本", QMessageBox.Warning)
            return
        # 更新进度条文本
        progressDialog.setLabelText(f"正在上传 {total_files} 个文件...")
        # 遍历并上传每个文件
        for index, file_name in enumerate(files):
            file_path = join_path(self.group_path, file_name)
            # 上传文件，若失败则停止
            try:
                group_id = HttpServer().get_group_id(config.SAMPLE_GROUP)
                HttpServer().upload_sample(file_path, group_id)
            except Exception as e:
                show_message_box("错误", f"上传失败: {str(e)}", QMessageBox.Critical)
                return
            # 更新进度条
            progress = int((index + 1) / total_files * 100)
            progressDialog.setValue(progress)
            

if __name__ == "__main__":
    # test_sample_api()
    # test_model_api()

    server = HttpServer()
    # print(server.list_model())
    # group_name = f"测试组-{int(time.time())}"
    # group_id = server.add_group(group_name)
    # print(f"创建组成功: 名称={group_name}, ID={group_id}")

    # 2. 获取组列表
    groups = server.get_group_list()
    print(f"组列表: {groups}")

    samples = server.get_sample_list(1)
    print(f"样本列表: {samples}")
    
    # # 下载样本组
    # download_dir = "B:/Development/GraduationDesign/app/test/downloads"
    # for sample in samples:
    #     server.save_downloaded_sample(sample, download_dir)

    # # 删除样本组
    # for group in groups:
    #     server.delete_group(group.get("id"))
