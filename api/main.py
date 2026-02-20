from fastapi import FastAPI, Depends, HTTPException, status, Form, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List
from api.recognition import face_engine # Наш ML движок
from api.s3 import s3                   # Наш S3 клиент
from api import models, schemas, auth, database
from api.database import engine

# Автоматическое создание таблиц (если alembic заглючил, но лучше использовать миграции)
models.Base.metadata.create_all(bind=engine)

tags_metadata = [
    {"name": "auth", "description": "Аутентификация и получение токенов."},
    {"name": "users", "description": "Управление пользователями."},
    {"name": "logs", "description": "Просмотр журналов посещаемости."},
]

app = FastAPI(
    title="Face Tracker API",
    description="Система учета рабочего времени на основе распознавания лиц.",
    version="1.0.0",
    openapi_tags=tags_metadata
)

from fastapi.middleware.cors import CORSMiddleware
import time
from fastapi import Request

# Разрешаем запросы с фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # В продакшене тут ставят конкретный домен, но для демо "*" ок
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Бонус: замер скорости работы (очень круто выглядит в отчете)
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Пример использования в эндпоинте:
@app.get("/logs", tags=["logs"], summary="Получить последние записи")
def get_logs():
    ...

# 2. Потом создаем эндпоинты
@app.post("/api/v1/employees/register")
async def register_employee(
    name: str = Form(...),
    code: str = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(database.get_db)
):
    # 1. Читаем байты загруженного изображения
    image_bytes = await photo.read()
    
    # 2. Просим нейросеть найти лицо и вернуть вектор
    # В ТЗ указано использование InsightFace для извлечения признаков.
    embedding, error = face_engine.get_embedding(image_bytes)
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not embedding:
        raise HTTPException(status_code=400, detail="Лицо не распознано на фото")

    # 3. Сохраняем оригинал фото в MinIO (S3)
    file_name = f"{code}_{photo.filename}"
    s3.upload_file(image_bytes, file_name)
    
    # 4. Записываем всё в PostgreSQL
    new_emp = models.Employee(
        name=name,
        employee_code=code,
        face_embedding=embedding, # Тот самый вектор из 512 чисел
        photo_s3_key=file_name
    )
    
    try:
        db.add(new_emp)
        db.commit() # Теперь данные точно попадут в базу!
        db.refresh(new_emp)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка БД: {str(e)}")
    
    return {
        "status": "success", 
        "employee_id": new_emp.id, 
        "message": f"Сотрудник {name} успешно зарегистрирован"
    }

@app.on_event("startup")
def create_default_admin():
    db = database.SessionLocal()
    user = db.query(models.User).filter(models.User.username == "admin").first()
    if not user:
        hashed_pwd = auth.get_password_hash("admin") # Пароль: admin
        new_user = models.User(username="admin", password_hash=hashed_pwd)
        db.add(new_user)
        db.commit()
        print("Admin user created: admin / admin")
    db.close()

# --- 1. Auth Endpoint ---
@app.post("/api/v1/auth/login", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# --- 2. Camera CRUD ---
@app.post("/api/v1/cameras", response_model=schemas.CameraResponse)
def create_camera(camera: schemas.CameraCreate, 
                  db: Session = Depends(database.get_db), 
                  current_user: str = Depends(auth.get_current_user)): # Защищено авторизацией
    
    db_camera = models.Camera(**camera.dict())
    db.add(db_camera)
    db.commit()
    db.refresh(db_camera)
    return db_camera

@app.get("/api/v1/cameras", response_model=List[schemas.CameraResponse])
def get_cameras(db: Session = Depends(database.get_db), 
                current_user: str = Depends(auth.get_current_user)):
    return db.query(models.Camera).all()

from fastapi.responses import FileResponse

@app.get("/api/v1/camera/{camera_id}/snapshot")
async def get_snapshot(camera_id: int):
    # Путь к файлу, который сохраняет твой воркер
    return FileResponse("live_check.jpg")

# --- 3. Attendance Logs ---
@app.get("/api/v1/attendance", response_model=List[schemas.LogResponse])
def get_logs(db: Session = Depends(database.get_db), 
             current_user: str = Depends(auth.get_current_user)):
    # Джойним таблицы, чтобы получить имена вместо ID
    results = db.query(
        models.AttendanceLog, models.Employee.name.label("emp_name"), models.Camera.name.label("cam_name")
    ).join(models.Employee, models.AttendanceLog.employee_id == models.Employee.id)\
     .join(models.Camera, models.AttendanceLog.camera_id == models.Camera.id)\
     .all()
    
    # Формируем ответ вручную, т.к. SQLALchemy возвращает кортежи при join
    response = []
    for log, emp_name, cam_name in results:
        resp = schemas.LogResponse(
            id=log.id,
            employee_name=emp_name,
            camera_name=cam_name,
            timestamp=log.timestamp,
            delay_minutes=log.delay_minutes
        )
        response.append(resp)
    return response

from fastapi.responses import FileResponse
import os

@app.get("/api/v1/camera/snapshot") 
async def get_snapshot(): # Тот самый файл, который генерирует твой воркер при распознавании 
    file_path = "live_check.jpg" 
    if os.path.exists(file_path): 
        return FileResponse(file_path) 
    return {"error": "Snapshot not ready yet"}

# TODO: В будущем рассмотреть возможность шардирования БД для этой таблицы