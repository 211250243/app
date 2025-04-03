## 大模型对接

1. anomaly_gpt_infer(img_list, question, normal_img_list, history)

```python
@app.post("/anomaly_gpt_infer")
def anomaly_gpt_infer(input :AnomalyGPT_Input,db: Session = Depends(get_db)):
    print(input)
    full_path_img_list = [os.path.join(os.path.join(data_path,'images'), _) for _ in input.img_list]
    normal_img_list = [os.path.join(os.path.join(data_path,'images'), _) for _ in input.normal_img_list]
    ans = []
    for full_path in full_path_img_list:
        response= predict(input.question,full_path,normal_img_list,input.history,os.path.join(data_path,'images'))
        print(response)
        ans.append(response)
    return ans
```

## 模型操作

1. add_model(model) // 添加模型
2. delete_model(model_id) // 删除模型
3. update_model_params(id, params) // 更新模型参数
4. list_model() // 获取模型列表
5. train_info(model_id) // 获取模型已训练的图像列表(由此可知训练进度)
6. infer_info(model_id) // 获取模型已推理的图像列表(由此可知推理进度)
7. train_process(model_id) // 获取模型训练实时信息
8. infer_process(model_id) // 获取模型推理实时信息
9. train_model(model_id, group_id) // 训练模型
10. finish_model(model_id) // 结束训练
11. infer_model(model_id, group_id) // 推理模型

```python
# 增删查模型
@app.post("/add_model")
def add_model(model: Model_Info, db: Session = Depends(get_db)):
    db_model = Model_Info_DB(
        name=model.name,
        input_h=model.input_h,
        input_w=model.input_w,
        end_acc = model.end_acc,
        layers = model.layers,
        patchsize = model.patchsize,
        embed_dimension=model.embed_dimension,
    )
    db.add(db_model)
    db.commit()
    db.refresh(db_model)
    return db_model.id
@app.delete("/delete_model/{model_id}")
def delete_model(model_id: int, db: Session = Depends(get_db)):
    db.query(Model_Trian_Info_DB).filter(Model_Trian_Info_DB.model_id==model_id).delete()
    remove_model_in_cache(model_id)
    model_dir = os.path.join(data_path,f"model-{model_id}")
    if os.path.exists(model_dir):
        shutil.rmtree(model_dir)
    db.commit()
    return {"message": "Model deleted successfully"}
@app.get("/list_model")
def list_model(db: Session = Depends(get_db)):
    model_list = db.query(Model_Info_DB).all()
    return model_list

# 获取训练、推理信息
@app.post("/train_info/{model_id}")
def train_info(model_id: int, db: Session = Depends(get_db)):
    x = db.query(Model_Trian_Info_DB).filter(Model_Trian_Info_DB.model_id == model_id).all()
    res={}
    for value in x:
        res[value.img_filename]=''
    res = list(res.keys())
    return res
@app.post("/infer_info/{model_id}")
def infer_info(model_id: int, db: Session = Depends(get_db)):
    x = db.query(Model_Infer_Info_DB).filter(Model_Infer_Info_DB.model_id == model_id).all()
    return x
@app.post('/train_process/{model_id}')
def train_process(model_id: int , db: Session = Depends(get_db)):
    model_info = db.query(Model_Info_DB).filter(Model_Info_DB.id == model_id).first()
    model = get_model_from_cache(model_info)
    return model.plot_data
@app.post('/infer_process/{model_id}')
def infer_process(model_id: int, db: Session = Depends(get_db)):
    model_info = db.query(Model_Info_DB).filter(Model_Info_DB.id == model_id).first()
    model = get_model_from_cache(model_info)
    result = 0
    if(model.to_infer_num>0):
        result = model.have_infer_num / model.to_infer_num
    return {"inferPercentage":result}

# 训练、推理
@app.post('/train_model/{model_id}')
def train_model(model_id: int, background_tasks: BackgroundTasks, group_id : int = None, db: Session = Depends(get_db)):
    # 查询模型信息
    model_info = db.query(Model_Info_DB).filter(Model_Info_DB.id == model_id).first()
    # 更新模型状态为“正在训练”
    model_info.status = 1
    db.commit()
    db.refresh(model_info)
    # 将训练任务作为后台任务进行处理
    background_tasks.add_task(train_model_async, model_info, group_id)
    # 返回一个响应，表示任务已提交
    return {"message": "Model training started", "model_id": model_id}
@app.post('/finish_model/{model_id}')
def finish_model(model_id: int , db: Session = Depends(get_db)):
    model_info = db.query(Model_Info_DB).filter(Model_Info_DB.id == model_id).first()
    model = get_model_from_cache(model_info)
    if model.finish_signal ==False:
        model.finish_signal =True
    return {}
@app.post("/infer_model/{model_id}")
async def infer_model(model_id: int, background_tasks: BackgroundTasks, group_id:int= None,db: Session = Depends(get_db)):
    model_info = db.query(Model_Info_DB).filter(Model_Info_DB.id == model_id).first()
    # 恢复到原状态
    pre_status =model_info.status
    # 更新模型状态为“正在推理”
    model_info.status = 3
    db.commit()
    db.refresh(model_info)
    background_tasks.add_task(infer_model_async, model_info, group_id, pre_status)
    return {}
```

