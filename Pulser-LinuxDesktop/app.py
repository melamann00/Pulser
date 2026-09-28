from datetime import datetime
import math
import customtkinter as ctk
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from data_store import Reading, add_reading, delete_reading, load_readings

DEFAULT_DARK_MODE = True

ctk.set_appearance_mode("dark" if DEFAULT_DARK_MODE else "light")
ctk.set_default_color_theme("green")

SYSTOLIC_COLOR = "#e63946"
DIASTOLIC_COLOR = "#8e44ad"
PULSE_COLOR = "#457b9d"
ROW_COLOR = ("#f2f2f2", "#2b2b2b")
ROW_HOVER = ("#e3e3e3", "#3a3a3a")
MUTED_TEXT = ("#8a8a8a", "#9a9a9a")

ZONE_GOOD = "#43a047"  # green
ZONE_MID = "#fb8c00"   # orange
ZONE_BAD = "#e53935"   # red

ZONE_BOUNDS = [
    (0, 50, ZONE_BAD),
    (50, 60, ZONE_MID),
    (60, 100, ZONE_GOOD),
    (100, 120, ZONE_MID),
    (120, 300, ZONE_BAD),
]

# Niepodwyższone <120/<70, Podwyższone 120-139/70-89, Nadciśnienie >=140/90.
SYSTOLIC_ZONE_BOUNDS = [
    (0, 120, ZONE_GOOD),
    (120, 140, ZONE_MID),
    (140, 300, ZONE_BAD),
]
DIASTOLIC_ZONE_BOUNDS = [
    (0, 70, ZONE_GOOD),
    (70, 90, ZONE_MID),
    (90, 300, ZONE_BAD),
]
NORM_BREAKS = (0.0, 100 / 3, 200 / 3, 100.0)
NORMALIZED_ZONE_BOUNDS = [
    (NORM_BREAKS[0], NORM_BREAKS[1], ZONE_GOOD),
    (NORM_BREAKS[1], NORM_BREAKS[2], ZONE_MID),
    (NORM_BREAKS[2], NORM_BREAKS[3], ZONE_BAD),
]
ZONE_TICK_LABELS = ["Prawidłowe", "Podwyższone", "Nadciśnienie"]

DEFAULT_Y_MIN = 30
DEFAULT_Y_MAX = 150
Y_PADDING = 10
HOVER_RADIUS_PX = 18


