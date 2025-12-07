# thumbnail_fixed_live_preview_fonts_fixed.py
import sys, os, glob, math, numpy as np
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QFileDialog,
    QLineEdit, QLabel, QSlider, QComboBox, QColorDialog, QTextEdit, QProgressBar,
    QApplication
)
from PyQt6.QtGui import QFontDatabase, QPixmap, QImage, QColor
from PyQt6.QtCore import QTimer, Qt
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from matplotlib import font_manager

import arabic_reshaper
from bidi.algorithm import get_display


class HalfFadeBlend(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Thumbnail Generator (Farsi + Glow + Gradient)")
        self.setGeometry(70, 70, 900, 550)

        # Paths
        self.Image1_path = None
        self.Image2_path = None

        # Colors
        self.gradient_color = (0, 255, 255)
        self.text_colors = {
            'top': (255, 255, 255),
            'bottom': (0, 255, 255),
            'username': (255, 255, 255),
            'label': (0, 255, 255)
        }

        # Text-specific settings (per-text sizes + stroke settings)
        self.text_settings = {
            'top': {'size': 90, 'stroke': 4, 'stroke_color': (0,0,0,255)},
            'bottom': {'size': 90, 'stroke': 4, 'stroke_color': (0,0,0,255)},
            'username': {'size': 53, 'stroke': 3, 'stroke_color': (0,0,0,255)},
            'label': {'size': 53, 'stroke': 2, 'stroke_color': (0,0,0,255)}
        }

        # Debounce timer for live preview
        self._preview_timer = QTimer(singleShot=True)
        self._preview_timer.setInterval(250)
        self._preview_timer.timeout.connect(self._update_preview_from_ui)

        # -------------------- Left Panel --------------------
        self.img1_btn = QPushButton("Browse Left Image")
        self.img1_btn.clicked.connect(lambda: self.load_Image(1))
        self.img2_btn = QPushButton("Browse Right Image")
        self.img2_btn.clicked.connect(lambda: self.load_Image(2))

        self.top_text_input = QLineEdit(); self.top_text_input.setPlaceholderText("Top caption (white)")
        self.top_text_input.setText("ژطي «ةگن » just Testing")
        self.bottom_text_input = QLineEdit(); self.bottom_text_input.setPlaceholderText("Bottom caption (cyan)")
        self.bottom_text_input.setText("گپچ لغ  - کتس just example")
        self.username_input = QLineEdit(); self.username_input.setPlaceholderText("Username (top-right)")
        self.username_input.setText("ولاگ Farsi")
        self.label_input = QLineEdit(); self.label_input.setPlaceholderText("Top-left label")
        self.label_input.setText("ليبل گزارشي")

        # Connect changes to live preview
        for widget in (self.top_text_input, self.bottom_text_input, self.username_input, self.label_input):
            widget.textChanged.connect(self.request_preview_update)

        # Sliders (we'll create actual widgets via make_slider)
        self.left_shift_slider = self.make_slider("Left Shift (%)", 25)
        self.right_shift_slider = self.make_slider("Right Shift (%)", 25)
        self.left_sat_slider = self.make_slider("Left Saturation (%)", 130)
        self.right_sat_slider = self.make_slider("Right Saturation (%)", 130)
        self.left_con_slider = self.make_slider("Left Contrast (%)", 115)
        self.right_con_slider = self.make_slider("Right Contrast (%)", 115)
        self.glow_density_slider = self.make_slider("Glow Density (%)", 100)
        self.glow_radius_slider = self.make_slider("Glow Radius", 80)
        self.gradient_size_slider = self.make_slider("Gradient Size (%)", 36)

        # Connect sliders to preview
        for s in (self.left_shift_slider, self.right_shift_slider,
                  self.left_sat_slider, self.right_sat_slider,
                  self.left_con_slider, self.right_con_slider,
                  self.glow_density_slider, self.glow_radius_slider,
                  self.gradient_size_slider):
            s["slider"].valueChanged.connect(self.request_preview_update)

        # Gradient button
        self.gradient_color_button = QPushButton("Gradient Color")
        self.gradient_color_button.clicked.connect(self.select_gradient_color)

        # Font selection - combobox
        self.font_selection_combobox = QComboBox()
        self._font_dir = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")

        # Helper: get installed fonts (returns dict name->path)
        def get_installed_fonts():
            font_dict = {}
            for f in font_manager.findSystemFonts(fontpaths=None, fontext='ttf'):
                try:
                    prop = font_manager.FontProperties(fname=f)
                    name = prop.get_name()
                    if name not in font_dict:
                        font_dict[name] = f
                except Exception:
                    continue
            return font_dict

        # Populate combobox
        self._font_dict = get_installed_fonts()
        for font_name in sorted(self._font_dict.keys()):
            self.font_selection_combobox.addItem(font_name, self._font_dict[font_name])
        if self.font_selection_combobox.count() == 0:
            self.font_selection_combobox.addItem("Arial", os.path.join(self._font_dir, "arial.ttf"))

        # choose preferred default if present
        preferred = ["Amin", "B Titr", "Impact", "Arial", "Segoe UI"]
        chosen_index = -1
        for i in range(self.font_selection_combobox.count()):
            text = self.font_selection_combobox.itemText(i)
            for pref in preferred:
                if text.lower() == pref.lower():
                    chosen_index = i
                    break
            if chosen_index != -1:
                break
        if chosen_index == -1 and self.font_selection_combobox.count() > 0:
            chosen_index = 0
        if chosen_index != -1:
            self.font_selection_combobox.setCurrentIndex(chosen_index)

        self.font_selection_combobox.currentIndexChanged.connect(self.request_preview_update)

        # Text color & stroke buttons
        self.top_text_color_button = QPushButton("Top Color"); self.top_text_color_button.clicked.connect(lambda: self.select_text_color('top'))
        self.bottom_text_color_button = QPushButton("Bottom Color"); self.bottom_text_color_button.clicked.connect(lambda: self.select_text_color('bottom'))
        self.username_text_color_button = QPushButton("Username Color"); self.username_text_color_button.clicked.connect(lambda: self.select_text_color('username'))
        self.label_text_color_button = QPushButton("Label Color"); self.label_text_color_button.clicked.connect(lambda: self.select_text_color('label'))

        self.top_stroke_color_button = QPushButton("Top Stroke Color"); self.top_stroke_color_button.clicked.connect(lambda: self.select_stroke_color('top'))
        self.bottom_stroke_color_button = QPushButton("Bottom Stroke Color"); self.bottom_stroke_color_button.clicked.connect(lambda: self.select_stroke_color('bottom'))
        self.username_stroke_color_button = QPushButton("Username Stroke Color"); self.username_stroke_color_button.clicked.connect(lambda: self.select_stroke_color('username'))
        self.label_stroke_color_button = QPushButton("Label Stroke Color"); self.label_stroke_color_button.clicked.connect(lambda: self.select_stroke_color('label'))

        # Font size & stroke sliders per-text
        self.top_size_slider = self.make_slider("Top Font Size", self.text_settings['top']['size'])
        self.top_size_slider["slider"].valueChanged.connect(lambda val: self.update_text_setting('top','size',val))
        self.bottom_size_slider = self.make_slider("Bottom Font Size", self.text_settings['bottom']['size'])
        self.bottom_size_slider["slider"].valueChanged.connect(lambda val: self.update_text_setting('bottom','size',val))
        self.username_size_slider = self.make_slider("Username Font Size", self.text_settings['username']['size'])
        self.username_size_slider["slider"].valueChanged.connect(lambda val: self.update_text_setting('username','size',val))
        self.label_size_slider = self.make_slider("Label Font Size", self.text_settings['label']['size'])
        self.label_size_slider["slider"].valueChanged.connect(lambda val: self.update_text_setting('label','size',val))

        self.top_stroke_slider = self.make_slider("Top Stroke Size", self.text_settings['top']['stroke'])
        self.top_stroke_slider["slider"].valueChanged.connect(lambda val: self.update_text_setting('top','stroke',val))
        self.bottom_stroke_slider = self.make_slider("Bottom Stroke Size", self.text_settings['bottom']['stroke'])
        self.bottom_stroke_slider["slider"].valueChanged.connect(lambda val: self.update_text_setting('bottom','stroke',val))
        self.username_stroke_slider = self.make_slider("Username Stroke Size", self.text_settings['username']['stroke'])
        self.username_stroke_slider["slider"].valueChanged.connect(lambda val: self.update_text_setting('username','stroke',val))
        self.label_stroke_slider = self.make_slider("Label Stroke Size", self.text_settings['label']['stroke'])
        self.label_stroke_slider["slider"].valueChanged.connect(lambda val: self.update_text_setting('label','stroke',val))

        # -------------------- Right Panel --------------------
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(320, 180)  # 16:9 preview area
        self.progress_bar = QProgressBar(); self.progress_bar.setRange(0,100); self.progress_bar.setValue(0)
        self.log_area = QTextEdit(); self.log_area.setReadOnly(True); self.log_area.setFixedHeight(60)
        self.save_btn = QPushButton("Save Thumbnail"); self.save_btn.clicked.connect(self.save_full_resolution)
        self.clear_log_btn = QPushButton("Clear Log"); self.clear_log_btn.clicked.connect(lambda: self.log_area.clear())

        # -------------------- Layouts --------------------
        left_layout = QVBoxLayout()
        row = QHBoxLayout(); row.addWidget(self.img1_btn); row.addWidget(self.img2_btn); left_layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(self.top_text_input); row.addWidget(self.bottom_text_input); left_layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(self.top_text_color_button); row.addWidget(self.top_stroke_color_button); row.addWidget(self.bottom_text_color_button); row.addWidget(self.bottom_stroke_color_button); left_layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(self.username_input); row.addWidget(self.label_input); left_layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(self.username_text_color_button); row.addWidget(self.username_stroke_color_button); row.addWidget(self.label_text_color_button); row.addWidget(self.label_stroke_color_button); left_layout.addLayout(row)

        # add_slider_pair must be defined before use (inner helper)
        def add_slider_pair(a, b):
            r = QHBoxLayout()
            r.addLayout(a["layout"])
            r.addLayout(b["layout"])
            left_layout.addLayout(r)

        add_slider_pair(self.left_shift_slider, self.right_shift_slider)
        add_slider_pair(self.left_sat_slider, self.right_sat_slider)
        add_slider_pair(self.left_con_slider, self.right_con_slider)
        add_slider_pair(self.glow_density_slider, self.glow_radius_slider)

        row = QHBoxLayout(); row.addLayout(self.gradient_size_slider["layout"]); row.addWidget(self.gradient_color_button); left_layout.addLayout(row)
        row = QHBoxLayout(); row.addWidget(QLabel("Font file:")); row.addWidget(self.font_selection_combobox); left_layout.addLayout(row)

        # Font size + stroke sliders grouped by text
        for key in ['top','bottom','username','label']:
            row = QHBoxLayout()
            row.addLayout(getattr(self,f"{key}_size_slider")["layout"])
            row.addLayout(getattr(self,f"{key}_stroke_slider")["layout"])
            left_layout.addLayout(row)

        left_layout.addStretch()
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Preview"))
        right_layout.addWidget(self.preview_label)
        right_layout.addWidget(self.progress_bar)
        right_layout.addWidget(self.log_area)
        btn_row = QHBoxLayout(); btn_row.addWidget(self.save_btn); btn_row.addWidget(self.clear_log_btn); right_layout.addLayout(btn_row)
        right_layout.addStretch()

        main_layout = QHBoxLayout(); main_layout.addLayout(left_layout); main_layout.addLayout(right_layout)
        self.setLayout(main_layout)

        self._last_preview_img = None
        self.log("Ready. Select images and a font file (choose actual .ttf/.otf).")

    # ---------- Utility Functions ----------
    def make_slider(self, name, default):
        """Create a labeled slider with a value label. Returns dict with 'layout' and 'slider' and 'val_label'."""
        label = QLabel(name)
        slider = QSlider(Qt.Orientation.Horizontal, self)

        # heuristics for ranges based on name
        if "Font Size" in name or "FontSize" in name or "Font Size" in name:
            minimum, maximum = 8, 300
        elif "Stroke" in name and "Glow" not in name:
            minimum, maximum = 0, 50
        elif "Shift" in name:
            minimum, maximum = 0, 50
        elif "Saturation" in name or "Contrast" in name or "Density" in name:
            minimum, maximum = 0, 200
        elif "Radius" in name:
            minimum, maximum = 0, 200
        elif "Gradient" in name:
            minimum, maximum = 0, 100
        else:
            minimum, maximum = 0, 200

        slider.setRange(minimum, maximum)
        slider.setValue(int(default))
        slider.setSingleStep(1)
        val_label = QLabel(str(int(default)))
        slider.valueChanged.connect(lambda v, l=val_label: l.setText(str(int(v))))

        layout = QVBoxLayout()
        layout.addWidget(label)
        hl = QHBoxLayout()
        hl.addWidget(slider)
        hl.addWidget(val_label)
        layout.addLayout(hl)
        return {"layout": layout, "slider": slider, "val_label": val_label}

    def select_gradient_color(self):
        col = QColorDialog.getColor()
        if col.isValid():
            self.gradient_color = (col.red(), col.green(), col.blue())
            self.request_preview_update()

    def select_text_color(self, key):
        col = QColorDialog.getColor()
        if col.isValid():
            self.text_colors[key] = (col.red(), col.green(), col.blue())
            self.request_preview_update()

    def select_stroke_color(self, key):
        col = QColorDialog.getColor()
        if col.isValid():
            # store as RGBA
            self.text_settings[key]['stroke_color'] = (col.red(), col.green(), col.blue(), col.alpha())
            self.request_preview_update()

    def load_Image(self, idx):
        path, _ = QFileDialog.getOpenFileName(self, f"Select Image {idx}", ".", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            if idx == 1:
                self.Image1_path = path
            else:
                self.Image2_path = path
            self.log(f"Loaded image {idx}: {path}")
            self.request_preview_update()

    def log(self, msg):
        # append message to log area with newline
        current = self.log_area.toPlainText()
        new = current + msg + "\n" if current else msg + "\n"
        self.log_area.setPlainText(new)
        # scroll to bottom
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())

    def update_text_setting(self, key, attr, value):
        self.text_settings[key][attr] = int(value)
        self.request_preview_update()

    def request_preview_update(self):
        self._preview_timer.start()  # debounce

    def prepare_rtl_text(self, text):
        if not text:
            return ""
        try:
            reshaped = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped)
            return bidi_text
        except Exception:
            return text

    # -------------------- Preview & Save pipeline --------------------
    def _update_preview_from_ui(self):
        self.progress_bar.setValue(0)
        QApplication.processEvents()
        if not self.Image1_path or not self.Image2_path:
            self.log("Preview: waiting for both images.")
            return
        try:
            img1 = Image.open(self.Image1_path).convert("RGB")
            img2 = Image.open(self.Image2_path).convert("RGB")

            pv_w, pv_h = 640, 360
            img1 = self.crop_to_aspect_ratio(img1)
            img2 = self.crop_to_aspect_ratio(img2)
            img1 = img1.resize((pv_w, pv_h), Image.Resampling.BILINEAR)
            img2 = img2.resize((pv_w, pv_h), Image.Resampling.BILINEAR)
            self.progress_bar.setValue(10); QApplication.processEvents()

            img1 = self.apply_enhancements(img1, self.left_sat_slider["slider"].value(), self.left_con_slider["slider"].value())
            img2 = self.apply_enhancements(img2, self.right_sat_slider["slider"].value(), self.right_con_slider["slider"].value())
            self.progress_bar.setValue(30); QApplication.processEvents()

            img1 = self.shift_image(img1, self.left_shift_slider["slider"].value(), "left")
            img2 = self.shift_image(img2, self.right_shift_slider["slider"].value(), "right")
            self.progress_bar.setValue(45); QApplication.processEvents()

            w, h = img1.size
            fade_ratio = 0.12
            fade_w = int(w * fade_ratio)
            mid = w // 2
            left_edge, right_edge = mid - fade_w // 2, mid + fade_w // 2
            x = np.arange(w)
            mask_cols = np.zeros_like(x, dtype=np.float32)
            mask_cols[:left_edge] = 255
            if right_edge > left_edge:
                grad = 1 - ((x[left_edge:right_edge] - left_edge) / (right_edge - left_edge))
                mask_cols[left_edge:right_edge] = grad * 255
            mask = np.tile(mask_cols, (h,1)).astype(np.uint8)
            mask_img = Image.fromarray(mask).filter(ImageFilter.GaussianBlur(radius=max(1, fade_w//8)))
            blended = Image.composite(img1, img2, mask_img).convert("RGBA")
            self.progress_bar.setValue(60); QApplication.processEvents()

            self.draw_gradient(blended, self.gradient_color, self.gradient_size_slider["slider"].value())
            self.progress_bar.setValue(70); QApplication.processEvents()

            font_path = self.font_selection_combobox.currentData()
            font_size = max(18, int(h * 0.12))
            try:
                if font_path and os.path.exists(font_path):
                    base_preview_font = ImageFont.truetype(font_path, size=font_size)
                else:
                    base_preview_font = ImageFont.truetype(os.path.join(self._font_dir, "arial.ttf"), size=font_size)
                self.progress_bar.setValue(80)
            except Exception as e:
                self.log(f"Preview font load error: {e} - falling back to default")
                base_preview_font = ImageFont.load_default()
                self.progress_bar.setValue(80)

            top_text = self.prepare_rtl_text(self.top_text_input.text())
            bottom_text = self.prepare_rtl_text(self.bottom_text_input.text())
            username = self.prepare_rtl_text(self.username_input.text())
            label_text = self.prepare_rtl_text(self.label_input.text())

            self._draw_texts_preview(blended, base_preview_font, top_text, bottom_text, username, label_text)
            self.progress_bar.setValue(90); QApplication.processEvents()

            preview_img = blended.resize((320,180), Image.Resampling.BILINEAR).convert("RGBA")
            data = preview_img.tobytes("raw", "RGBA")
            qimg = QImage(data, preview_img.width, preview_img.height, QImage.Format.Format_RGBA8888)
            self.preview_label.setPixmap(QPixmap.fromImage(qimg))
            self._last_preview_img = blended
            self.progress_bar.setValue(100)
            QApplication.processEvents()
        except Exception as e:
            self.log(f"Preview error: {e}")
            self.preview_label.clear()
            self.progress_bar.setValue(0)

    # (rest of methods _draw_texts_preview, save_full_resolution, apply_enhancements, shift_image,
    #  crop_to_aspect_ratio, draw_gradient, draw_all_texts, draw_text_with_stroke)
    # For brevity I left them unchanged from your CHUNK2 — they were already OK structurally.
    # (Paste the CHUNK2 methods exactly here if you want a full single file.)

    # Insert CHUNK2 methods exactly as provided previously (they are compatible now).

    def _draw_texts_preview(self, blended, base_font, top_text, bottom_text, username, label_text):
        """Lightweight drawing used for preview only (faster).
        Uses per-text preview sizes so top & bottom don't overlap."""
        draw = ImageDraw.Draw(blended)
        w, h = blended.size
        right_margin = int(w * 0.09)

        # Build preview fonts based on user settings scaled down for preview
        font_path = self.font_selection_combobox.currentData()
        def make_preview_font(key, scale=0.5, fallback=base_font):
            try:
                size = max(8, int(self.text_settings[key]['size'] * scale))
                if font_path and os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size=size)
                else:
                    return ImageFont.truetype(os.path.join(self._font_dir, "arial.ttf"), size=size)
            except Exception:
                return fallback

        top_font = make_preview_font('top', scale=0.5)
        bottom_font = make_preview_font('bottom', scale=0.5)
        username_font = make_preview_font('username', scale=0.45)
        label_font = make_preview_font('label', scale=0.45)

        # measure bboxes
        top_bbox = draw.textbbox((0,0), top_text, font=top_font) if top_text else (0,0,0,0)
        top_h = top_bbox[3] - top_bbox[1]
        bottom_bbox = draw.textbbox((0,0), bottom_text, font=bottom_font) if bottom_text else (0,0,0,0)
        bottom_h = bottom_bbox[3] - bottom_bbox[1]

        # spacing: relative to average font size but at least a few pixels
        spacing = max(6, int((top_font.size if hasattr(top_font,'size') else 12 + bottom_font.size if hasattr(bottom_font,'size') else 12) * 0.12))

        # bottom_y anchored above bottom padding

        bottom_padding = int(h * 0.065)
#==================== bottom text show above the lowest down border 🛂 prevent bottom text to go below the down border =======
        safe_margin = max(2, int(bottom_h * 0.05))
        bottom_y = h - bottom_padding - bottom_h - safe_margin

        # top_y placed above bottom with spacing; if there's no bottom text, place top a bit above bottom padding
        if top_text and bottom_text:
            top_y = bottom_y - spacing - top_h
            # safety if overlap would still occur (rare), push top up further
            if top_y < 6:
                top_y = 6
        elif top_text:
            top_y = h - bottom_padding - top_h - 6
        else:
            top_y = None

        # Draw top
        if top_text:
            bbox = draw.textbbox((0,0), top_text, font=top_font)
            text_w = bbox[2]-bbox[0]
            x_pos = max(right_margin, w - right_margin - text_w)
            self.draw_text_with_stroke(blended, top_text, top_font, (x_pos, int(top_y)), self.text_colors['top'], stroke_key='top')

        # Draw bottom
        if bottom_text:
            bbox = draw.textbbox((0,0), bottom_text, font=bottom_font)
            text_w = bbox[2]-bbox[0]
            x_pos = max(right_margin, w - right_margin - text_w)
            self.draw_text_with_stroke(blended, bottom_text, bottom_font, (x_pos, int(bottom_y)), self.text_colors['bottom'], stroke_key='bottom')

        # username (top-right)
        if username:
            bbox = draw.textbbox((0,0), username, font=username_font)
            text_w = bbox[2]-bbox[0]
            pos = (w - text_w - 40, 30)
            self.draw_text_with_stroke(blended, username, username_font, pos, self.text_colors['username'], stroke_key='username')

        # label in top-left with tight background
#============= add strake shadow around the label txt- reduce adjustment of opaque around the ' label ' text
        # Label: tight background roughly the size of text + small paddings, text centered
        # Label: tight background roughly the size of text + small paddings, text centered
        # Label: tight background roughly the size of text + small paddings
        # Label: tight background roughly the size of text + small paddings
        # Label: tight background roughly the size of text + small paddings
    # Label: tight background roughly the size of text + small paddings
        # Label: tight background roughly the size of text + small paddings
        if label_text:
            bbox_l = draw.textbbox((0,0), label_text, font=label_font)
            text_w = bbox_l[2] - bbox_l[0]; text_h = bbox_l[3] - bbox_l[1]

            pad_x = max(2, int(self.text_settings['label']['size'] * 0.12))
            pad_y = max(1, int(self.text_settings['label']['size'] * 0.15))

            # use a proportional top offset so full-res matches preview placement
            # preview used y=70 when pv_h=360 -> ratio ~ 70/360
            preview_offset_ratio = 70.0 / 360.0
            x = 10
            y = max(10, int(h * preview_offset_ratio))  # keeps some minimum margin on tiny images

            bg_x0 = x - pad_x
            bg_y0 = y - pad_y
            bg_x1 = x + text_w + pad_x
            bg_y1 = y + text_h + pad_y

            # draw opaque box (RGBA)
            draw.rectangle((bg_x0, bg_y0, bg_x1, bg_y1), fill=(0, 0, 180, 200))

            # center text vertically and horizontally inside the box
            text_x = bg_x0 + (bg_x1 - bg_x0 - text_w) / 2
            text_y = bg_y0 + (bg_y1 - bg_y0 - text_h) / 2

            # draw text with stroke (uses your existing helper so stroke color/size apply)
            self.draw_text_with_stroke(blended, label_text, label_font, (text_x, text_y),
                                      self.text_colors['label'], stroke_key='label')






    def save_full_resolution(self):
        """Run full-res pipeline and open Save As dialog; logs errors."""
        if not self.Image1_path or not self.Image2_path:
            self.log("Save: both images required.")
            return
        self.progress_bar.setValue(0)
        QApplication.processEvents()
        try:
            # Load full-res images and crop/resize to target 1280x720
            img1 = Image.open(self.Image1_path).convert("RGB")
            img2 = Image.open(self.Image2_path).convert("RGB")
            target = (1280, 720)
            img1 = self.crop_to_aspect_ratio(img1).resize(target, Image.Resampling.LANCZOS)
            img2 = self.crop_to_aspect_ratio(img2).resize(target, Image.Resampling.LANCZOS)
            self.progress_bar.setValue(15); QApplication.processEvents()

            # apply enhancements
            img1 = self.apply_enhancements(img1, self.left_sat_slider["slider"].value(), self.left_con_slider["slider"].value())
            img2 = self.apply_enhancements(img2, self.right_sat_slider["slider"].value(), self.right_con_slider["slider"].value())
            self.progress_bar.setValue(35); QApplication.processEvents()

            # shift
            img1 = self.shift_image(img1, self.left_shift_slider["slider"].value(), "left")
            img2 = self.shift_image(img2, self.right_shift_slider["slider"].value(), "right")
            self.progress_bar.setValue(50); QApplication.processEvents()

            # blend at middle (same logic)
            w,h = img1.size
            fade_ratio = 0.12
            fade_w = int(w * fade_ratio)
            mid = w // 2
            left_edge, right_edge = mid - fade_w // 2, mid + fade_w // 2
            x = np.arange(w)
            mask_cols = np.zeros_like(x, dtype=np.float32)
            mask_cols[:left_edge] = 255
            if right_edge>left_edge:
                grad = 1 - ((x[left_edge:right_edge] - left_edge) / (right_edge - left_edge))
                mask_cols[left_edge:right_edge] = grad * 255
            mask = np.tile(mask_cols, (h,1)).astype(np.uint8)
            mask_img = Image.fromarray(mask).filter(ImageFilter.GaussianBlur(radius=max(1, fade_w//8)))
            blended = Image.composite(img1, img2, mask_img).convert("RGBA")
            self.progress_bar.setValue(65); QApplication.processEvents()

            # gradient
            self.draw_gradient(blended, self.gradient_color, self.gradient_size_slider["slider"].value())
            self.progress_bar.setValue(75); QApplication.processEvents()

            # font loading (use font file path selected in combobox)
            font_path = self.font_selection_combobox.currentData()
            # We'll create per-text fonts now using the user's size settings
            try:
                if font_path and os.path.exists(font_path):
                    # create a default font object for fallback use
                    default_font = ImageFont.truetype(font_path, size=max(8, int(self.text_settings['top']['size'])))
                else:
                    default_font = ImageFont.truetype(os.path.join(self._font_dir, "arial.ttf"), size=max(8, int(self.text_settings['top']['size'])))
            except Exception as e:
                self.log(f"Full-res font load error: {e} - using default")
                default_font = ImageFont.load_default()

            self.progress_bar.setValue(85); QApplication.processEvents()

            # texts
            top_text = self.prepare_rtl_text(self.top_text_input.text())
            bottom_text = self.prepare_rtl_text(self.bottom_text_input.text())
            username = self.prepare_rtl_text(self.username_input.text())
            label_text = self.prepare_rtl_text(self.label_input.text())

            # draw full-res texts using same safe approach as preview but with per-text sizes and safe spacing
            self.draw_all_texts(blended, default_font, top_text, bottom_text, username, label_text)
            self.progress_bar.setValue(95); QApplication.processEvents()

            # Save as dialog (must not overwrite automatically)
            suggested = os.path.join(os.path.dirname(self.Image1_path) or ".", "thumbnail_output.jpg")
            save_path, _ = QFileDialog.getSaveFileName(self, "Save Thumbnail As", suggested, "JPEG Files (*.jpg)")
            if save_path:
                # If exists, QFileDialog will warn user normally; we just save
                blended.convert("RGB").save(save_path, "JPEG", quality=92)
                self.log(f"Saved thumbnail: {save_path}")
            else:
                self.log("Save cancelled.")
            self.progress_bar.setValue(100)
            QApplication.processEvents()
        except Exception as e:
            self.log(f"Save error: {e}")
            self.progress_bar.setValue(0)

    # -------------------- Image helper functions (keep your original logic) --------------------
    def apply_enhancements(self, img, saturation, contrast):
        sat_factor = 1.0 + (saturation - 100) / 100.0
        con_factor = 1.0 + (contrast - 100) / 100.0
        img = ImageEnhance.Color(img).enhance(sat_factor)
        img = ImageEnhance.Contrast(img).enhance(con_factor)
        return img

    def shift_image(self, img, shift_percent, direction):
        w, h = img.size
        shift_px = int(w * (shift_percent / 100.0))
        new_img = Image.new("RGB", (w, h), (0, 0, 0))
        if direction == "left":
            new_img.paste(img, (-shift_px, 0))
        else:
            new_img.paste(img, (shift_px, 0))
        return new_img

    def crop_to_aspect_ratio(self, img, target_ratio=16/9):
        w,h = img.size
        ratio = w/h
        if ratio > target_ratio:
            new_w = int(h * target_ratio)
            left = (w - new_w)//2
            img = img.crop((left,0,left+new_w,h))
        else:
            new_h = int(w/target_ratio)
            top = (h - new_h)//2
            img = img.crop((0,top,w,top+new_h))
        return img

    def draw_gradient(self, image, color, height_percent):
        width, height = image.size
        grad_height = int(height * (height_percent / 100))
        if grad_height <= 0:
            return
        gradient = Image.new("RGBA", image.size, (0,0,0,0))
        draw = ImageDraw.Draw(gradient)
        for y in range(height - grad_height, height):
            alpha = int(255 * ((y - (height - grad_height))/grad_height))
            draw.line([(0,y),(width,y)], fill=color+(alpha,))
        image.alpha_composite(gradient)

    def draw_all_texts(self, blended, base_font, top_text, bottom_text, username, label_text):
        """Full-res text drawing — uses per-text sizes and measured bounding boxes to avoid overlap.
           Label background is sized tightly to the label text."""
        draw = ImageDraw.Draw(blended)
        w, h = blended.size
        right_margin = int(w * 0.09)

        # Create per-text fonts (try chosen system font path; fallback to base_font)
        font_path = self.font_selection_combobox.currentData()
        def make_font_for_key(key):
            try:
                sz = max(8, int(self.text_settings[key]['size']))
                if font_path and os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size=sz)
                else:
                    # try arial from windows fonts as fallback
                    return ImageFont.truetype(os.path.join(self._font_dir, "arial.ttf"), size=sz)
            except Exception:
                # final fallback to passed base_font
                return base_font

        top_font = make_font_for_key('top')
        bottom_font = make_font_for_key('bottom')
        username_font = make_font_for_key('username')
        label_font = make_font_for_key('label')

        # Measure text bboxes
        top_bbox = draw.textbbox((0,0), top_text, font=top_font) if top_text else (0,0,0,0)
        top_h = top_bbox[3] - top_bbox[1]
        bottom_bbox = draw.textbbox((0,0), bottom_text, font=bottom_font) if bottom_text else (0,0,0,0)
        bottom_h = bottom_bbox[3] - bottom_bbox[1]

        # spacing based on font sizes
        spacing = max(8, int((top_font.size + bottom_font.size) * 0.06)) if hasattr(top_font, 'size') else 10

        bottom_padding = int(h * 0.065)
        bottom_y = h - bottom_padding - bottom_h

        if top_text and bottom_text:
            top_y = bottom_y - spacing - top_h
            if top_y < 6:
                top_y = 6
        elif top_text:
            top_y = h - bottom_padding - top_h - 6
        else:
            top_y = None

        # Draw top text (right aligned)
        if top_text:
            bbox = draw.textbbox((0,0), top_text, font=top_font)
            text_w = bbox[2]-bbox[0]
            x_pos = max(right_margin, w - right_margin - text_w)
            self.draw_text_with_stroke(blended, top_text, top_font, (x_pos, int(top_y)), self.text_colors['top'], stroke_key='top')

        # Draw bottom text (right aligned)
        if bottom_text:
            bbox_b = draw.textbbox((0,0), bottom_text, font=bottom_font)
            text_w = bbox_b[2]-bbox_b[0]
            x_pos_b = max(right_margin, w - right_margin - text_w)
            self.draw_text_with_stroke(blended, bottom_text, bottom_font, (x_pos_b, int(bottom_y)), self.text_colors['bottom'], stroke_key='bottom')

        # Username: top-right
        if username:
            bbox_u = draw.textbbox((0,0), username, font=username_font)
            text_w = bbox_u[2]-bbox_u[0]
            pos = (w - text_w - 40, 30)
            self.draw_text_with_stroke(blended, username, username_font, pos, self.text_colors['username'], stroke_key='username')

        # Label: tight background roughly the size of text + small paddings

        if label_text:
            # Font and bbox
            bbox_l = draw.textbbox((0,0), label_text, font=label_font)
            text_w = bbox_l[2]-bbox_l[0]
            text_h = bbox_l[3]-bbox_l[1]

            pad_x = max(4, int(self.text_settings['label']['size'] * 0.14))
            pad_y = max(4, int(self.text_settings['label']['size'] * 0.30))

            # position
            x, y = 10, 70  # keep this as your label position
            bg_rect = (x - pad_x, y - pad_y, x + text_w + pad_x, y + text_h + pad_y)

            # draw background rectangle
            draw.rectangle(bg_rect, fill=(0, 0, 180, 200))

            # draw text inside rectangle with stroke
            self.draw_text_with_stroke(blended, label_text, label_font, (x, y),
                                       self.text_colors['label'], stroke_key='label')


    def draw_text_with_stroke(self,image,text,font,pos,fill,stroke_key=None):
        x,y = pos
        draw = ImageDraw.Draw(image)
        # pull stroke thickness and color from text_settings if stroke_key provided
        if stroke_key and stroke_key in self.text_settings:
            stroke_thick = int(self.text_settings[stroke_key].get('stroke', 2))
            sc = self.text_settings[stroke_key].get('stroke_color', (0,0,0,255))
            # ensure stroke_color is RGBA
            if len(sc) == 3:
                stroke_color = (sc[0], sc[1], sc[2], 255)
            else:
                stroke_color = sc
        else:
            stroke_thick = 2
            stroke_color = (0,0,0,255)
        # Draw stroke by drawing text shifted in a grid
        for dx in range(-stroke_thick, stroke_thick+1):
            for dy in range(-stroke_thick, stroke_thick+1):
                if dx==0 and dy==0: continue
                draw.text((x+dx,y+dy), text, font=font, fill=stroke_color)
        # main text
        draw.text((x,y), text, font=font, fill=fill)


# -------------------- Run --------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = HalfFadeBlend()
    w.show()
    sys.exit(app.exec())