## 样本组操作

1. upload_sample(file, group_id) // 上传样本
2. download_sample(filename) // 下载样本
3. get_sample_list(group_id) // 获取一个组的样本名列表
4. add_group(group_name) // 添加组
5. delete_group(group_id) // 删除组
6. clear_group(group_id) // 清空组
7. get_group_list() // 获取组名列表

```python
@app.post("/upload_sample")
def upload_sample(file: UploadFile = File(...),group_id:int = None,db: Session = Depends(get_db)):
    file.filename = str(uuid.uuid4()) + "-" + file.filename
    file_location = f"{data_path}/images/{file.filename}"
    print(f"group_id:{group_id}")
    with open(file_location, "wb") as buffer:
        buffer.write(file.file.read())
    if group_id is not None:
        relation = File_Group_Relation_DB(group_id=group_id,file_name = file.filename)
        db.add(relation)
        db.commit()
        print(f"{file.filename}加入group{group_id}")
    return {"filename": file.filename}
@app.get("/download_sample")
def download_sample(info: Single_Info):
    file_location = f"{data_path}/images/{info.filename}"
    print(file_location)
    try:
        with open(file_location, "rb") as file:
            return Response(content=file.read(), media_type="image/jpeg")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found")
@app.get("/get_sample_list/{group_id}")
def get_sample_list(group_id: int,db: Session = Depends(get_db)):
    file_name_list = db.query(File_Group_Relation_DB).filter(File_Group_Relation_DB.group_id == group_id).all()
    ans = []
    for relation in file_name_list:
        ans.append(relation.file_name)
    return ans
@app.post("/add_group")
def add_group(info: Single_Info, db: Session = Depends(get_db)):
    db_model = File_Group_Info_DB(
        group_name=info.group_name
    )
    db.add(db_model)
    db.commit()
    db.refresh(db_model)
    return db_model.id
@app.delete("/delete_group/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    db.query(File_Group_Info_DB).filter(File_Group_Info_DB.id==group_id).delete()
    db.commit()
    return {"message": "Model deleted successfully"}
@app.post("/clear_group/{group_id}")
def clear_group(group_id: int, db: Session = Depends(get_db)):
    db.query(File_Group_Relation_DB).filter(File_Group_Relation_DB.group_id == group_id).delete()
    db.commit()
    return {"message": "Group cleared successfully"}
@app.get("/get_group_list")
def get_group_list(db: Session = Depends(get_db)):
    return db.query(File_Group_Info_DB).all()
```