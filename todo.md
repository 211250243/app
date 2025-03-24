1. upload_sample(file, group_id) // 上传样本
2. download_sample(filename) // 下载样本
3. get_sample_list(group_id) // 获取一个组的样本名列表
4. add_group(group_name) // 添加组
5. delete_group(group_id) // 删除组
6. get_group_list() // 获取组名列表

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
@app.get("/get_group_list")
def get_group_list(db: Session = Depends(get_db)):
    return db.query(File_Group_Info_DB).all()
```