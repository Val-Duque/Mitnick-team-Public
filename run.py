"""Arranque rápido:  python run.py   (docs en http://127.0.0.1:8081/docs)"""
import uvicorn
from app.config import HOST, PORT

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
