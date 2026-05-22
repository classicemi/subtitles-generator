WHISPER_MODEL ?= medium
BACKEND_PORT  ?= 8000
FRONTEND_PORT ?= 5173

ROOT_DIR   := $(shell pwd)
VENV       := $(ROOT_DIR)/.venv
PIP        := $(VENV)/bin/pip
PYTHON     := $(VENV)/bin/python
UVICORN    := $(VENV)/bin/uvicorn
WHISPER_DIR := $(ROOT_DIR)/vendor/whisper.cpp
WHISPER_CLI := $(WHISPER_DIR)/build/bin/whisper-cli
MODEL_FILE := $(ROOT_DIR)/models/ggml-$(WHISPER_MODEL).bin
PID_DIR    := $(ROOT_DIR)/data
BACKEND_PID := $(PID_DIR)/.backend.pid
FRONTEND_PID := $(PID_DIR)/.frontend.pid

.PHONY: setup start stop clean
.PHONY: setup-python setup-whisper setup-model setup-frontend
.PHONY: build-whisper download-model build-frontend

# ── One-time setup ───────────────────────────────────────────────

setup: setup-python setup-whisper setup-model setup-frontend
	@echo ""
	@echo "Setup complete. Run 'make start' to launch the app."

setup-python: $(VENV)/bin/activate

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt
	touch $@

setup-whisper: $(WHISPER_CLI)

$(WHISPER_CLI): $(WHISPER_DIR)/CMakeLists.txt
	@mkdir -p $(PID_DIR)
	cmake -B $(WHISPER_DIR)/build -S $(WHISPER_DIR)
	cmake --build $(WHISPER_DIR)/build --config Release

$(WHISPER_DIR)/CMakeLists.txt:
	@echo "Cloning whisper.cpp..."
	git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git $(WHISPER_DIR)

setup-model: $(MODEL_FILE)

$(MODEL_FILE):
	@mkdir -p $(ROOT_DIR)/models
	@echo "Downloading ggml-$(WHISPER_MODEL).bin (~1.5 GB)..."
	curl -L -# -o $(MODEL_FILE) \
		https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-$(WHISPER_MODEL).bin
	@echo "Model saved to $(MODEL_FILE)"

setup-frontend: frontend/node_modules/.package-lock.json

frontend/node_modules/.package-lock.json: frontend/package.json
	cd frontend && npm install

build-frontend:
	cd frontend && npm run build

# ── Start / Stop services ────────────────────────────────────────

start: build-frontend
	@mkdir -p $(PID_DIR)
	@if [ -f $(BACKEND_PID) ] && kill -0 $$(cat $(BACKEND_PID)) 2>/dev/null; then \
		echo "Backend already running (PID $$(cat $(BACKEND_PID)))"; \
	else \
		$(UVICORN) app.main:app --reload --host 127.0.0.1 --port $(BACKEND_PORT) \
			> $(PID_DIR)/backend.log 2>&1 & \
		echo $$! > $(BACKEND_PID); \
		echo "Backend  started (PID $$!)  http://127.0.0.1:$(BACKEND_PORT)"; \
	fi
	@if [ -f $(FRONTEND_PID) ] && kill -0 $$(cat $(FRONTEND_PID)) 2>/dev/null; then \
		echo "Frontend already running (PID $$(cat $(FRONTEND_PID)))"; \
	else \
		cd frontend && npx vite --host 127.0.0.1 --port $(FRONTEND_PORT) \
			> $(PID_DIR)/frontend.log 2>&1 & \
		echo $$! > $(FRONTEND_PID); \
		echo "Frontend started (PID $$!)  http://127.0.0.1:$(FRONTEND_PORT)"; \
	fi
	@echo ""
	@echo "Open http://127.0.0.1:$(FRONTEND_PORT) in your browser."
	@echo "Run 'make stop' to shut down both services."

stop:
	@if [ -f $(BACKEND_PID) ]; then \
		PID=$$(cat $(BACKEND_PID)); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID 2>/dev/null || true; \
			echo "Backend  stopped (PID $$PID)"; \
		else \
			echo "Backend  was not running (stale PID $$PID)"; \
		fi; \
		rm -f $(BACKEND_PID); \
	else \
		echo "Backend  was not running"; \
	fi
	@if [ -f $(FRONTEND_PID) ]; then \
		PID=$$(cat $(FRONTEND_PID)); \
		if kill -0 $$PID 2>/dev/null; then \
			kill $$PID 2>/dev/null || true; \
			echo "Frontend stopped (PID $$PID)"; \
		else \
			echo "Frontend was not running (stale PID $$PID)"; \
		fi; \
		rm -f $(FRONTEND_PID); \
	else \
		echo "Frontend was not running"; \
	fi

# ── Cleanup ──────────────────────────────────────────────────────

clean: stop
	rm -rf $(VENV)
	rm -rf frontend/node_modules
	rm -rf $(WHISPER_DIR)
	rm -f $(MODEL_FILE)
	rm -rf $(PID_DIR)
