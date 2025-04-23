<p align="center" width="100%">
<img src="./images/logo.png" alt="AnomalyGPT_logo" style="width: 40%; min-width: 300px; display: block; margin: auto;" />
</p>

# AnomalyGPT：基于大型视觉语言模型的工业异常检测

![许可证](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-red.svg)

<p align="left">
   🌐 <a href="https://anomalygpt.github.io" target="_blank">项目主页</a> • 🤗 <a href="https://huggingface.co/spaces/FantasticGNU/AnomalyGPT" target="_blank">在线演示</a> • 📃 <a href="https://arxiv.org/abs/2308.15366" target="_blank">论文</a> • 🤖 <a href="https://huggingface.co/FantasticGNU/AnomalyGPT" target="_blank">模型</a> • 📹 <a href="https://www.youtube.com/watch?v=lcxBfy0YnNA" target="_blank">视频</a>
</p>

作者：顾照鹏、朱炳柯、朱贵波、陈莹莹、唐明、王金桥

****

<span id='all_catelogue'/>

## 目录

* <a href='#introduction'>1. 简介</a>
* <a href='#environment'>2. 运行AnomalyGPT演示</a>
    * <a href='#install_environment'>2.1 环境安装</a>
    * <a href='#download_imagebind_model'>2.2 准备ImageBind检查点</a>
    * <a href='#download_vicuna_model'>2.3 准备Vicuna检查点</a>
    * <a href='#download_anomalygpt'>2.4 准备AnomalyGPT增量权重</a>
    * <a href='#running_demo'>2.5 部署演示</a>
* <a href='#train_anomalygpt'>3. 训练自定义AnomalyGPT</a>
    * <a href='#data_preparation'>3.1 数据准备</a>
    * <a href='#training_configurations'>3.2 训练配置</a>
    * <a href='#model_training'>3.3 训练AnomalyGPT</a>
* <a href='#examples'>4. 示例</a>
* <a href='#license'>许可证</a>
* <a href='#citation'>引用</a>
* <a href='#acknowledgments'>致谢</a>

****

<span id='introduction'/>

### 1. 简介 <a href='#all_catelogue'>[返回顶部]</a>

<p align="center" width="100%">
<img src="./images/compare.png" alt="AnomalyGPT对比图" style="width: 80%; min-width: 400px; display: block; margin: auto;" />
</p>

**AnomalyGPT**是首个基于大型视觉语言模型（LVLM）的工业异常检测（IAD）方法，无需手动设置阈值即可检测工业图像中的异常。现有IAD方法只能提供异常分数且需要手动设置阈值，而现有LVLM无法检测图像中的异常。AnomalyGPT不仅能指示异常的存在和位置，还能提供图像相关信息。

<img src="./images/AnomalyGPT.png" alt="AnomalyGPT架构" style="zoom:100%;" />

我们通过预训练图像编码器和大型语言模型（LLM），利用模拟异常数据对齐IAD图像及其对应的文本描述。采用轻量级的视觉-文本特征匹配图像解码器获取定位结果，并设计提示学习器为LLM提供细粒度语义，通过提示嵌入微调LVLM。我们的方法还可以通过少量正常样本检测未见物品的异常。

****

<span id='environment'/>

### 2. 运行AnomalyGPT演示 <a href='#all_catelogue'>[返回顶部]</a>

<span id='install_environment'/>

#### 2.1 环境安装

克隆代码库：

```
git clone https://github.com/CASIA-IVA-Lab/AnomalyGPT.git
```

安装依赖包：

```
pip install -r requirements.txt
```

<span id='download_imagebind_model'/>

#### 2.2 准备ImageBind检查点

