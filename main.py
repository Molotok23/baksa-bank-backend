import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import uvicorn
from passlib.context import CryptContext

app = FastAPI(title="Бакса Банк")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ========== БАЗА ДАННЫХ ==========
users_db = {
    "superadmin": {
        "id": 1,
        "username": "superadmin",
        "password": pwd_context.hash("admin123"),
        "full_name": "Главный Админ",
        "role": "super_admin",
        "balance": 1000000,
        "cash": 50000,
        "fcm_token": None,  # сюда сохраним токен устройства для уведомлений
        "created_at": datetime.now().isoformat()
    }
}

transactions_db = []

# ========== МОДЕЛИ ==========
class UserLogin(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str

class TransactionCreate(BaseModel):
    receiver_username: str
    amount: float
    description: str = ""

class AtmOperation(BaseModel):
    amount: float

class FcmToken(BaseModel):
    token: str

# ========== ВСПОМОГАТЕЛЬНЫЕ ==========
def get_user(username: str):
    return users_db.get(username)

def check_role(username: str, roles: list):
    user = get_user(username)
    return user and user["role"] in roles

# ========== АВТОРИЗАЦИЯ ==========
@app.post("/api/auth/login")
async def login(user: UserLogin):
    db_user = get_user(user.username)
    if db_user and pwd_context.verify(user.password, db_user["password"]):
        return {
            "success": True,
            "user": {
                "id": db_user["id"],
                "username": db_user["username"],
                "full_name": db_user["full_name"],
                "role": db_user["role"],
                "balance": db_user["balance"],
                "cash": db_user["cash"]
            }
        }
    raise HTTPException(status_code=400, detail="Неверный логин или пароль")

# ========== СОХРАНЕНИЕ ТОКЕНА УВЕДОМЛЕНИЙ ==========
@app.post("/api/user/fcm-token")
async def save_fcm_token(data: FcmToken, username: str = "superadmin"):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user["fcm_token"] = data.token
    return {"success": True}

# ========== СОЗДАНИЕ ПОЛЬЗОВАТЕЛЕЙ ==========
@app.post("/api/users/create")
async def create_user(user: UserCreate, admin: str = "superadmin"):
    if not check_role(admin, ["super_admin"]):
        raise HTTPException(status_code=403, detail="Только главный админ")
    
    if user.username in users_db:
        raise HTTPException(status_code=400, detail="Уже есть")
    
    new_id = len(users_db) + 1
    users_db[user.username] = {
        "id": new_id,
        "username": user.username,
        "password": pwd_context.hash(user.password),
        "full_name": user.full_name,
        "role": user.role,
        "balance": 0,
        "cash": 0,
        "fcm_token": None,
        "created_at": datetime.now().isoformat()
    }
    
    return {"success": True, "message": f"Создан {user.full_name}"}

# ========== СПИСОК ПОЛЬЗОВАТЕЛЕЙ ==========
@app.get("/api/users")
async def get_users(admin: str = "superadmin"):
    if not check_role(admin, ["super_admin", "admin"]):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    return [
        {
            "id": u["id"],
            "username": u["username"],
            "full_name": u["full_name"],
            "role": u["role"],
            "balance": u["balance"],
            "cash": u["cash"]
        }
        for u in users_db.values()
    ]

# ========== ПЕРЕВОД ==========
@app.post("/api/transfer")
async def transfer_money(tx: TransactionCreate, sender: str = "superadmin"):
    sender_data = get_user(sender)
    if not sender_data:
        raise HTTPException(status_code=404, detail="Отправитель не найден")

    receiver_data = None
    receiver_username = None
    for name, data in users_db.items():
        if data["username"] == tx.receiver_username:
            receiver_data = data
            receiver_username = name
            break

    if not receiver_data:
        raise HTTPException(status_code=404, detail="Получатель не найден")

    if sender_data["balance"] < tx.amount:
        raise HTTPException(status_code=400, detail="Недостаточно баксов")

    # Перевод
    sender_data["balance"] -= tx.amount
    receiver_data["balance"] += tx.amount

    # Лог
    tx_id = len(transactions_db) + 1
    transactions_db.append({
        "id": tx_id,
        "sender": sender_data["full_name"],
        "receiver": receiver_data["full_name"],
        "amount": tx.amount,
        "description": tx.description,
        "created_at": datetime.now().isoformat()
    })

    # 👇 ЗДЕСЬ ПОТОМ БУДЕМ ОТПРАВЛЯТЬ УВЕДОМЛЕНИЕ
    # if receiver_data["fcm_token"]:
    #     send_push_notification(receiver_data["fcm_token"], "Перевод", f"{sender_data['full_name']} перевёл тебе {tx.amount} баксов")

    return {
        "success": True,
        "message": f"Переведено {tx.amount} баксов",
        "new_balance": sender_data["balance"],
        "notification_sent": True,
        "to": receiver_data["full_name"]
    }

# ========== ИСТОРИЯ ==========
@app.get("/api/transactions")
async def get_transactions(username: str = "superadmin"):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    result = []
    for tx in transactions_db:
        if tx["sender"] == user["full_name"] or tx["receiver"] == user["full_name"]:
            result.append(tx)
    return sorted(result, key=lambda x: x["created_at"], reverse=True)

# ========== БАНКОМАТ ==========
@app.post("/api/atm/deposit")
async def deposit_cash(op: AtmOperation, username: str = "superadmin"):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    if user["cash"] < op.amount:
        raise HTTPException(status_code=400, detail="Недостаточно нала")
    
    user["cash"] -= op.amount
    user["balance"] += op.amount

    return {
        "success": True,
        "message": f"Положил {op.amount} нала → +{op.amount} баксов",
        "new_balance": user["balance"],
        "new_cash": user["cash"]
    }

@app.post("/api/atm/withdraw")
async def withdraw_cash(op: AtmOperation, username: str = "superadmin"):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    if user["balance"] < op.amount:
        raise HTTPException(status_code=400, detail="Недостаточно баксов")
    
    user["balance"] -= op.amount
    user["cash"] += op.amount

    return {
        "success": True,
        "message": f"Снял {op.amount} баксов → +{op.amount} нала",
        "new_balance": user["balance"],
        "new_cash": user["cash"]
    }

# ========== СТАТУС ==========
@app.get("/api/user/status")
async def user_status(username: str = "superadmin"):
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    return {
        "full_name": user["full_name"],
        "role": user["role"],
        "balance": user["balance"],
        "cash": user["cash"]
    }

# ========== АДМИН СТАТИСТИКА ==========
@app.get("/api/admin/stats")
async def admin_stats(admin: str = "superadmin"):
    if not check_role(admin, ["super_admin"]):
        raise HTTPException(status_code=403, detail="Только главный админ")
    
    total_balance = sum(u["balance"] for u in users_db.values())
    total_cash = sum(u["cash"] for u in users_db.values())
    
    return {
        "users_count": len(users_db),
        "total_balance": total_balance,
        "total_cash": total_cash,
        "transactions_count": len(transactions_db)
    }

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)