.PHONY: help dev prod install-backend install-frontend init-db clean

help:
	@echo "Stock Watchlist - Make Commands"
	@echo "  make dev         - Run backend (dev mode with reload)"
	@echo "  make frontend    - Run frontend dev server"
	@echo "  make prod        - Build & run with Docker Compose"
	@echo "  make init-db     - Initialize database"
	@echo "  make install     - Install all dependencies"
	@echo "  make clean       - Clean build artifacts"

dev:
	cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	cd frontend && npm run dev

prod:
	docker compose up --build -d
	@echo "Production running at http://localhost:80"

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

init-db:
	cd backend && python init_db.py

clean:
	rm -rf frontend/dist frontend/node_modules/.vite backend/__pycache__ backend/**/__pycache__
