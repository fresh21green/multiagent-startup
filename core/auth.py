from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from pathlib import Path
import json, os

# === ИНИЦИАЛИЗАЦИЯ ===
router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
DATA_DIR = BASE / "data"
USERS_FILE = DATA_DIR / "users.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 360
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# === УТИЛИТЫ ===
def load_users():
    if not USERS_FILE.exists():
        USERS_FILE.write_text("[]", encoding="utf-8")
    return json.loads(USERS_FILE.read_text(encoding="utf-8"))

def save_users(users):
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

def verify_password(plain, hashed): 
    return pwd_context.verify(plain, hashed)

def get_password_hash(password): 
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# === РЕГИСТРАЦИЯ ===
@router.post("/register")
async def register(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    if any(u["username"] == username for u in users):
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    users.append({"username": username, "password": get_password_hash(password)})
    save_users(users)
    return {"ok": True, "message": f"Пользователь {username} зарегистрирован"}

# === ВХОД (API) ===
@router.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    user = next((u for u in users if u["username"] == username), None)
    if not user or not verify_password(password, user["password"]):
        raise HTTPException(status_code=401, detail="Неверные учетные данные")
    token = create_access_token({"sub": username})
    return {"ok": True, "access_token": token, "token_type": "bearer"}

# === HTML-СТРАНИЦА ВХОДА ===
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Простая форма логина"""
    return templates.TemplateResponse("login.html", {"request": request})

# === ПРОВЕРКА ТОКЕНА ===
def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Неверный токен")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Неверный токен")

# === ЗАЩИЩЕННЫЙ ТЕСТОВЫЙ МАРШРУТ ===
@router.get("/me")
async def read_users_me(user: str = Depends(get_current_user)):
    return {"ok": True, "user": user}
