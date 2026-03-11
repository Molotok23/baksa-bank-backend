from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
from datetime import datetime
import random

app = FastAPI()

# Разрешаем запросы с любых сайтов (для разработки)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Временная база данных в памяти (пока без настоящей БД)
users_db = {
    "superadmin": {
        "id": 1,
        "username": "superadmin",
        "password": "admin123",  # в реальном проекте нужно хешировать
        "full_name": "Главный Админ",
        "role": "super_admin",
        "balance": 1000000.00,
        "created_at": datetime.now().isoformat()
    }
}

# Модели данных
class UserLogin(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str  # "admin" или "worker"

class TransactionCreate(BaseModel):
    receiver_username: str
    amount: float
    description: str = ""

# Корневой маршрут для проверки
@app.get("/")
async def root():
    return {"message": "Бакса Банк API работает!", "status": "online"}

# Регистрация/вход
@app.post("/api/auth/login")
async def login(user: UserLogin):
    # Ищем пользователя
    if user.username in users_db:
        if users_db[user.username]["password"] == user.password:
            return {
                "success": True,
                "user": {
                    "id": users_db[user.username]["id"],
                    "username": users_db[user.username]["username"],
                    "full_name": users_db[user.username]["full_name"],
                    "role": users_db[user.username]["role"],
                    "balance": users_db[user.username]["balance"]
                }
            }
    raise HTTPException(status_code=400, detail="Неверный логин или пароль")

# Создание пользователя (только для super_admin)
@app.post("/api/users/create")
async def create_user(user: UserCreate):
    # Проверяем, есть ли уже такой пользователь
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    
    # Создаем нового пользователя
    new_id = len(users_db) + 1
    users_db[user.username] = {
        "id": new_id,
        "username": user.username,
        "password": user.password,
        "full_name": user.full_name,
        "role": user.role,
        "balance": 0.00,
        "created_at": datetime.now().isoformat()
    }
    
    return {"success": True, "message": f"Пользователь {user.full_name} создан"}

# Получить всех пользователей
@app.get("/api/users")
async def get_users():
    users_list = []
    for username, data in users_db.items():
        users_list.append({
            "id": data["id"],
            "username": data["username"],
            "full_name": data["full_name"],
            "role": data["role"],
            "balance": data["balance"]
        })
    return users_list

# Перевод денег
@app.post("/api/transactions/send")
async def send_money(transaction: TransactionCreate):
    # Здесь нужно будет добавить проверку отправителя
    # Пока для теста будем использовать первого админа
    sender = users_db["superadmin"]
    
    # Ищем получателя
    receiver = None
    for username, data in users_db.items():
        if data["username"] == transaction.receiver_username:
            receiver = data
            break
    
    if not receiver:
        raise HTTPException(status_code=404, detail="Получатель не найден")
    
    # Проверяем достаточно ли денег
    if sender["balance"] < transaction.amount:
        raise HTTPException(status_code=400, detail="Недостаточно средств")
    
    # Переводим деньги
    sender["balance"] -= transaction.amount
    receiver["balance"] += transaction.amount
    
    return {
        "success": True,
        "message": f"Переведено {transaction.amount} пользователю {receiver['full_name']}",
        "new_balance": sender["balance"]
    }

# Получить баланс пользователя
@app.get("/api/balance/{username}")
async def get_balance(username: str):
    if username in users_db:
        return {"username": username, "balance": users_db[username]["balance"]}
    raise HTTPException(status_code=404, detail="Пользователь не найден")

# Запуск сервера (для теста)
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)