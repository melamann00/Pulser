from datetime import datetime
import customtkinter as ctk
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from data_store import Reading, add_reading, delete_reading, load_readings

DEFAULT_DARK_MODE = True  # flip to False if you'd rather the app open in light mode

ctk.set_appearance_mode("dark" if DEFAULT_DARK_MODE else "light")
ctk.set_default_color_theme("green")

HEART_COLOR = "#e63946"
PULSE_COLOR = "#457b9d"
ROW_COLOR = ("#f2f2f2", "#2b2b2b")
ROW_HOVER = ("#e3e3e3", "#3a3a3a")
MUTED_TEXT = ("#8a8a8a", "#9a9a9a")

ZONE_GOOD = "#43a047"# green - normal/good
ZONE_MID = "#fb8c00"# orange - borderline
ZONE_BAD = "#e53935"# red - too low / too high

ZONE_BOUNDS = [
    (0, 50, ZONE_BAD),# too low
    (50, 60, ZONE_MID),# borderline low
    (60, 100, ZONE_GOOD),# normal resting range
    (100, 120, ZONE_MID),# borderline high
    (120, 300, ZONE_BAD),# too high
]

DEFAULT_Y_MIN = 30 # visible axis floor when nothing pushes it wider
DEFAULT_Y_MAX = 150 # visible axis ceiling when nothing pushes it wider
Y_PADDING = 10 # extra bpm of headroom shown above/below actual readings

class ChartCard(ctk.CTkFrame):
    def __init__(self, master, title: str, line_color: str, unit: str = "bpm",
                 is_dark: bool = DEFAULT_DARK_MODE, **kwargs):
        super().__init__(master, corner_radius=14, **kwargs)
        self.line_color = line_color
        self.unit = unit
        self.is_dark = is_dark
        self._timestamps: list = []
        self._values: list = []
        ctk.CTkLabel(
            self, text=title, font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
        ).pack(fill="x", padx=18, pady=(14, 4))
        self.figure = Figure(figsize=(6, 3), dpi=100)
        self.axis = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=14, pady=(0, 16))
        self.canvas.get_tk_widget().configure(highlightthickness=0, bd=0)
        self.canvas.get_tk_widget().bind("<Configure>", lambda e: self._redraw(), add="+")
        self._redraw()

    def _palette(self) -> dict:
        if self.is_dark:
            return {
                "bg": "#242424", "text": "#dddddd", "grid": "#3a3a3a",
                "spine": "#4a4a4a", "muted": "#8a8a8a", "zone_alpha": 0.30,
            }
        return {
            "bg": "#ffffff", "text": "#4a4a4a", "grid": "#e8e8e8",
            "spine": "#dddddd", "muted": "#aaaaaa", "zone_alpha": 0.22,
        }

    def set_dark(self, is_dark: bool) -> None:
        self.is_dark = is_dark
        self._redraw()

    def update_data(self, timestamps: list, values: list) -> None:
        self._timestamps = timestamps
        self._values = values
        self._redraw()

    def _compute_ylim(self) -> tuple:
        if self._values:
            lo = min(DEFAULT_Y_MIN, min(self._values) - Y_PADDING)
            hi = max(DEFAULT_Y_MAX, max(self._values) + Y_PADDING)
        else:
            lo, hi = DEFAULT_Y_MIN, DEFAULT_Y_MAX
        return max(0, lo), hi

    def _draw_zones(self, ylim: tuple, alpha: float) -> None:
        y0, y1 = ylim
        for band_lo, band_hi, color in ZONE_BOUNDS:
            lo, hi = max(band_lo, y0), min(band_hi, y1)
            if hi <= lo:
                continue
            self.axis.axhspan(lo, hi, color=color, alpha=alpha, linewidth=0, zorder=0)

    def _redraw(self) -> None:
        c = self._palette()
        self.figure.patch.set_facecolor(c["bg"])
        self.canvas.get_tk_widget().configure(bg=c["bg"])
        self.axis.clear()
        self.axis.set_facecolor(c["bg"])

        if not self._timestamps:
            self.axis.text(
                0.5, 0.5, "No readings yet",
                ha="center", va="center", color=c["muted"], fontsize=11,
                transform=self.axis.transAxes, zorder=5,
            )
            self.axis.set_xticks([])
            self.axis.set_yticks([])
            for spine in self.axis.spines.values():
                spine.set_visible(False)
        else:
            self.axis.plot(
                self._timestamps, self._values,
                color=self.line_color, linewidth=2.2,
                marker="o", markersize=4.5,
                markerfacecolor=c["bg"], markeredgecolor=self.line_color,
                markeredgewidth=1.4, zorder=4,
            )
            self.axis.set_ylabel(self.unit, fontsize=9, color=c["text"])
            self.axis.tick_params(axis="both", labelsize=8, colors=c["text"])
            self.axis.grid(True, axis="y", linestyle="--", linewidth=0.6, color=c["grid"], zorder=1)
            for side in ("top", "right"):
                self.axis.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                self.axis.spines[side].set_color(c["spine"])
            self.axis.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
            self.figure.autofmt_xdate(rotation=0, ha="center")

        ylim = self._compute_ylim()
        self.axis.set_ylim(*ylim)
        self._draw_zones(ylim, c["zone_alpha"])

        try:
            self.figure.tight_layout()
        except Exception:
            pass
        self.canvas.draw_idle()

class HealthTrackerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Health Tracker")
        self.geometry("1150x760")
        self.minsize(940, 640)

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_charts()
        self.refresh()
        
    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=320, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nswe")
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_columnconfigure(1, weight=0)
        sidebar.grid_rowconfigure(4, weight=1)
        sidebar.grid_propagate(False)
        
        ctk.CTkLabel(
            sidebar, text="Health Tracker", font=ctk.CTkFont(size=21, weight="bold"),
        ).grid(row=0, column=0, padx=(20, 0), pady=(22, 0), sticky="w")

        self.appearance_switch = ctk.CTkSwitch(
            sidebar, text="Dark", font=ctk.CTkFont(size=12), command=self._toggle_appearance,
        )
        self.appearance_switch.grid(row=0, column=1, padx=(0, 16), pady=(22, 0), sticky="e")
        if DEFAULT_DARK_MODE:
            self.appearance_switch.select()

        ctk.CTkLabel(
            sidebar, text="Log a new reading", font=ctk.CTkFont(size=13),
            text_color=MUTED_TEXT,
        ).grid(row=1, column=0, columnspan=2, padx=20, pady=(2, 14), sticky="w")

        form = ctk.CTkFrame(sidebar, fg_color="transparent")
        form.grid(row=2, column=0, columnspan=2, padx=20, sticky="we")
        form.grid_columnconfigure((0, 1), weight=1)
        now = datetime.now()
        ctk.CTkLabel(form, text="Date", font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, sticky="w", pady=(0, 2)
        )
        ctk.CTkLabel(form, text="Time", font=ctk.CTkFont(size=12)).grid(
            row=0, column=1, sticky="w", pady=(0, 2)
        )
        self.date_entry = ctk.CTkEntry(form, placeholder_text="YYYY-MM-DD")
        self.date_entry.insert(0, now.strftime("%Y-%m-%d"))
        self.date_entry.grid(row=1, column=0, sticky="we", padx=(0, 6), pady=(0, 12))

        time_row = ctk.CTkFrame(form, fg_color="transparent")
        time_row.grid(row=1, column=1, sticky="we", pady=(0, 12))
        time_row.grid_columnconfigure(0, weight=1)

        self.time_entry = ctk.CTkEntry(time_row, placeholder_text="HH:MM")
        self.time_entry.insert(0, now.strftime("%H:%M"))
        self.time_entry.grid(row=0, column=0, sticky="we")

        ctk.CTkButton(
            time_row, text="Now", width=48, command=self.on_use_now,
        ).grid(row=0, column=1, padx=(6, 0))

        ctk.CTkLabel(form, text="Heart rate (bpm)", font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        self.hr_entry = ctk.CTkEntry(form, placeholder_text="e.g. 72")
        self.hr_entry.grid(row=3, column=0, columnspan=2, sticky="we", pady=(0, 12))

        ctk.CTkLabel(form, text="Pulse (bpm)", font=ctk.CTkFont(size=12)).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        self.pulse_entry = ctk.CTkEntry(form, placeholder_text="e.g. 70")
        self.pulse_entry.grid(row=5, column=0, columnspan=2, sticky="we", pady=(0, 12))

        self.add_button = ctk.CTkButton(form, text="Add reading", command=self.on_add)
        self.add_button.grid(row=6, column=0, columnspan=2, sticky="we")

        self.status_label = ctk.CTkLabel(
            form, text="", font=ctk.CTkFont(size=12), text_color="#c62828", anchor="w",
        )
        self.status_label.grid(row=7, column=0, columnspan=2, sticky="we", pady=(6, 0))

        ctk.CTkLabel(
            sidebar, text="Recent readings", font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=3, column=0, columnspan=2, padx=20, pady=(14, 6), sticky="w")

        self.history_frame = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self.history_frame.grid(row=4, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="nswe")

    def _build_charts(self) -> None:
        charts = ctk.CTkFrame(self, fg_color="transparent")
        charts.grid(row=0, column=1, sticky="nswe", padx=20, pady=20)
        charts.grid_rowconfigure((0, 1), weight=1)
        charts.grid_columnconfigure(0, weight=1)

        self.hr_card = ChartCard(charts, "Heart rate over time", HEART_COLOR)
        self.hr_card.grid(row=0, column=0, sticky="nswe", pady=(0, 10))

        self.pulse_card = ChartCard(charts, "Pulse over time", PULSE_COLOR)
        self.pulse_card.grid(row=1, column=0, sticky="nswe", pady=(10, 0))
        
    def _toggle_appearance(self) -> None:
        is_dark = bool(self.appearance_switch.get())
        ctk.set_appearance_mode("dark" if is_dark else "light")
        self.hr_card.set_dark(is_dark)
        self.pulse_card.set_dark(is_dark)

    def on_use_now(self) -> None:
        now = datetime.now()
        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, now.strftime("%Y-%m-%d"))
        self.time_entry.delete(0, "end")
        self.time_entry.insert(0, now.strftime("%H:%M"))

    def on_add(self) -> None:
        date_str = self.date_entry.get().strip()
        time_str = self.time_entry.get().strip()
        hr_str = self.hr_entry.get().strip()
        pulse_str = self.pulse_entry.get().strip()

        try:
            timestamp = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            self._set_status("Enter a valid date (YYYY-MM-DD) and time (HH:MM).")
            return

        try:
            heart_rate = int(hr_str)
            pulse = int(pulse_str)
        except ValueError:
            self._set_status("Heart rate and pulse must be whole numbers.")
            return

        if not (20 <= heart_rate <= 250) or not (20 <= pulse <= 250):
            self._set_status("Enter values between 20 and 250 bpm.")
            return

        add_reading(Reading(timestamp=timestamp, heart_rate=heart_rate, pulse=pulse))
        self._set_status("Reading added.", ok=True)
        self.hr_entry.delete(0, "end")
        self.pulse_entry.delete(0, "end")
        self.refresh()

    def on_delete(self, reading_id: str) -> None:
        delete_reading(reading_id)
        self.refresh()

    def _set_status(self, text: str, ok: bool = False) -> None:
        self.status_label.configure(text=text, text_color="#2e7d32" if ok else "#c62828")

    def refresh(self) -> None:
        readings = load_readings()
        self.hr_card.update_data([r.timestamp for r in readings], [r.heart_rate for r in readings])
        self.pulse_card.update_data([r.timestamp for r in readings], [r.pulse for r in readings])
        self._refresh_history(readings)

    def _refresh_history(self, readings: list) -> None:
        for widget in self.history_frame.winfo_children():
            widget.destroy()

        recent = list(reversed(readings))[:15]
        if not recent:
            ctk.CTkLabel(
                self.history_frame, text="No readings yet.",
                text_color=MUTED_TEXT, font=ctk.CTkFont(size=12),
            ).pack(anchor="w", pady=6, padx=6)
            return

        for r in recent:
            row = ctk.CTkFrame(self.history_frame, fg_color=ROW_COLOR, corner_radius=8)
            row.pack(fill="x", pady=3)
            row.grid_columnconfigure(0, weight=1)

            text = f"{r.timestamp.strftime('%Y-%m-%d %H:%M')}\nHR {r.heart_rate}  ·  Pulse {r.pulse}"
            ctk.CTkLabel(
                row, text=text, font=ctk.CTkFont(size=11), justify="left", anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=10, pady=6)

            ctk.CTkButton(
                row, text="✕", width=24, height=24, fg_color="transparent",
                text_color=MUTED_TEXT, hover_color=ROW_HOVER,
                command=lambda rid=r.id: self.on_delete(rid),
            ).grid(row=0, column=1, padx=(0, 6))


if __name__ == "__main__":
    app = HealthTrackerApp()
    app.mainloop()