class ChartCard(ctk.CTkFrame):
    def __init__(self, master, title: str, series: list, unit: str = "mmHg",
                 zone_bounds: list = None, is_dark: bool = DEFAULT_DARK_MODE,
                 normalize_zones: bool = False, y_min: float = None,
                 y_max: float = None, **kwargs):
        super().__init__(master, corner_radius=10, border_width=1,
                         border_color=("#d9d9d9", "#3c3c3c"), **kwargs)
        self.series = series
        self.unit = unit
        # Każdy wykres jest niezależny i pokazuje rzeczywiste wartości.
        # Ciśnienie skurczowe i rozkurczowe nie są normalizowane do wspólnej skali.
        self.normalized = bool(normalize_zones) and bool(series) and all(
            s.get("zone_bounds") for s in series
        )
        self.zone_bounds = NORMALIZED_ZONE_BOUNDS if self.normalized else (zone_bounds or [])
        self.is_dark = is_dark
        self.y_min = y_min
        self.y_max = y_max
        self._timestamps: list = []
        self._values: list = []
        self._hover_idx = None
        ctk.CTkLabel(
            self, text=title, font=ctk.CTkFont(size=16, weight="bold"), anchor="w"
        ).pack(fill="x", padx=18, pady=(14, 4))
        self.figure = Figure(figsize=(5, 3), dpi=100)
        self.axis = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=14, pady=(0, 16))
        self.canvas.get_tk_widget().configure(highlightthickness=0, bd=0)
        self.canvas.get_tk_widget().bind("<Configure>", lambda e: self._redraw(), add="+")
        self.canvas.mpl_connect("motion_notify_event", self._on_hover)
        self.canvas.mpl_connect("figure_leave_event", lambda _e: self._hide_tooltip())
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
        if self.y_min is not None and self.y_max is not None:
            lo, hi = float(self.y_min), float(self.y_max)
        else:
            all_vals = [
                v for series_vals in self._values
                for v in series_vals if not math.isnan(v)
            ]
            if all_vals:
                lo = min(DEFAULT_Y_MIN, min(all_vals) - Y_PADDING)
                hi = max(DEFAULT_Y_MAX, max(all_vals) + Y_PADDING)
            else:
                lo, hi = DEFAULT_Y_MIN, DEFAULT_Y_MAX
        return max(0, lo), hi

    @staticmethod
    def _classify(value: float, zone_bounds: list) -> str:
        for lo, hi, color in zone_bounds:
            if lo <= value < hi:
                return color
        return zone_bounds[-1][2] if value >= zone_bounds[-1][1] else zone_bounds[0][2]

    @staticmethod
    def _normalize(value: float, zone_bounds: list) -> float:
        b0, b1, b2, b3 = NORM_BREAKS
        lo0, t1, _ = zone_bounds[0]
        _, t2, _ = zone_bounds[1]
        _, t3, _ = zone_bounds[-1]

        if value < t1:
            frac = (value - lo0) / (t1 - lo0) if t1 > lo0 else 0.0
            return b0 + frac * (b1 - b0)
        if value < t2:
            return b1 + (value - t1) / (t2 - t1) * (b2 - b1)

        span = (t3 - t2) or 1
        return min(b3, b2 + (value - t2) / span * (b3 - b2))

    def _display_vals(self, s_idx: int) -> list:
        vals = self._values[s_idx]
        if not self.normalized:
            return vals
        zb = self.series[s_idx]["zone_bounds"]
        return [v if math.isnan(v) else self._normalize(v, zb) for v in vals]

    def _draw_zones(self, ylim: tuple, alpha: float) -> None:
        y0, y1 = ylim
        for band_lo, band_hi, color in self.zone_bounds:
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
                0.5, 0.5, "Brak pomiarów",
                ha="center", va="center", color=c["muted"], fontsize=11,
                transform=self.axis.transAxes, zorder=5,
            )
            self.axis.set_xticks([])
            self.axis.set_yticks([])
            for spine in self.axis.spines.values():
                spine.set_visible(False)
        else:
            for s_idx, (s, vals) in enumerate(zip(self.series, self._values)):
                disp = self._display_vals(s_idx)
                self.axis.plot(
                    self._timestamps, disp,
                    color=s["color"], linewidth=2.2, zorder=3, label=s["label"],
                )
                points = [(t, d, r) for t, d, r in zip(self._timestamps, disp, vals) if not math.isnan(r)]
                if not points:
                    continue
                xs, ys, raws = zip(*points)
                if s.get("zone_bounds"):
                    marker_colors = [self._classify(r, s["zone_bounds"]) for r in raws]
                else:
                    marker_colors = s["color"]
                self.axis.scatter(
                    xs, ys, s=32, facecolors=c["bg"], edgecolors=marker_colors,
                    linewidths=1.4, zorder=4,
                )
            if self.normalized:
                mid = [(lo + hi) / 2 for lo, hi, _ in NORMALIZED_ZONE_BOUNDS]
                self.axis.set_yticks(mid)
                self.axis.set_yticklabels(ZONE_TICK_LABELS)
            else:
                self.axis.set_ylabel(self.unit, fontsize=9, color=c["text"])
            self.axis.tick_params(axis="both", labelsize=8, colors=c["text"])
            self.axis.grid(True, axis="y", linestyle="--", linewidth=0.6, color=c["grid"], zorder=1)
            for side in ("top", "right"):
                self.axis.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                self.axis.spines[side].set_color(c["spine"])
            self.axis.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
            self.figure.autofmt_xdate(rotation=0, ha="center")
            if len(self.series) > 1:
                legend = self.axis.legend(loc="upper left", fontsize=8, frameon=False)
                for text in legend.get_texts():
                    text.set_color(c["text"])

        ylim = (0.0, 100.0) if self.normalized else self._compute_ylim()
        self.axis.set_ylim(*ylim)
        if self.zone_bounds:
            self._draw_zones(ylim, c["zone_alpha"])

        self._hover_idx = None
        self._tooltip = self.axis.annotate(
            "", xy=(0, 0), xytext=(12, 12), textcoords="offset points",
            fontsize=9, color=c["text"], zorder=10, visible=False,
            bbox=dict(
                boxstyle="round,pad=0.45",
                fc=ROW_COLOR[1] if self.is_dark else ROW_COLOR[0],
                ec=self.series[0]["color"], lw=1.2,
            ),
        )

        try:
            self.figure.tight_layout()
        except Exception:
            pass
        self.canvas.draw_idle()

    def _hide_tooltip(self) -> None:
        if self._hover_idx is not None:
            self._hover_idx = None
            self._tooltip.set_visible(False)
            self.canvas.draw_idle()

    def _on_hover(self, event) -> None:
        if not self._timestamps or event.inaxes != self.axis:
            self._hide_tooltip()
            return

        x_nums = mdates.date2num(self._timestamps)
        best = None
        for s_idx, vals in enumerate(self._values):
            disp = self._display_vals(s_idx)
            idxs = [i for i, v in enumerate(vals) if not math.isnan(v)]
            if not idxs:
                continue
            xy_data = [(x_nums[i], disp[i]) for i in idxs]
            xs_px, ys_px = self.axis.transData.transform(xy_data).T
            local_best = int(((xs_px - event.x) ** 2 + (ys_px - event.y) ** 2).argmin())
            dist = ((xs_px[local_best] - event.x) ** 2 + (ys_px[local_best] - event.y) ** 2) ** 0.5
            if best is None or dist < best[0]:
                best = (dist, s_idx, idxs[local_best])

        if best is None or best[0] > HOVER_RADIUS_PX:
            self._hide_tooltip()
            return
        if (best[1], best[2]) == self._hover_idx:
            return
        self._hover_idx = (best[1], best[2])

        _, s_idx, idx = best
        ts = self._timestamps[idx]
        val = self._values[s_idx][idx]
        disp_val = self._display_vals(s_idx)[idx]
        x0, x1 = self.axis.get_xlim()
        y0, y1 = self.axis.get_ylim()
        dx = 12 if mdates.date2num(ts) <= (x0 + x1) / 2 else -12
        dy = 12 if disp_val <= (y0 + y1) / 2 else -12

        self._tooltip.xy = (mdates.date2num(ts), disp_val)
        self._tooltip.set_position((dx, dy))
        self._tooltip.set_ha("left" if dx > 0 else "right")
        self._tooltip.set_va("bottom" if dy > 0 else "top")
        if len(self.series) > 1:
            text = f"{ts.strftime('%Y-%m-%d %H:%M')}\n{self.series[s_idx]['label']}: {val} {self.unit}"
        else:
            text = f"{ts.strftime('%Y-%m-%d %H:%M')}\n{val} {self.unit}"
        self._tooltip.set_text(text)
        bbox_patch = self._tooltip.get_bbox_patch()
        if bbox_patch is not None:
            s = self.series[s_idx]
            edge_color = self._classify(val, s["zone_bounds"]) if s.get("zone_bounds") else s["color"]
            bbox_patch.set_edgecolor(edge_color)
        self._tooltip.set_visible(True)
        self.canvas.draw_idle()


class HealthTrackerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Health Tracker")
        self.geometry("1668x890")
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
        ctk.CTkLabel(form, text="Data", font=ctk.CTkFont(size=12)).grid(
            row=0, column=0, sticky="w", pady=(0, 2)
        )
        ctk.CTkLabel(form, text="Godzina", font=ctk.CTkFont(size=12)).grid(
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

        ctk.CTkLabel(form, text="Ciśnienie skurczowe (mmHg)", font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        self.systolic_entry = ctk.CTkEntry(form, placeholder_text="np. 120")
        self.systolic_entry.grid(row=3, column=0, columnspan=2, sticky="we", pady=(0, 12))

        ctk.CTkLabel(form, text="Ciśnienie rozkurczowe (mmHg)", font=ctk.CTkFont(size=12)).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        self.diastolic_entry = ctk.CTkEntry(form, placeholder_text="np. 80")
        self.diastolic_entry.grid(row=5, column=0, columnspan=2, sticky="we", pady=(0, 12))

        ctk.CTkLabel(form, text="Puls (bpm)", font=ctk.CTkFont(size=12)).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(0, 2)
        )
        self.pulse_entry = ctk.CTkEntry(form, placeholder_text="np. 70")
        self.pulse_entry.grid(row=7, column=0, columnspan=2, sticky="we", pady=(0, 12))

        self.add_button = ctk.CTkButton(form, text="Add reading", command=self.on_add)
        self.add_button.grid(row=8, column=0, columnspan=2, sticky="we")

        self.status_label = ctk.CTkLabel(
            form, text="", font=ctk.CTkFont(size=12), text_color="#c62828", anchor="w",
        )
        self.status_label.grid(row=9, column=0, columnspan=2, sticky="we", pady=(6, 0))

        ctk.CTkLabel(
            sidebar, text="Wcześniejsze wyniki", font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=3, column=0, columnspan=2, padx=20, pady=(14, 6), sticky="w")

        self.history_frame = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self.history_frame.grid(row=4, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="nswe")

    def _build_charts(self) -> None:
        # Układ jak na screenie:
        # [ osobny wykres skurczowego ] [ osobny wykres rozkurczowego ]
        # [                 szeroki wykres pulsu                    ]
        charts = ctk.CTkFrame(self, fg_color="transparent")
        charts.grid(row=0, column=1, sticky="nswe", padx=16, pady=16)

        charts.grid_columnconfigure(0, weight=1, uniform="pressure_charts")
        charts.grid_columnconfigure(1, weight=1, uniform="pressure_charts")
        charts.grid_rowconfigure(0, weight=1, minsize=300)
        charts.grid_rowconfigure(1, weight=1, minsize=300)

        # OSOBNY WYKRES: ciśnienie skurczowe
        self.systolic_card = ChartCard(
            charts,
            "Ciśnienie skurczowe",
            series=[{
                "label": "Skurczowe",
                "color": SYSTOLIC_COLOR,
                "zone_bounds": SYSTOLIC_ZONE_BOUNDS,
            }],
            unit="mmHg",
            zone_bounds=SYSTOLIC_ZONE_BOUNDS,
            normalize_zones=False,
            y_min=50,
            y_max=190,
        )
        self.systolic_card.grid(
            row=0, column=0, sticky="nswe",
            padx=(0, 6), pady=(0, 6)
        )

        # OSOBNY WYKRES: ciśnienie rozkurczowe
        self.diastolic_card = ChartCard(
            charts,
            "Ciśnienie rozkurczowe",
            series=[{
                "label": "Rozkurczowe",
                "color": DIASTOLIC_COLOR,
                "zone_bounds": DIASTOLIC_ZONE_BOUNDS,
            }],
            unit="mmHg",
            zone_bounds=DIASTOLIC_ZONE_BOUNDS,
            normalize_zones=False,
            y_min=30,
            y_max=120,
        )
        self.diastolic_card.grid(
            row=0, column=1, sticky="nswe",
            padx=(6, 0), pady=(0, 6)
        )

        # SZEROKI DOLNY WYKRES: puls
        self.pulse_card = ChartCard(
            charts,
            "Wykres Pulsu",
            series=[{"label": "Puls", "color": PULSE_COLOR}],
            unit="bpm",
            zone_bounds=ZONE_BOUNDS,
            y_min=30,
            y_max=150,
        )
        self.pulse_card.grid(
            row=1, column=0, columnspan=2,
            sticky="nswe", padx=0, pady=(6, 0)
        )

    def _toggle_appearance(self) -> None:
        is_dark = bool(self.appearance_switch.get())
        ctk.set_appearance_mode("dark" if is_dark else "light")
        self.systolic_card.set_dark(is_dark)
        self.diastolic_card.set_dark(is_dark)
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
        systolic_str = self.systolic_entry.get().strip()
        diastolic_str = self.diastolic_entry.get().strip()
        pulse_str = self.pulse_entry.get().strip()

        try:
            timestamp = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            self._set_status("Enter a valid date (YYYY-MM-DD) and time (HH:MM).")
            return

        try:
            systolic = int(systolic_str)
            diastolic = int(diastolic_str)
            pulse = int(pulse_str)
        except ValueError:
            self._set_status("Systolic, diastolic and pulse must be whole numbers.")
            return

        if not (50 <= systolic <= 260) or not (30 <= diastolic <= 200):
            self._set_status("Enter blood pressure within a realistic mmHg range.")
            return
        if not (20 <= pulse <= 250):
            self._set_status("Enter a pulse between 20 and 250 bpm.")
            return

        add_reading(Reading(timestamp=timestamp, systolic=systolic, diastolic=diastolic, pulse=pulse))
        self._set_status("Reading added.", ok=True)
        self.systolic_entry.delete(0, "end")
        self.diastolic_entry.delete(0, "end")
        self.pulse_entry.delete(0, "end")
        self.refresh()

    def on_delete(self, reading_id: str) -> None:
        delete_reading(reading_id)
        self.refresh()

    def _set_status(self, text: str, ok: bool = False) -> None:
        self.status_label.configure(text=text, text_color="#2e7d32" if ok else "#c62828")

    def refresh(self) -> None:
        readings = load_readings()
        timestamps = [r.timestamp for r in readings]
        systolic_vals = [r.systolic if r.systolic is not None else float("nan") for r in readings]
        diastolic_vals = [r.diastolic if r.diastolic is not None else float("nan") for r in readings]
        pulse_vals = [r.pulse for r in readings]

        self.systolic_card.update_data(timestamps, [systolic_vals])
        self.diastolic_card.update_data(timestamps, [diastolic_vals])
        self.pulse_card.update_data(timestamps, [pulse_vals])
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

            if r.systolic is not None and r.diastolic is not None:
                bp_str = f"{r.systolic}/{r.diastolic} mmHg"
            else:
                bp_str = "-/- mmHg"
            text = f"{r.timestamp.strftime('%Y-%m-%d %H:%M')}\n{bp_str}  ·  Puls {r.pulse} bpm"
            ctk.CTkLabel(
                row, text=text, font=ctk.CTkFont(size=11), justify="left", anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=10, pady=6)

            ctk.CTkButton(
                row, text="\u2715", width=24, height=24, fg_color="transparent",
                text_color=MUTED_TEXT, hover_color=ROW_HOVER,
                command=lambda rid=r.id: self.on_delete(rid),
            ).grid(row=0, column=1, padx=(0, 6))


if __name__ == "__main__":
    app = HealthTrackerApp()
    app.mainloop()
