import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
import ctypes
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from dotenv import dotenv_values
from PIL import Image
from simulation_profiles import (
    create_profile,
    get_active_profile,
    get_database_path_for_current_mode,
    list_profiles,
    reset_profile,
    set_active_profile,
)


APP_NAME = "InversorIA Launcher"
PORT = 8501


TEXT = {
    "es": {
        "title": "InversorIA",
        "subtitle": "Centro de mando local para tu bot de trading",
        "mission": "Arranca la web, controla el daemon y cambia entre simulación y real con seguridad.",
        "language": "Idioma",
        "mode": "Modo de arranque",
        "simulation": "Simulación",
        "real": "Real",
        "start_system": "Iniciar sistema",
        "open_web": "Abrir web",
        "stop_bot": "Detener bot",
        "stop_all": "Detener todo",
        "configure_apis": "Configurar APIs",
        "api_status": "APIs",
        "api_ready": "Configuradas",
        "api_missing": "Faltan datos",
        "status": "Estado",
        "web": "Web",
        "daemon": "Daemon",
        "trading": "Trading",
        "active": "Activo",
        "inactive": "Inactivo",
        "paused": "Pausado",
        "armed": "Armado",
        "heartbeat": "latido",
        "no_heartbeat": "sin latido",
        "mode_label": "Modo",
        "simulation_profile": "Perfil simulación",
        "initial_capital": "Capital inicial USDT",
        "new_profile": "Crear perfil",
        "reset_profile": "Reset perfil",
        "profile_created": "Perfil creado y activado.",
        "profile_reset": "Perfil reiniciado.",
        "profile_name": "Nombre del perfil",
        "port": "Puerto",
        "logs": "Log del daemon",
        "logs_hint": "Escaneo en vivo del bot: decisiones por símbolo, proveedores IA, filtros y errores.",
        "ready": "Listo.",
        "starting": "Arrancando sistema...",
        "waiting_web": "Esperando a que la web esté lista",
        "streamlit_started": "Web iniciada.",
        "daemon_started": "Daemon iniciado.",
        "already_running": "Ya estaba iniciado.",
        "opening_web": "Abriendo navegador...",
        "stopping_bot": "Deteniendo bot...",
        "stopping_all": "Deteniendo procesos...",
        "stopped": "Detenido.",
        "close_title": "Cerrar InversorIA Launcher",
        "close_warning": (
            "Si cierras el launcher se detendrán también la web y el daemon iniciados desde aquí.\n\n"
            "¿Quieres cerrar y detener todo?"
        ),
        "real_title": "Confirmar modo real",
        "real_warning": (
            "Vas a iniciar InversorIA en modo REAL.\n\n"
            "Esto puede enviar órdenes reales al exchange si el bot está activo.\n"
            "Confirma solo si has revisado configuración, claves y riesgo."
        ),
        "missing_keys_title": "Claves no detectadas",
        "missing_keys": (
            "No se han detectado CRYPTO_API_KEY y/o CRYPTO_API_SECRET en .env.\n\n"
            "No iniciaré el daemon en modo real hasta que estén configuradas."
        ),
        "setup_title": "Configurar APIs",
        "setup_required": "Faltan claves necesarias para arrancar correctamente. Rellena las APIs y guarda para crear/actualizar .env.",
        "setup_help": "Las claves se guardan solo en este equipo, en .env. No se incluyen en Git ni en el exe.",
        "exchange_section": "Exchange",
        "ai_section": "Inteligencia artificial",
        "data_section": "Datos y noticias",
        "required": "requerida",
        "optional": "opcional",
        "configured": "configurada",
        "missing": "falta",
        "save_apis": "Guardar APIs",
        "cancel": "Cancelar",
        "env_saved": ".env guardado correctamente.",
        "env_backup": "Backup creado",
        "delete_local_keys": "Borrar claves locales",
        "delete_confirm": "¿Seguro que quieres borrar las claves locales de .env?",
        "python_missing": "No encuentro Python/venv para ejecutar la app.",
        "project_missing": "No encuentro app.py o bot_daemon.py en la carpeta del proyecto.",
        "mode_saved": "Modo guardado.",
        "db_error": "Error accediendo a la base de datos",
    },
    "en": {
        "title": "InversorIA",
        "subtitle": "Local command center for your trading bot",
        "mission": "Start the web app, control the daemon and switch between simulation and real mode safely.",
        "language": "Language",
        "mode": "Startup mode",
        "simulation": "Simulation",
        "real": "Real",
        "start_system": "Start system",
        "open_web": "Open web",
        "stop_bot": "Stop bot",
        "stop_all": "Stop all",
        "configure_apis": "Configure APIs",
        "api_status": "APIs",
        "api_ready": "Configured",
        "api_missing": "Missing data",
        "status": "Status",
        "web": "Web",
        "daemon": "Daemon",
        "trading": "Trading",
        "active": "Active",
        "inactive": "Inactive",
        "paused": "Paused",
        "armed": "Armed",
        "heartbeat": "heartbeat",
        "no_heartbeat": "no heartbeat",
        "mode_label": "Mode",
        "simulation_profile": "Simulation profile",
        "initial_capital": "Initial USDT capital",
        "new_profile": "Create profile",
        "reset_profile": "Reset profile",
        "profile_created": "Profile created and activated.",
        "profile_reset": "Profile reset.",
        "profile_name": "Profile name",
        "port": "Port",
        "logs": "Daemon log",
        "logs_hint": "Live bot scan: symbol decisions, AI providers, filters and errors.",
        "ready": "Ready.",
        "starting": "Starting system...",
        "waiting_web": "Waiting for web app to be ready",
        "streamlit_started": "Web started.",
        "daemon_started": "Daemon started.",
        "already_running": "Already running.",
        "opening_web": "Opening browser...",
        "stopping_bot": "Stopping bot...",
        "stopping_all": "Stopping processes...",
        "stopped": "Stopped.",
        "close_title": "Close InversorIA Launcher",
        "close_warning": (
            "Closing the launcher will also stop the web app and daemon started from here.\n\n"
            "Close and stop everything?"
        ),
        "real_title": "Confirm real mode",
        "real_warning": (
            "You are about to start InversorIA in REAL mode.\n\n"
            "This can send real exchange orders if the bot is active.\n"
            "Confirm only after reviewing configuration, keys and risk."
        ),
        "missing_keys_title": "Keys not detected",
        "missing_keys": (
            "CRYPTO_API_KEY and/or CRYPTO_API_SECRET were not found in .env.\n\n"
            "The daemon will not be started in real mode until they are configured."
        ),
        "setup_title": "Configure APIs",
        "setup_required": "Required keys are missing for a proper startup. Fill in the APIs and save to create/update .env.",
        "setup_help": "Keys are stored only on this machine, in .env. They are not included in Git or in the exe.",
        "exchange_section": "Exchange",
        "ai_section": "Artificial intelligence",
        "data_section": "Data and news",
        "required": "required",
        "optional": "optional",
        "configured": "configured",
        "missing": "missing",
        "save_apis": "Save APIs",
        "cancel": "Cancel",
        "env_saved": ".env saved successfully.",
        "env_backup": "Backup created",
        "delete_local_keys": "Delete local keys",
        "delete_confirm": "Are you sure you want to delete local keys from .env?",
        "python_missing": "Could not find Python/venv to run the app.",
        "project_missing": "Could not find app.py or bot_daemon.py in the project folder.",
        "mode_saved": "Mode saved.",
        "db_error": "Database access error",
    },
}


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if exe_dir.name.lower() == "dist":
            return exe_dir.parent
        return exe_dir
    return Path(__file__).resolve().parent