从[此链接](https://dl.fbaipublicfiles.com/imagebind/imagebind_huge.pth)下载预训练ImageBind模型，将文件（imagebind_huge.pth）放入[[./pretrained_ckpt/imagebind_ckpt/]](./pretrained_ckpt/imagebind_ckpt/)目录。

<span id='download_vicuna_model'/>

#### 2.3 准备Vicuna检查点

按照[[此处]](./pretrained_ckpt#1-prepare-vicuna-checkpoint)说明准备预训练Vicuna模型。

<span id='download_anomalygpt'/>

#### 2.4 准备AnomalyGPT增量权重

使用[PandaGPT](https://github.com/yxuansu/PandaGPT)的预训练参数初始化模型，不同策略的训练权重如下表所示。实验和在线演示使用Vicuna-7B和`openllmplayground/pandagpt_7b_max_len_1024`，改用Vicuna-13B预期效果更佳。

| **基础语言模型** | **最大序列长度** |            **Huggingface增量权重地址**             |
| :--------------: | :--------------: | :-----------------------------------------------: |
|  Vicuna-7B (v0)  |       512        | [openllmplayground/pandagpt_7b_max_len_512](https://huggingface.co/openllmplayground/pandagpt_7b_max_len_512) |
|  Vicuna-7B (v0)  |       1024       | [openllmplayground/pandagpt_7b_max_len_1024](https://huggingface.co/openllmplayground/pandagpt_7b_max_len_1024) |
| Vicuna-13B (v0)  |       256        | [openllmplayground/pandagpt_13b_max_len_256](https://huggingface.co/openllmplayground/pandagpt_13b_max_len_256) |
| Vicuna-13B (v0)  |       400        | [openllmplayground/pandagpt_13b_max_len_400](https://huggingface.co/openllmplayground/pandagpt_13b_max_len_400) |

将下载的7B/13B增量权重文件（pytorch_model.pt）放入[./pretrained_ckpt/pandagpt_ckpt/7b/](./pretrained_ckpt/pandagpt_ckpt/7b/)或[./pretrained_ckpt/pandagpt_ckpt/13b/](./pretrained_ckpt/pandagpt_ckpt/13b/)目录。

下载AnomalyGPT权重：

|                  训练设置与数据集                  | 权重地址 |
| :-----------------------------------------------: | :------: |
|            MVTec-AD无监督训练           | [AnomalyGPT/train_mvtec](https://huggingface.co/FantasticGNU/AnomalyGPT/blob/main/train_mvtec/pytorch_model.pt) |
|             VisA无监督训练              | [AnomalyGPT/train_visa](https://huggingface.co/FantasticGNU/AnomalyGPT/blob/main/train_visa/pytorch_model.pt) |
| MVTec-AD/VisA/MVTec-LOCO-AD/CrackForest有监督训练 | [AnomalyGPT/train_supervised](https://huggingface.co/FantasticGNU/AnomalyGPT/blob/main/train_supervised/pytorch_model.pt) |

将AnomalyGPT权重放入[./code/ckpt/](./code/ckpt/)目录，在线演示默认使用有监督训练模型。

<span id='running_demo'/>

#### 2.5 部署演示

完成上述步骤后运行：
```bash
cd ./code/
python web_demo.py
```

****

<span id='train_anomalygpt'/>

### 3. 训练自定义AnomalyGPT <a href='#all_catelogue'>[返回顶部]</a>

**前提条件**：确保环境正确安装且已下载ImageBind、Vicuna和PandaGPT检查点。

<span id='data_preparation'/>

#### 3.1 数据准备

从[此链接](https://www.mvtec.com/company/research/datasets/mvtec-ad/downloads)下载MVTec-AD数据集，从[此链接](https://github.com/amazon-science/spot-diff)下载VisA数据集，PandaGPT预训练数据从[此处](https://huggingface.co/datasets/openllmplayground/pandagpt_visual_instruction_dataset/tree/main)下载，数据目录结构如下：

```
data
|---pandagpt4_visual_instruction_data.json
|---images
|-----|-- ...
|---mvtec_anomaly_detection
|-----|-- bottle
|-----|-----|----- ground_truth
|-----|-----|----- test
|-----|-----|----- train
|-----|-- ...
|----VisA
|-----|-- split_csv
|-----|-----|--- 1cls.csv
|-----|-- candle
|-----|-----|--- Data
|-----|-----|-----|----- Images
|-----|-----|-----|----- Masks
|-----|-- ...
```

<span id='training_configurations'/>

#### 3.2 训练配置

使用2块RTX3090 GPU的训练超参数：

| **基础语言模型** | **训练轮次** | **批大小** | **学习率** | **最大长度** |
| :--------------: | :----------: | :--------: | :--------: | :----------: |
|     Vicuna-7B    |      50      |     16     |    1e-3    |     1024     |

<span id='model_training'/>

#### 3.3 训练AnomalyGPT

运行训练脚本：
```yaml
cd ./code
bash ./scripts/train_mvtec.sh
```

关键参数：
- `--data_path`: PandaGPT视觉指令数据JSON文件路径
- `--image_root_path`: 训练图像根路径
- `--imagebind_ckpt_path`: ImageBind检查点路径
- `--vicuna_ckpt_path`: Vicuna预训练检查点目录
- `--max_tgt_len`: 训练实例最大序列长度
- `--save_path`: 增量权重保存目录
- `--log_path`: 日志保存目录

****

<span id='examples'/>

### 4. 示例

![](./images/demo_1.png)
<h4 align='center'>有裂缝的混凝土</h4>

![](./images/demo_5.png)
<h4 align='center'>破损的胶囊</h4>

![](./images/demo_8.png)
<h4 align='center'>切开的榛子</h4>

![](./images/demo_7.png)
<h4 align='center'>损坏的瓶子</h4>

****

<span id='license'/>

### 许可证

AnomalyGPT采用[CC BY-NC-SA 40许可证](./LICENSE)。

****

<span id='citation'/>

### 引用

```
@article{gu2023anomalyagpt,
  title={AnomalyGPT: Detecting Industrial Anomalies using Large Vision-Language Models},
  author={Gu, Zhaopeng and Zhu, Bingke and Zhu, Guibo and Chen, Yingying and Tang, Ming and Wang, Jinqiao},
  journal={arXiv preprint arXiv:2308.15366},
  year={2023}
}
```

****

<span id='acknowledgments'/>

### 致谢

感谢[PandaGPT](https://github.com/yxuansu/PandaGPT)提供的代码和预训练权重。

[![Star History Chart](https://api.star-history.com/svg?repos=CASIA-IVA-Lab/AnomalyGPT&type=Date)](https://star-history.com/#CASIA-IVA-Lab/AnomalyGPT&Date)