ROOT = project_root()
DB_PATH = ROOT / "iversoria.db"
SETTINGS_PATH = ROOT / "user_settings.json"
ENV_PATH = ROOT / ".env"
LOG_DIR = ROOT / "launcher_logs"
LOGO_PATH = ROOT / "assets" / "inversoria_logo.png"

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

API_FIELDS = [
    ("exchange_section", "CRYPTO_API_KEY", True),
    ("exchange_section", "CRYPTO_API_SECRET", True),
    ("ai_section", "GOOGLE_API_KEY", False),
    ("ai_section", "GROQ_API_KEY", False),
    ("ai_section", "SAMBANOVA_API_KEY", False),
    ("data_section", "ALPHA_VANTAGE_API_KEY", False),
    ("data_section", "COINDESK_API_KEY", False),
]

AI_KEYS = {"GOOGLE_API_KEY", "GROQ_API_KEY", "SAMBANOVA_API_KEY"}


class InversoriaLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.lang = self._load_language()
        self.streamlit_process = None
        self.daemon_process = None
        self._streamlit_log_handle = None
        self._daemon_log_handle = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        self.title(APP_NAME)
        self.geometry("1180x820")
        self.minsize(1040, 720)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.language_var = ctk.StringVar(value="Español" if self.lang == "es" else "English")
        self.mode_var = ctk.StringVar(value=self.t("simulation") if self._current_simulation_mode() else self.t("real"))
        self.profile_var = ctk.StringVar(value="")
        self.profile_name_var = ctk.StringVar(value="")
        self.profile_capital_var = ctk.StringVar(value="60")
        self.web_state_var = ctk.StringVar(value=self.t("inactive"))
        self.daemon_state_var = ctk.StringVar(value=self.t("inactive"))
        self.trading_state_var = ctk.StringVar(value=self.t("paused"))
        self.mode_state_var = ctk.StringVar(value="-")
        self.port_state_var = ctk.StringVar(value=str(PORT))
        self.api_state_var = ctk.StringVar(value="-")
        self.status_var = ctk.StringVar(value=self.t("ready"))
        self.logo_image = self._load_logo_image()
        self._api_window = None
        self._api_entries = {}
        self._profile_display_to_id = {}
        self._api_prompt_shown = False
        self._sleep_blocked = False

        self._build_ui()
        self.refresh_texts()
        self.after(700, self._prompt_api_config_if_needed)
        self.after(1000, self.refresh_status_loop)

    def t(self, key: str) -> str:
        return TEXT.get(self.lang, TEXT["es"]).get(key, key)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.configure(fg_color="#070B12")
        header = ctk.CTkFrame(self, corner_radius=26, fg_color="#0B1220", border_width=1, border_color="#1F2937")
        header.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.grid(row=0, column=0, padx=22, pady=22, sticky="w")
        self.logo_label = ctk.CTkLabel(brand, text="", image=self.logo_image)
        self.logo_label.grid(row=0, column=0, rowspan=3, padx=(0, 18), sticky="w")
        self.title_label = ctk.CTkLabel(brand, font=ctk.CTkFont(size=34, weight="bold"))
        self.title_label.grid(row=0, column=1, sticky="w")
        self.subtitle_label = ctk.CTkLabel(brand, text_color="#A7F3D0", font=ctk.CTkFont(size=14, weight="bold"))
        self.subtitle_label.grid(row=1, column=1, pady=(2, 0), sticky="w")
        self.mission_label = ctk.CTkLabel(brand, text_color="#94A3B8", font=ctk.CTkFont(size=12))
        self.mission_label.grid(row=2, column=1, pady=(4, 0), sticky="w")

        self.language_menu = ctk.CTkOptionMenu(
            header,
            variable=self.language_var,
            values=["Español", "English"],
            command=self.change_language,
            width=140,
            height=36,
            fg_color="#0F766E",
            button_color="#10B981",
            button_hover_color="#34D399",
        )
        self.language_menu.grid(row=0, column=1, padx=22, pady=22, sticky="ne")

        controls = ctk.CTkFrame(self, corner_radius=24, fg_color="#111827", border_width=1, border_color="#1F2937")
        controls.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        controls.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.mode_label = ctk.CTkLabel(controls, font=ctk.CTkFont(size=14, weight="bold"))
        self.mode_label.grid(row=0, column=0, padx=18, pady=(18, 6), sticky="w")
        self.mode_menu = ctk.CTkSegmentedButton(
            controls,
            variable=self.mode_var,
            values=[self.t("simulation"), self.t("real")],
            selected_color="#10B981",
            selected_hover_color="#059669",
            unselected_color="#1F2937",
            unselected_hover_color="#374151",
            height=42,
        )
        self.mode_menu.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="ew")

        self.start_button = ctk.CTkButton(controls, height=46, corner_radius=14, fg_color="#10B981", hover_color="#059669", command=self.start_system)
        self.start_button.grid(row=1, column=1, padx=8, pady=(0, 18), sticky="ew")
        self.open_button = ctk.CTkButton(controls, height=46, corner_radius=14, fg_color="#2563EB", hover_color="#1D4ED8", command=self.open_web)
        self.open_button.grid(row=1, column=2, padx=8, pady=(0, 18), sticky="ew")
        self.stop_button = ctk.CTkButton(controls, height=46, corner_radius=14, fg_color="#B45309", hover_color="#D97706", command=self.stop_bot)
        self.stop_button.grid(row=1, column=3, padx=(8, 18), pady=(0, 18), sticky="ew")
        self.stop_all_button = ctk.CTkButton(
            controls,
            height=40,
            corner_radius=14,
            fg_color="#7F1D1D",
            hover_color="#991B1B",
            command=self.stop_all,
        )
        self.stop_all_button.grid(row=2, column=1, columnspan=3, padx=(8, 18), pady=(0, 18), sticky="ew")
        self.api_button = ctk.CTkButton(
            controls,
            height=40,
            corner_radius=14,
            fg_color="#374151",
            hover_color="#4B5563",
            command=self.open_api_config,
        )
        self.api_button.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="ew")

        self.profile_label = ctk.CTkLabel(controls, font=ctk.CTkFont(size=14, weight="bold"))
        self.profile_label.grid(row=3, column=0, padx=18, pady=(0, 6), sticky="w")
        self.profile_name_entry = ctk.CTkEntry(controls, textvariable=self.profile_name_var, height=34)
        self.profile_name_entry.grid(row=3, column=1, columnspan=3, padx=(8, 18), pady=(0, 6), sticky="ew")
        self.profile_menu = ctk.CTkOptionMenu(
            controls,
            variable=self.profile_var,
            values=["default · 60.00 USDT"],
            command=self.change_simulation_profile,
            fg_color="#1F2937",
            button_color="#374151",
            button_hover_color="#4B5563",
            height=38,
        )
        self.profile_menu.grid(row=4, column=0, padx=18, pady=(0, 18), sticky="ew")
        self.profile_capital_entry = ctk.CTkEntry(controls, textvariable=self.profile_capital_var, height=38)
        self.profile_capital_entry.grid(row=4, column=1, padx=8, pady=(0, 18), sticky="ew")
        self.create_profile_button = ctk.CTkButton(
            controls,
            height=38,
            corner_radius=14,
            fg_color="#0F766E",
            hover_color="#0D9488",
            command=self.create_simulation_profile,
        )
        self.create_profile_button.grid(row=4, column=2, padx=8, pady=(0, 18), sticky="ew")
        self.reset_profile_button = ctk.CTkButton(
            controls,
            height=38,
            corner_radius=14,
            fg_color="#7C2D12",
            hover_color="#9A3412",
            command=self.reset_simulation_profile,
        )
        self.reset_profile_button.grid(row=4, column=3, padx=(8, 18), pady=(0, 18), sticky="ew")

        status = ctk.CTkFrame(self, corner_radius=24, fg_color="#0B1220", border_width=1, border_color="#1F2937")
        status.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        status.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)
        self.status_title = ctk.CTkLabel(status, font=ctk.CTkFont(size=15, weight="bold"))
        self.status_title.grid(row=0, column=0, padx=18, pady=(16, 0), sticky="w")
        self.web_card = self._metric(status, 0, self.t("web"), self.web_state_var)
        self.daemon_card = self._metric(status, 1, self.t("daemon"), self.daemon_state_var)
        self.trading_card = self._metric(status, 2, self.t("trading"), self.trading_state_var)
        self.mode_card = self._metric(status, 3, self.t("mode_label"), self.mode_state_var)
        self.port_card = self._metric(status, 4, self.t("port"), self.port_state_var)
        self.api_card = self._metric(status, 5, self.t("api_status"), self.api_state_var)

        logs = ctk.CTkFrame(self, corner_radius=24, fg_color="#0B1220", border_width=1, border_color="#1F2937")
        logs.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")
        logs.grid_columnconfigure(0, weight=1)
        logs.grid_rowconfigure(2, weight=1)
        self.logs_label = ctk.CTkLabel(logs, font=ctk.CTkFont(size=15, weight="bold"))
        self.logs_label.grid(row=0, column=0, padx=18, pady=(16, 6), sticky="w")
        self.logs_hint_label = ctk.CTkLabel(logs, text_color="#94A3B8", font=ctk.CTkFont(size=12))
        self.logs_hint_label.grid(row=1, column=0, padx=18, pady=(0, 8), sticky="w")
        self.log_box = ctk.CTkTextbox(
            logs,
            wrap="word",
            fg_color="#020617",
            text_color="#D1FAE5",
            border_width=1,
            border_color="#1F2937",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log_box.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.log_box.configure(state="disabled")

        self.footer = ctk.CTkLabel(self, textvariable=self.status_var, text_color="#9CA3AF")
        self.footer.grid(row=4, column=0, padx=24, pady=(0, 14), sticky="w")

    def _metric(self, parent, column, title, variable):
        frame = ctk.CTkFrame(parent, fg_color="#111827", corner_radius=18, border_width=1, border_color="#1F2937")
        frame.grid(row=1, column=column, padx=8, pady=16, sticky="ew")
        title_label = ctk.CTkLabel(frame, text=title, text_color="#9CA3AF", font=ctk.CTkFont(size=12))
        title_label.pack(anchor="w", padx=14, pady=(12, 0))
        value_label = ctk.CTkLabel(frame, textvariable=variable, font=ctk.CTkFont(size=16, weight="bold"))
        value_label.pack(anchor="w", padx=14, pady=(2, 14))
        return {"frame": frame, "title": title_label, "value": value_label}

    def _load_logo_image(self):
        if LOGO_PATH.exists():
            return ctk.CTkImage(Image.open(LOGO_PATH), size=(72, 72))
        fallback = Image.new("RGBA", (72, 72), "#0B1220")
        return ctk.CTkImage(fallback, size=(72, 72))

    def refresh_texts(self):
        current_is_sim = self.mode_var.get() in {TEXT["es"]["simulation"], TEXT["en"]["simulation"]}
        self.title_label.configure(text=self.t("title"))
        self.subtitle_label.configure(text=self.t("subtitle"))
        self.mission_label.configure(text=self.t("mission"))
        self.mode_label.configure(text=self.t("mode"))
        self.profile_label.configure(text=self.t("simulation_profile"))
        self.profile_name_entry.configure(placeholder_text=self.t("profile_name"))
        self.profile_capital_entry.configure(placeholder_text=self.t("initial_capital"))
        self.create_profile_button.configure(text=self.t("new_profile"))
        self.reset_profile_button.configure(text=self.t("reset_profile"))
        self.start_button.configure(text=self.t("start_system"))
        self.open_button.configure(text=self.t("open_web"))
        self.stop_button.configure(text=self.t("stop_bot"))
        self.stop_all_button.configure(text=self.t("stop_all"))
        self.api_button.configure(text=self.t("configure_apis"))
        self.status_title.configure(text=self.t("status"))
        self.logs_label.configure(text=self.t("logs"))
        self.logs_hint_label.configure(text=self.t("logs_hint"))
        self.web_card["title"].configure(text=self.t("web"))
        self.daemon_card["title"].configure(text=self.t("daemon"))
        self.trading_card["title"].configure(text=self.t("trading"))
        self.mode_card["title"].configure(text=self.t("mode_label"))
        self.port_card["title"].configure(text=self.t("port"))
        self.api_card["title"].configure(text=self.t("api_status"))
        self.mode_menu.configure(values=[self.t("simulation"), self.t("real")])
        self.mode_var.set(self.t("simulation") if current_is_sim else self.t("real"))
        self.refresh_profile_menu()
        self.status_var.set(self.t("ready"))
        self.refresh_status()

    def change_language(self, value):
        self.lang = "en" if value == "English" else "es"
        self._set_system_status("language", self.lang)
        self.refresh_texts()

    def _profile_display(self, profile):
        return f"{profile.get('name', profile.get('id'))} · {profile.get('initial_capital', 0):.2f} USDT"

    def refresh_profile_menu(self):
        try:
            profiles = list_profiles()
            active = get_active_profile()
        except Exception:
            profiles = []
            active = None
        self._profile_display_to_id = {self._profile_display(profile): profile["id"] for profile in profiles}
        values = list(self._profile_display_to_id.keys()) or ["default · 60.00 USDT"]
        self.profile_menu.configure(values=values)
        selected = None
        if active:
            for display, profile_id in self._profile_display_to_id.items():
                if profile_id == active.get("id"):
                    selected = display
                    self.profile_capital_var.set(str(active.get("initial_capital", 60)))
                    break
        self.profile_var.set(selected or values[0])

    def change_simulation_profile(self, display_value):
        profile_id = self._profile_display_to_id.get(display_value)
        if not profile_id:
            return
        try:
            profile = set_active_profile(profile_id)
            self.profile_capital_var.set(str(profile.get("initial_capital", 60)))
            self._apply_mode(True, profile_id=profile_id)
            self._restart_runtime_after_profile_change()
            self.refresh_status()
        except Exception as exc:
            self.status_var.set(f"{self.t('db_error')}: {exc}")

    def create_simulation_profile(self):
        try:
            capital = float(str(self.profile_capital_var.get() or "60").replace(",", "."))
        except ValueError:
            capital = 60.0
        name = self.profile_name_var.get().strip() or f"{self.t('profile_name')} {time.strftime('%Y%m%d-%H%M')}"
        try:
            profile = create_profile(name, capital, activate=True)
            self.refresh_profile_menu()
            for display, profile_id in self._profile_display_to_id.items():
                if profile_id == profile["id"]:
                    self.profile_var.set(display)
                    break
            self._apply_mode(True, profile_id=profile["id"])
            self._restart_runtime_after_profile_change()
            self.status_var.set(self.t("profile_created"))
        except Exception as exc:
            self.status_var.set(f"{self.t('db_error')}: {exc}")

    def reset_simulation_profile(self):
        display = self.profile_var.get()
        profile_id = self._profile_display_to_id.get(display)
        if not profile_id:
            return
        if not messagebox.askyesno(self.t("reset_profile"), self.t("delete_confirm")):
            return
        try:
            reset_profile(profile_id)
            self._apply_mode(True, profile_id=profile_id)
            self._restart_runtime_after_profile_change()
            self.refresh_profile_menu()
            self.status_var.set(self.t("profile_reset"))
        except Exception as exc:
            self.status_var.set(f"{self.t('db_error')}: {exc}")

    def _restart_runtime_after_profile_change(self):
        # Streamlit keeps session_state in memory, so changing profiles while the web
        # is already running requires a restart to avoid showing the previous DB.
        self._set_system_status("is_running", "false")
        self._terminate_process("daemon")
        self._terminate_process("streamlit")

    def _prompt_api_config_if_needed(self):
        if self._api_prompt_shown:
            return
        self._api_prompt_shown = True
        if self._missing_startup_keys():
            messagebox.showwarning(self.t("setup_title"), self.t("setup_required"))
            self.open_api_config()

    def open_api_config(self):
        if self._api_window is not None and self._api_window.winfo_exists():
            self._api_window.focus()
            return

        env_data = self._load_env_values()
        self._api_entries = {}
        win = ctk.CTkToplevel(self)
        self._api_window = win
        win.title(self.t("setup_title"))
        win.geometry("760x720")
        win.minsize(700, 620)
        win.transient(self)
        win.grab_set()
        win.grid_columnconfigure(0, weight=1)
        win.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(win, corner_radius=18, fg_color="#0B1220", border_width=1, border_color="#1F2937")
        header.grid(row=0, column=0, padx=18, pady=(18, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text=self.t("setup_title"), font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, padx=18, pady=(16, 4), sticky="w")
        ctk.CTkLabel(header, text=self.t("setup_help"), text_color="#94A3B8", wraplength=680).grid(row=1, column=0, padx=18, pady=(0, 16), sticky="w")

        body = ctk.CTkScrollableFrame(win, corner_radius=18, fg_color="#111827", border_width=1, border_color="#1F2937")
        body.grid(row=1, column=0, padx=18, pady=10, sticky="nsew")
        body.grid_columnconfigure(1, weight=1)

        row = 0
        current_section = None
        for section_key, key, required in API_FIELDS:
            if section_key != current_section:
                current_section = section_key
                ctk.CTkLabel(body, text=self.t(section_key), font=ctk.CTkFont(size=17, weight="bold")).grid(row=row, column=0, columnspan=3, padx=14, pady=(18, 8), sticky="w")
                row += 1

            value = env_data.get(key, "")
            state = self.t("configured") if value else self.t("missing")
            requirement = self.t("required") if required else self.t("optional")
            label = ctk.CTkLabel(body, text=f"{key}\n{requirement} · {state}", text_color="#D1D5DB", justify="left")
            label.grid(row=row, column=0, padx=14, pady=8, sticky="w")
            entry = ctk.CTkEntry(body, show="*", width=420)
            entry.insert(0, value)
            entry.grid(row=row, column=1, padx=10, pady=8, sticky="ew")
            self._api_entries[key] = entry
            row += 1

        footer = ctk.CTkFrame(win, fg_color="transparent")
        footer.grid(row=2, column=0, padx=18, pady=(8, 18), sticky="ew")
        footer.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(footer, text=self.t("save_apis"), height=42, fg_color="#10B981", hover_color="#059669", command=self._save_api_config).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ctk.CTkButton(footer, text=self.t("delete_local_keys"), height=42, fg_color="#7F1D1D", hover_color="#991B1B", command=self._delete_local_keys).grid(row=0, column=1, padx=8, sticky="ew")
        ctk.CTkButton(footer, text=self.t("cancel"), height=42, fg_color="#374151", hover_color="#4B5563", command=win.destroy).grid(row=0, column=2, padx=(8, 0), sticky="ew")

    def start_system(self):
        self.set_status("starting")
        if not self._validate_project():
            self.set_status("project_missing")
            return

        if self._missing_startup_keys():
            messagebox.showwarning(self.t("setup_title"), self.t("setup_required"))
            self.open_api_config()
            self.set_status("api_missing")
            return

        is_sim = self.mode_var.get() == self.t("simulation")
        if not is_sim:
            if not messagebox.askyesno(self.t("real_title"), self.t("real_warning")):
                self.set_status("ready")
                return
            if not self._has_real_keys():
                messagebox.showwarning(self.t("missing_keys_title"), self.t("missing_keys"))
                self.set_status("missing_keys")
                return

        self._apply_mode(is_sim)
        self.set_status("mode_saved")
        threading.Thread(target=self._start_system_worker, daemon=True).start()

    def _start_system_worker(self):
        self._prevent_sleep()
        self._start_streamlit()
        self._start_daemon()
        self._open_web_when_ready()
        self.refresh_status()

    def _start_streamlit(self):
        if self.streamlit_process and self.streamlit_process.poll() is None:
            self.set_status("already_running")
            return
        if self._is_port_open(PORT):
            self.set_status("already_running")
            return
        python = self._python_executable()
        if not python:
            self.set_status("python_missing")
            return
        LOG_DIR.mkdir(exist_ok=True)
        self._streamlit_log_handle = open(LOG_DIR / "streamlit.log", "a", encoding="utf-8", buffering=1)
        cmd = [
            python,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "app.py"),
            "--server.port",
            str(PORT),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ]
        self.streamlit_process = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=self._streamlit_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=self._creation_flags(),
            startupinfo=self._startup_info(),
            env=self._child_env(),
        )
        self.set_status("streamlit_started")

    def _start_daemon(self):
        if self.daemon_process and self.daemon_process.poll() is None:
            self.set_status("already_running")
            return
        python = self._python_executable()
        if not python:
            self.set_status("python_missing")
            return
        LOG_DIR.mkdir(exist_ok=True)
        self._daemon_log_handle = open(LOG_DIR / "daemon.log", "w", encoding="utf-8", buffering=1)
        self._daemon_log_handle.write(
            f"[LAUNCHER] Nueva sesión daemon · {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        if self._current_simulation_mode():
            try:
                profile = get_active_profile()
                self._daemon_log_handle.write(
                    f"[LAUNCHER] Perfil simulación activo · {profile.get('name')} "
                    f"({profile.get('id')}) · capital {float(profile.get('initial_capital', 0)):.2f} USDT\n"
                )
            except Exception:
                pass
        self._set_system_status("is_running", "true")
        self.daemon_process = subprocess.Popen(
            [python, "-u", str(ROOT / "bot_daemon.py")],
            cwd=str(ROOT),
            stdout=self._daemon_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=self._creation_flags(),
            startupinfo=self._startup_info(),
            env=self._child_env(),
        )
        self.set_status("daemon_started")

    def open_web(self):
        self.set_status("opening_web")
        webbrowser.open(f"http://localhost:{PORT}")

    def _open_web_when_ready(self, max_wait=8):
        for remaining in range(max_wait, 0, -1):
            if self._is_port_open(PORT):
                self.open_web()
                return
            self.status_var.set(f"{self.t('waiting_web')}... {remaining}s")
            time.sleep(1)
        self.open_web()

    def stop_bot(self):
        self.set_status("stopping_bot")
        self._set_system_status("is_running", "false")
        self._terminate_process("daemon")
        self.refresh_status()

    def stop_all(self):
        self.set_status("stopping_all")
        self._set_system_status("is_running", "false")
        self._terminate_process("daemon")
        self._terminate_process("streamlit")
        self._allow_sleep()
        self.refresh_status()

    def on_close(self):
        has_children = any(
            process is not None and process.poll() is None
            for process in (self.daemon_process, self.streamlit_process)
        )
        if has_children:
            if not messagebox.askyesno(self.t("close_title"), self.t("close_warning")):
                return
            self.stop_all()
            time.sleep(0.4)
        else:
            self._allow_sleep()
        self.destroy()

    def refresh_status_loop(self):
        self.refresh_status()
        self.after(1500, self.refresh_status_loop)

    def refresh_status(self):
        web_active = self._is_port_open(PORT)
        daemon_active, daemon_label = self._daemon_health()
        trading_active = self._system_flag("is_running")
        self.web_state_var.set(self.t("active") if web_active else self.t("inactive"))
        self.daemon_state_var.set(daemon_label)
        self.trading_state_var.set(self.t("active") if trading_active else self.t("paused"))
        self.mode_state_var.set(self.t("simulation") if self._current_simulation_mode() else self.t("real"))
        self.port_state_var.set(str(PORT))
        api_ready = not self._missing_startup_keys()
        self.api_state_var.set(self.t("api_ready") if api_ready else self.t("api_missing"))
        self._paint_metric(self.web_card, web_active)
        self._paint_metric(self.daemon_card, daemon_active)
        self._paint_metric(self.trading_card, trading_active)
        self._paint_metric(self.api_card, api_ready)
        self._refresh_logs()

    def _refresh_logs(self):
        lines = []
        daemon_log = LOG_DIR / "daemon.log"
        if daemon_log.exists():
            try:
                lines = daemon_log.read_text(encoding="utf-8", errors="replace").splitlines()[-220:]
            except OSError as exc:
                lines = [f"{self.t('db_error')}: {exc}"]

        # If this launcher has not started the daemon yet, fall back to persisted DB events.
        # External daemons cannot have their stdout captured retroactively.
        if not lines:
            try:
                db_path = self._current_db_path()
                if db_path.exists():
                    with sqlite3.connect(db_path, timeout=2) as conn:
                        rows = conn.execute("SELECT message FROM logs ORDER BY id DESC LIMIT 80").fetchall()
                        lines = [row[0] for row in reversed(rows)]
            except Exception as exc:
                lines = [f"{self.t('db_error')}: {exc}"]

        if not lines:
            streamlit_log = LOG_DIR / "streamlit.log"
            if streamlit_log.exists():
                try:
                    lines = streamlit_log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
                except OSError:
                    pass

        text = "\n".join(lines) if lines else self.t("ready")
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.insert("1.0", text)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _paint_metric(self, card, active):
        card["value"].configure(text_color="#22C55E" if active else "#EF4444")

    def set_status(self, key):
        self.status_var.set(self.t(key))

    def _apply_mode(self, is_sim, profile_id=None):
        if is_sim:
            profile_id = profile_id or self._profile_display_to_id.get(self.profile_var.get())
            if profile_id:
                set_active_profile(profile_id)
        self._save_user_setting("MODO_SIMULACION", bool(is_sim))
        self._set_system_status("simulacion", "true" if is_sim else "false")

    def _save_user_setting(self, key, value):
        data = {}
        if SETTINGS_PATH.exists():
            try:
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data[key] = value
        SETTINGS_PATH.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")

    def _load_env_values(self):
        raw = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
        return {key: str(raw.get(key) or "") for _, key, _ in API_FIELDS}

    def _save_api_config(self):
        values = {key: entry.get().strip() for key, entry in self._api_entries.items()}
        self._write_env(values)
        self.refresh_status()
        messagebox.showinfo(self.t("setup_title"), self.t("env_saved"))
        if self._api_window is not None and self._api_window.winfo_exists():
            self._api_window.destroy()

    def _delete_local_keys(self):
        if not messagebox.askyesno(self.t("setup_title"), self.t("delete_confirm")):
            return
        self._write_env({key: "" for _, key, _ in API_FIELDS})
        for entry in self._api_entries.values():
            entry.delete(0, "end")
        self.refresh_status()

    def _write_env(self, values):
        if ENV_PATH.exists():
            backup = ENV_PATH.with_name(f".env.backup-{time.strftime('%Y%m%d-%H%M%S')}")
            try:
                backup.write_text(ENV_PATH.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            except OSError:
                pass

        lines = [
            "# --- INVERSORIA: CONFIGURACION LOCAL ---",
            "# Archivo generado por InversorIA Launcher. No lo compartas ni lo subas a Git.",
            "",
            "# CRYPTO.COM EXCHANGE",
            f"CRYPTO_API_KEY={self._env_escape(values.get('CRYPTO_API_KEY', ''))}",
            f"CRYPTO_API_SECRET={self._env_escape(values.get('CRYPTO_API_SECRET', ''))}",
            "",
            "# INTELIGENCIA ARTIFICIAL",
            f"GOOGLE_API_KEY={self._env_escape(values.get('GOOGLE_API_KEY', ''))}",
            f"GROQ_API_KEY={self._env_escape(values.get('GROQ_API_KEY', ''))}",
            f"SAMBANOVA_API_KEY={self._env_escape(values.get('SAMBANOVA_API_KEY', ''))}",
            "",
            "# DATOS Y NOTICIAS",
            f"ALPHA_VANTAGE_API_KEY={self._env_escape(values.get('ALPHA_VANTAGE_API_KEY', ''))}",
            f"COINDESK_API_KEY={self._env_escape(values.get('COINDESK_API_KEY', ''))}",
            "",
        ]
        ENV_PATH.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _env_escape(value):
        value = str(value or "").strip()
        if not value:
            return ""
        if any(ch.isspace() for ch in value) or any(ch in value for ch in ['"', "'", "#"]):
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return value

    def _missing_startup_keys(self):
        env = self._load_env_values()
        missing_exchange = not env.get("CRYPTO_API_KEY") or not env.get("CRYPTO_API_SECRET")
        missing_ai = not any(env.get(key) for key in AI_KEYS)
        return missing_exchange or missing_ai

    def _set_system_status(self, key, value):
        try:
            with sqlite3.connect(self._current_db_path(), timeout=5) as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS system_status (key TEXT PRIMARY KEY, value TEXT)"
                )
                conn.execute(
                    "INSERT OR REPLACE INTO system_status (key, value) VALUES (?, ?)",
                    (key, str(value)),
                )
                conn.commit()
        except Exception as exc:
            self.status_var.set(f"{self.t('db_error')}: {exc}")

    def _get_system_status(self, key, default=None):
        try:
            db_path = self._current_db_path()
            if db_path.exists():
                with sqlite3.connect(db_path, timeout=2) as conn:
                    row = conn.execute("SELECT value FROM system_status WHERE key = ?", (key,)).fetchone()
                    if row:
                        return row[0]
        except Exception:
            pass
        return default

    def _current_db_path(self):
        try:
            return Path(get_database_path_for_current_mode())
        except Exception:
            return DB_PATH

    def _system_flag(self, key):
        return str(self._get_system_status(key, "false")).lower() == "true"

    def _daemon_health(self):
        process_alive = self.daemon_process is not None and self.daemon_process.poll() is None
        state = None
        age = None
        try:
            raw = self._get_system_status("daemon_diagnostics", "{}") or "{}"
            diag = json.loads(raw)
            state = diag.get("state")
            state_ts = float(diag.get("state_ts") or 0)
            if state_ts > 0:
                age = max(0, int(time.time() - state_ts))
        except Exception:
            pass

        heartbeat_alive = age is not None and age <= 180
        active = process_alive or heartbeat_alive
        if active and state:
            suffix = f"{state} · {age}s" if age is not None else state
            return True, f"{self.t('active')} · {suffix}"
        if active:
            return True, self.t("active")
        if self._system_flag("is_running"):
            return False, self.t("armed")
        return False, self.t("inactive")

    def _current_simulation_mode(self):
        if SETTINGS_PATH.exists():
            try:
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if "MODO_SIMULACION" in data:
                    return bool(data["MODO_SIMULACION"])
            except Exception:
                pass
        try:
            with sqlite3.connect(DB_PATH, timeout=2) as conn:
                row = conn.execute("SELECT value FROM system_status WHERE key = 'simulacion'").fetchone()
                if row:
                    return str(row[0]).lower() == "true"
        except Exception:
            pass
        return True

    def _load_language(self):
        try:
            db_path = self._current_db_path()
            if db_path.exists():
                with sqlite3.connect(db_path, timeout=2) as conn:
                    row = conn.execute("SELECT value FROM system_status WHERE key = 'language'").fetchone()
                    if row and str(row[0]).lower() in {"es", "en"}:
                        return str(row[0]).lower()
        except Exception:
            pass
        return "es"

    def _has_real_keys(self):
        env = dotenv_values(ENV_PATH)
        return bool(env.get("CRYPTO_API_KEY")) and bool(env.get("CRYPTO_API_SECRET"))

    def _validate_project(self):
        return (ROOT / "app.py").exists() and (ROOT / "bot_daemon.py").exists()

    def _python_executable(self):
        candidates = [
            ROOT / "venv" / "Scripts" / "pythonw.exe",
            ROOT / ".venv" / "Scripts" / "pythonw.exe",
            ROOT / "env" / "Scripts" / "pythonw.exe",
            ROOT / "venv" / "Scripts" / "python.exe",
            ROOT / ".venv" / "Scripts" / "python.exe",
            ROOT / "env" / "Scripts" / "python.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        if not getattr(sys, "frozen", False):
            return sys.executable.replace("python.exe", "pythonw.exe") if os.name == "nt" and sys.executable.endswith("python.exe") else sys.executable
        return "python"

    def _terminate_process(self, name):
        process = self.daemon_process if name == "daemon" else self.streamlit_process
        if process and process.poll() is None:
            self._terminate_process_tree(process)
        if name == "daemon":
            self.daemon_process = None
            self._close_handle("_daemon_log_handle")
        else:
            self.streamlit_process = None
            self._close_handle("_streamlit_log_handle")
        self.set_status("stopped")

    def _close_handle(self, attr):
        handle = getattr(self, attr, None)
        if handle:
            try:
                handle.close()
            except OSError:
                pass
        setattr(self, attr, None)

    @staticmethod
    def _is_port_open(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            return sock.connect_ex(("127.0.0.1", int(port))) == 0

    @staticmethod
    def _creation_flags():
        if os.name == "nt":
            return subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        return 0

    @staticmethod
    def _startup_info():
        if os.name != "nt":
            return None
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        return startupinfo

    @staticmethod
    def _child_env():
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _terminate_process_tree(self, process):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=self._creation_flags(),
                startupinfo=self._startup_info(),
            )
            return
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()

    def _prevent_sleep(self):
        if os.name != "nt" or self._sleep_blocked:
            return
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
            self._sleep_blocked = True
        except Exception:
            pass

    def _allow_sleep(self):
        if os.name != "nt" or not self._sleep_blocked:
            return
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass
        self._sleep_blocked = False


if __name__ == "__main__":
    app = InversoriaLauncher()
    app.mainloop()
