# main.py (增强版)
import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
from PIL import Image, ImageTk, ImageDraw, ImageFont

# 可选：tkinterdnd2 支持拖拽（若未安装则忽略）
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except Exception:
    DND_AVAILABLE = False

SUPPORTED_INPUT_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif")

# 配置文件（模板与上次设置）路径
DATA_PATH = os.path.join(os.path.expanduser("~"), ".watermarker_data.json")


class WatermarkerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("批量水印工具 (Tkinter)")

        # --- 图片与预览相关 ---
        self.images = []          # 图片路径列表
        self.thumbs = []          # 缩略图 PhotoImage 列表 (保持引用)
        self.thumb_items = []     # 缩略图在 canvas 上的 item id 列表
        self.current_index = None
        self.preview_tk = None
        self.orig_image = None    # 当前选中图片的 PIL.Image (RGBA)
        self.preview_image = None # 当前显示的缩放后 PIL.Image

        # 画布尺寸
        self.canvas_w = 800
        self.canvas_h = 500

        # 拖拽控制（用于移动水印）
        self.dragging = False

        # --- 水印参数（可保存为模板） ---
        self.wm_type = tk.StringVar(value="text")  # text or image

        # 文本水印
        self.watermark_text = tk.StringVar(value="示例水印")
        self.font_size = tk.IntVar(value=36)
        self.font_color = "#FF0000"
        self.font_file = ""   # 可选 ttf 字体文件路径
        self.rotation = tk.IntVar(value=0)
        self.add_shadow = tk.BooleanVar(value=True)

        # 图片水印
        self.wm_image_path = ""
        self.wm_image_tk = None
        self.wm_image = None
        self.wm_image_scale = tk.IntVar(value=30)  # 百分比相对原图宽度或特定比例
        self.wm_image_opacity = tk.IntVar(value=80)  # 0-100

        # 位置
        self.position = tk.StringVar(value="center")  # nine-grid + custom
        self.custom_x = 0.5  # 0-1 relative
        self.custom_y = 0.5

        # 透明度（文本统一使用此值，图片水印也有单独调节）
        self.opacity = tk.DoubleVar(value=0.6)   # 0.0 - 1.0

        # 导出设置
        self.out_format = tk.StringVar(value="JPEG")  # JPEG或PNG
        self.name_rule = tk.StringVar(value="prefix") # keep, prefix, suffix
        self.prefix = tk.StringVar(value="wm_")
        self.suffix = tk.StringVar(value="_watermarked")
        self.jpeg_quality = tk.IntVar(value=90)

        # 导出缩放设置
        self.export_scale_mode = tk.StringVar(value="original")  # original / percent
        self.export_scale_percent = tk.IntVar(value=100)

        # 模板数据（内存）
        self.templates = {}  # name -> settings dict

        # 构建UI
        self.build_ui()

        # 尝试加载上次设置/模板
        self.load_data()
        # 确保 UI 完整渲染后更新（首次显示 canvas）
        self.root.update_idletasks()

        # 退出时保存设置
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- UI 构建 ----------------
    def build_ui(self):
        # 左侧：缩略图 + 文件列表
        left = tk.Frame(self.root, width=260)
        left.pack(side=tk.LEFT, fill=tk.Y)

        # 缩略图横向滚动区域（放在上方）
        thumb_frame = tk.Frame(left, height=140)
        thumb_frame.pack(fill=tk.X, padx=4, pady=4)
        self.thumb_canvas = tk.Canvas(thumb_frame, height=120)
        self.thumb_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        hbar = tk.Scrollbar(thumb_frame, orient=tk.HORIZONTAL, command=self.thumb_canvas.xview)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.thumb_canvas.configure(xscrollcommand=hbar.set)
        self.thumb_inner = tk.Frame(self.thumb_canvas)
        self.thumb_window = self.thumb_canvas.create_window((0, 0), window=self.thumb_inner, anchor="nw")
        self.thumb_inner.bind("<Configure>", lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all")))

        # 下方：文件操作按钮与列表
        btn_frame = tk.Frame(left)
        btn_frame.pack(fill=tk.X, padx=6, pady=6)
        tk.Button(btn_frame, text="导入文件", command=self.import_files).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="导入文件夹", command=self.import_folder).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="移除选中", command=self.remove_selected).pack(side=tk.LEFT, padx=2)

        # 文件名列表
        self.listbox = tk.Listbox(left)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self.on_select())

        # 支持拖拽导入（如果可用）
        if DND_AVAILABLE:
            try:
                # 如果使用 tkinterdnd2，需要把 root 换成 TkinterDnD.Tk()
                # 但我们这里只是尝试把 listbox、thumb canvas 注册为 drop target
                self.thumb_canvas.drop_target_register(DND_FILES)
                self.thumb_canvas.dnd_bind("<<Drop>>", self._on_dnd)
                self.listbox.drop_target_register(DND_FILES)
                self.listbox.dnd_bind("<<Drop>>", self._on_dnd)
            except Exception:
                pass

        # 右侧：预览 + 可滚动控件区
        right = tk.Frame(self.root)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 预览区
        preview_frame = tk.Frame(right, bd=2, relief=tk.SUNKEN)
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.canvas = tk.Canvas(preview_frame, width=self.canvas_w, height=self.canvas_h, bg="#333333")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        # 绑定拖拽事件（用于移动水印）
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        # 控件区：使用 canvas + frame 实现可滚动
        ctrl_outer = tk.Frame(right)
        ctrl_outer.pack(fill=tk.BOTH, expand=False, padx=6, pady=4)
        ctrl_canvas = tk.Canvas(ctrl_outer, height=260)  # 可视高度
        ctrl_scroll = tk.Scrollbar(ctrl_outer, orient=tk.VERTICAL, command=ctrl_canvas.yview)
        ctrl_canvas.configure(yscrollcommand=ctrl_scroll.set)
        ctrl_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        ctrl_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.ctrl_frame = tk.Frame(ctrl_canvas)
        self.ctrl_window = ctrl_canvas.create_window((0, 0), window=self.ctrl_frame, anchor="nw")
        self.ctrl_frame.bind("<Configure>", lambda e: ctrl_canvas.configure(scrollregion=ctrl_canvas.bbox("all")))

        # -------- 控件内容放到 self.ctrl_frame 中 --------
        # 水印类型选择
        type_row = tk.Frame(self.ctrl_frame)
        type_row.pack(fill=tk.X, pady=4)
        tk.Label(type_row, text="水印类型:").pack(side=tk.LEFT)
        tk.Radiobutton(type_row, text="文本", variable=self.wm_type, value="text", command=self.update_preview).pack(side=tk.LEFT)
        tk.Radiobutton(type_row, text="图片", variable=self.wm_type, value="image", command=self.update_preview).pack(side=tk.LEFT)

        # 文本水印组
        text_group = tk.LabelFrame(self.ctrl_frame, text="文本水印设置")
        text_group.pack(fill=tk.X, pady=4, padx=2)

        row1 = tk.Frame(text_group)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="水印文本:").pack(side=tk.LEFT)
        ent = tk.Entry(row1, textvariable=self.watermark_text)
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ent.bind("<KeyRelease>", lambda e: self.update_preview())

        row2 = tk.Frame(text_group)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="字号:").pack(side=tk.LEFT)
        font_slider = tk.Scale(row2, from_=8, to=300, orient=tk.HORIZONTAL, variable=self.font_size, command=lambda e: self.update_preview())
        font_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        row3 = tk.Frame(text_group)
        row3.pack(fill=tk.X, pady=2)
        tk.Button(row3, text="选择颜色", command=self.choose_color).pack(side=tk.LEFT)
        tk.Label(row3, text="透明度:").pack(side=tk.LEFT, padx=6)
        op = tk.Scale(row3, from_=0, to=100, orient=tk.HORIZONTAL, command=lambda v: (self.opacity.set(float(v)/100.0), self.update_preview()))
        op.set(int(self.opacity.get()*100))
        op.pack(side=tk.LEFT, fill=tk.X, expand=True)

        row4 = tk.Frame(text_group)
        row4.pack(fill=tk.X, pady=2)
        tk.Label(row4, text="旋转(°):").pack(side=tk.LEFT)
        rot = tk.Scale(row4, from_=-180, to=180, orient=tk.HORIZONTAL, variable=self.rotation, command=lambda e: self.update_preview())
        rot.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        tk.Checkbutton(row4, text="阴影/描边增强", variable=self.add_shadow, command=self.update_preview).pack(side=tk.LEFT, padx=6)

        row5 = tk.Frame(text_group)
        row5.pack(fill=tk.X, pady=2)
        tk.Label(row5, text="字体文件(.ttf 可选):").pack(side=tk.LEFT)
        tk.Button(row5, text="选择字体", command=self.choose_font_file).pack(side=tk.LEFT, padx=4)
        self.font_label = tk.Label(row5, text="(使用系统默认字体)")
        self.font_label.pack(side=tk.LEFT, padx=6)

        # 图片水印组
        img_group = tk.LabelFrame(self.ctrl_frame, text="图片水印设置")
        img_group.pack(fill=tk.X, pady=4, padx=2)

        rowi1 = tk.Frame(img_group)
        rowi1.pack(fill=tk.X, pady=2)
        tk.Button(rowi1, text="选择水印图片", command=self.choose_wm_image).pack(side=tk.LEFT)
        self.wm_img_label = tk.Label(rowi1, text="未选择")
        self.wm_img_label.pack(side=tk.LEFT, padx=6)

        rowi2 = tk.Frame(img_group)
        rowi2.pack(fill=tk.X, pady=2)
        tk.Label(rowi2, text="缩放(%):").pack(side=tk.LEFT)
        tk.Scale(rowi2, from_=5, to=200, orient=tk.HORIZONTAL, variable=self.wm_image_scale, command=lambda e: self.update_preview()).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(rowi2, text="透明(%)").pack(side=tk.LEFT, padx=6)
        tk.Scale(rowi2, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.wm_image_opacity, command=lambda e: self.update_preview()).pack(side=tk.LEFT)

        # 位置选项（九宫格 + custom）
        pos_row = tk.Frame(self.ctrl_frame)
        pos_row.pack(fill=tk.X, pady=4)
        tk.Label(pos_row, text="位置:").pack(side=tk.LEFT)
        pos_menu = tk.OptionMenu(pos_row, self.position,
                                 "topleft", "topcenter", "topright",
                                 "centerleft", "center", "centerright",
                                 "bottomleft", "bottomcenter", "bottomright",
                                 "custom", command=lambda e: self.update_preview())
        pos_menu.pack(side=tk.LEFT, padx=6)
        tk.Button(pos_row, text="重置为中心", command=self.reset_position).pack(side=tk.LEFT, padx=6)

        # 模板管理
        tpl_frame = tk.LabelFrame(self.ctrl_frame, text="模板管理")
        tpl_frame.pack(fill=tk.X, pady=4, padx=2)
        self.tpl_var = tk.StringVar(value="")
        tpl_row = tk.Frame(tpl_frame)
        tpl_row.pack(fill=tk.X, pady=2)
        self.tpl_menu = tk.OptionMenu(tpl_row, self.tpl_var, ())
        self.tpl_menu.pack(side=tk.LEFT, padx=4)
        tk.Button(tpl_row, text="加载", command=self.load_template).pack(side=tk.LEFT, padx=4)
        tk.Button(tpl_row, text="保存当前为模板", command=self.save_template).pack(side=tk.LEFT, padx=4)
        tk.Button(tpl_row, text="删除模板", command=self.delete_template).pack(side=tk.LEFT, padx=4)

        # 导出设置
        exp = tk.LabelFrame(self.ctrl_frame, text="导出设置")
        exp.pack(fill=tk.X, pady=4, padx=2)

        fmt_frame = tk.Frame(exp)
        fmt_frame.pack(fill=tk.X, pady=2)
        tk.Label(fmt_frame, text="格式:").pack(side=tk.LEFT, padx=4)
        tk.OptionMenu(fmt_frame, self.out_format, "JPEG", "PNG").pack(side=tk.LEFT)
        tk.Label(fmt_frame, text="JPEG质量:").pack(side=tk.LEFT, padx=6)
        q = tk.Scale(fmt_frame, from_=10, to=100, orient=tk.HORIZONTAL, variable=self.jpeg_quality)
        q.pack(side=tk.LEFT)

        name_frame = tk.Frame(exp)
        name_frame.pack(fill=tk.X, pady=2)
        tk.Radiobutton(name_frame, text="添加前缀", variable=self.name_rule, value="prefix").pack(side=tk.LEFT)
        tk.Radiobutton(name_frame, text="添加后缀", variable=self.name_rule, value="suffix").pack(side=tk.LEFT)
        tk.Radiobutton(name_frame, text="保留原名", variable=self.name_rule, value="keep").pack(side=tk.LEFT)
        tk.Label(name_frame, text="前缀:").pack(side=tk.LEFT, padx=4)
        tk.Entry(name_frame, textvariable=self.prefix, width=12).pack(side=tk.LEFT)
        tk.Label(name_frame, text="后缀:").pack(side=tk.LEFT, padx=4)
        tk.Entry(name_frame, textvariable=self.suffix, width=12).pack(side=tk.LEFT)

        scale_frame = tk.Frame(exp)
        scale_frame.pack(fill=tk.X, pady=2)
        tk.Radiobutton(scale_frame, text="保持原尺寸", variable=self.export_scale_mode, value="original").pack(side=tk.LEFT)
        tk.Radiobutton(scale_frame, text="按百分比缩放", variable=self.export_scale_mode, value="percent").pack(side=tk.LEFT)
        tk.Label(scale_frame, text="比例%:").pack(side=tk.LEFT, padx=4)
        tk.Entry(scale_frame, textvariable=self.export_scale_percent, width=6).pack(side=tk.LEFT)

        # 导出按钮区
        export_row = tk.Frame(self.ctrl_frame)
        export_row.pack(fill=tk.X, padx=6, pady=6)
        tk.Button(export_row, text="导出全部图片", command=self.export_images, bg="#4caf50", fg="white").pack(side=tk.RIGHT, padx=4)
        tk.Button(export_row, text="导出选中图片", command=self.export_selected_image).pack(side=tk.RIGHT)

    # ----------------- 拖拽（tkinterdnd2）回调 -----------------
    def _on_dnd(self, event):
        # event.data 可能是空格/回车分隔的文件路径
        try:
            data = event.data
            # tkinterdnd 在 windows 上通常返回 '{C:\path\to\file} {C:\path\to\file2}'
            paths = self.root.splitlist(data)
            for p in paths:
                if p and p.lower().endswith(SUPPORTED_INPUT_EXT):
                    self._add_image_path(p)
            self.refresh_thumbnails()
        except Exception as e:
            print("DND 解析错误:", e)

    # ---------------- 文件导入 / 列表操作 ----------------
    def import_files(self):
        fpaths = filedialog.askopenfilenames(title="选择图片文件", filetypes=[("图片文件", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff")])
        if not fpaths:
            return
        for p in fpaths:
            self._add_image_path(p)
        self.refresh_thumbnails()

    def import_folder(self):
        folder = filedialog.askdirectory(title="选择图片文件夹")
        if not folder:
            return
        for fname in sorted(os.listdir(folder)):
            if fname.lower().endswith(SUPPORTED_INPUT_EXT):
                self._add_image_path(os.path.join(folder, fname))
        self.refresh_thumbnails()

    def _add_image_path(self, path):
        if path in self.images:
            return
        if not os.path.isfile(path):
            return
        self.images.append(path)
        self.listbox.insert(tk.END, os.path.basename(path))
        try:
            im = Image.open(path).convert("RGBA")
            thumb = im.copy()
            thumb.thumbnail((100, 100), Image.LANCZOS)
            tkimg = ImageTk.PhotoImage(thumb)
            self.thumbs.append(tkimg)
        except Exception as e:
            print("生成缩略图失败:", e)
            # 用占位图
            placeholder = Image.new("RGBA", (100, 80), (200, 200, 200, 255))
            tkimg = ImageTk.PhotoImage(placeholder)
            self.thumbs.append(tkimg)

    def refresh_thumbnails(self):
        # 清理旧的 thumbnail widgets
        for widget in self.thumb_inner.winfo_children():
            widget.destroy()
        self.thumb_items.clear()

        for idx, tkimg in enumerate(self.thumbs):
            frm = tk.Frame(self.thumb_inner, bd=1, relief=tk.RAISED)
            lbl = tk.Label(frm, image=tkimg)
            lbl.image = tkimg
            lbl.pack()
            name = tk.Label(frm, text=os.path.basename(self.images[idx]), wraplength=100)
            name.pack()
            frm.pack(side=tk.LEFT, padx=4, pady=4)
            # 点击缩略图选中
            frm.bind("<Button-1>", lambda e, i=idx: self._select_index(i))
            lbl.bind("<Button-1>", lambda e, i=idx: self._select_index(i))
            name.bind("<Button-1>", lambda e, i=idx: self._select_index(i))
            self.thumb_items.append(frm)
        # 更新 canvas scrollregion
        self.thumb_canvas.update_idletasks()
        bbox = self.thumb_canvas.bbox("all")
        if bbox:
            self.thumb_canvas.configure(scrollregion=bbox)

    def _select_index(self, idx):
        # 让 listbox 也选中
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self.on_select()

    def remove_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.listbox.delete(idx)
        try:
            del self.images[idx]
            del self.thumbs[idx]
        except:
            pass
        self.refresh_thumbnails()
        # reset selection
        self.current_index = None
        self.orig_image = None
        self.canvas.delete("all")

    def on_select(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.current_index = idx
        path = self.images[idx]
        try:
            img = Image.open(path).convert("RGBA")
            self.orig_image = img
        except Exception as e:
            messagebox.showerror("错误", f"无法打开图片: {e}")
            return
        # 重置自定义位置为中心（保持 position setting unless custom）
        if self.position.get() != "custom":
            self.reset_position(apply_preview=False)
        self.update_preview()

    # ---------------- 水印绘制与预览 ----------------
    def choose_color(self):
        c = colorchooser.askcolor(title="选择水印颜色")
        if c and c[1]:
            self.font_color = c[1]
            self.update_preview()

    def choose_font_file(self):
        path = filedialog.askopenfilename(title="选择字体文件 (.ttf)", filetypes=[("TrueType 字体", "*.ttf"), ("All files", "*.*")])
        if path:
            self.font_file = path
            self.font_label.config(text=os.path.basename(path))
            self.update_preview()

    def choose_wm_image(self):
        path = filedialog.askopenfilename(title="选择水印图像 (PNG 推荐)", filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff")])
        if not path:
            return
        try:
            im = Image.open(path).convert("RGBA")
            self.wm_image_path = path
            self.wm_image = im
            self.wm_img_label.config(text=os.path.basename(path))
            # 缩一张小图用于 UI
            thumb = im.copy()
            thumb.thumbnail((60, 60), Image.LANCZOS)
            self.wm_image_tk = ImageTk.PhotoImage(thumb)
            self.update_preview()
        except Exception as e:
            messagebox.showerror("错误", f"无法打开水印图片: {e}")

    def reset_position(self, apply_preview=True):
        self.custom_x = 0.5
        self.custom_y = 0.5
        self.position.set("center")
        if apply_preview:
            self.update_preview()

    def on_position_change(self):
        self.update_preview()

    def on_canvas_click(self, event):
        # 点击图片区域开始拖拽
        if not self.preview_image:
            return
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        img_w, img_h = self.preview_image.size
        img_x = (canvas_w - img_w) // 2
        img_y = (canvas_h - img_h) // 2

        if img_x <= event.x <= img_x + img_w and img_y <= event.y <= img_y + img_h:
            self.dragging = True
            self.position.set("custom")
            rel_x = (event.x - img_x) / img_w
            rel_y = (event.y - img_y) / img_h
            self.custom_x = min(max(rel_x, 0.0), 1.0)
            self.custom_y = min(max(rel_y, 0.0), 1.0)
            self.update_preview()

    def on_canvas_drag(self, event):
        if not self.dragging or not self.preview_image:
            return
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        img_w, img_h = self.preview_image.size
        img_x = (canvas_w - img_w) // 2
        img_y = (canvas_h - img_h) // 2
        rel_x = (event.x - img_x) / img_w
        rel_y = (event.y - img_y) / img_h
        self.custom_x = min(max(rel_x, 0.0), 1.0)
        self.custom_y = min(max(rel_y, 0.0), 1.0)
        self.update_preview()

    def on_canvas_release(self, event):
        self.dragging = False

    def update_preview(self):
        # 更新预览图（缩放后在 canvas 中显示）
        if self.current_index is None or self.orig_image is None:
            self.canvas.delete("all")
            return

        img = self.orig_image.copy()
        img_w, img_h = img.size
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        scale = min(cw / img_w, ch / img_h, 1.0)
        disp_w = int(img_w * scale)
        disp_h = int(img_h * scale)
        self.preview_image = img.resize((disp_w, disp_h), Image.LANCZOS)

        # 在缩放后的图片上绘制水印（用于预览）
        preview_with_wm = self._apply_watermark_to_image(self.preview_image, for_preview=True)
        self.preview_tk = ImageTk.PhotoImage(preview_with_wm)
        self.canvas.delete("all")
        x = cw // 2
        y = ch // 2
        self.canvas.create_image(x, y, image=self.preview_tk, anchor=tk.CENTER)
        pos_str = f"位置: {self.position.get()}"
        self.canvas.create_text(8, 8, text=pos_str, anchor=tk.NW, fill="white", font=("Arial", 10))

    def _apply_watermark_to_image(self, pil_img, for_preview=False):
        """
        在传入的 PIL RGBA 图像上绘制文本或图片水印并返回新的图像。
        - if for_preview=True: pil_img 是缩放后的显示图（RGBA）
        - 若 for_preview=False: pil_img 通常为原始尺寸图（RGBA）
        """
        # 确保 RGBA
        if pil_img.mode != "RGBA":
            base = pil_img.convert("RGBA")
        else:
            base = pil_img.copy()

        w, h = base.size
        txt_layer = Image.new("RGBA", (w, h), (255, 255, 255, 0))

        # 选择渲染哪种水印
        if self.wm_type.get() == "text":
            txt = self.watermark_text.get()
            if not txt:
                return base

            # 计算字体大小：当是预览时按比例缩放字体大小（保持近似视觉）
            font_size = max(8, int(self.font_size.get() * (0.6 if for_preview else 1.0)))
            # 尝试加载字体
            font = None
            if self.font_file:
                try:
                    font = ImageFont.truetype(self.font_file, font_size)
                except Exception:
                    font = None
            if font is None:
                # 优先尝试常见系统字体
                for name in ("arial.ttf", "DejaVuSans.ttf", "NotoSansCJK-Regular.ttc"):
                    try:
                        font = ImageFont.truetype(name, font_size)
                        break
                    except Exception:
                        font = None
                if font is None:
                    font = ImageFont.load_default()

            # 计算文本大小（兼容不同 Pillow 版本）
            try:
                # 使用临时 draw 获取 bbox
                tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
                dtmp = ImageDraw.Draw(tmp)
                bbox = dtmp.textbbox((0, 0), txt, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except Exception:
                try:
                    text_w, text_h = font.getsize(txt)
                except Exception:
                    text_w, text_h = (100, 20)

            # 创建单独的图层绘制文本（以便旋转）
            padding = int(max(4, font.size * 0.2))
            text_img = Image.new("RGBA", (text_w + padding * 2, text_h + padding * 2), (255, 255, 255, 0))
            d = ImageDraw.Draw(text_img)

            # 颜色与 alpha
            try:
                r, g, b = self.root.winfo_rgb(self.font_color)
                r, g, b = r // 256, g // 256, b // 256
            except Exception:
                r, g, b = (255, 0, 0)
            alpha = int(max(0.0, min(1.0, self.opacity.get())) * 255)
            fill = (r, g, b, alpha)

            # 绘制阴影/描边（如果选中）
            if self.add_shadow.get():
                shadow_offset = max(1, int(font.size * 0.06))
                shadow_color = (0, 0, 0, int(alpha * 0.6))
                d.text((padding + shadow_offset, padding + shadow_offset), txt, font=font, fill=shadow_color)
            d.text((padding, padding), txt, font=font, fill=fill)

            # 旋转文本层
            angle = self.rotation.get()
            if angle != 0:
                text_img = text_img.rotate(angle, expand=1, resample=Image.BICUBIC)

            # 将 text_img 粘贴到 txt_layer 的相对位置
            tx_w, tx_h = text_img.size

            pos_mode = self.position.get()
            padding_edge = 10
            if pos_mode == "topleft":
                pos = (padding_edge, padding_edge)
            elif pos_mode == "topcenter":
                pos = ((w - tx_w) // 2, padding_edge)
            elif pos_mode == "topright":
                pos = (w - tx_w - padding_edge, padding_edge)
            elif pos_mode == "centerleft":
                pos = (padding_edge, (h - tx_h) // 2)
            elif pos_mode == "center":
                pos = ((w - tx_w) // 2, (h - tx_h) // 2)
            elif pos_mode == "centerright":
                pos = (w - tx_w - padding_edge, (h - tx_h) // 2)
            elif pos_mode == "bottomleft":
                pos = (padding_edge, h - tx_h - padding_edge)
            elif pos_mode == "bottomcenter":
                pos = ((w - tx_w) // 2, h - tx_h - padding_edge)
            elif pos_mode == "bottomright":
                pos = (w - tx_w - padding_edge, h - tx_h - padding_edge)
            else:  # custom
                cx = int(self.custom_x * w)
                cy = int(self.custom_y * h)
                pos = (int(cx - tx_w // 2), int(cy - tx_h // 2))

            # 粘贴带 alpha 的 text_img 到 txt_layer
            txt_layer.paste(text_img, pos, text_img)
            out = Image.alpha_composite(base, txt_layer)
            return out

        else:
            # 图片水印
            if not self.wm_image:
                return base
            # 计算目标水印大小：使用 wm_image_scale as % of base width (for preview use scaled)
            scale_pct = self.wm_image_scale.get()
            target_w = max(1, int(w * (scale_pct / 100.0)))
            # 保持纵横比
            iw, ih = self.wm_image.size
            new_h = max(1, int(iw and (target_w * ih / iw) or target_w))
            wm_resized = self.wm_image.resize((target_w, new_h), Image.LANCZOS)

            # 应用 opacity（独立于整体透明度）
            opacity_pct = self.wm_image_opacity.get() / 100.0
            # 将 wm_resized 的 alpha 通道按比例调整
            if wm_resized.mode != "RGBA":
                wm_resized = wm_resized.convert("RGBA")
            alpha_chan = wm_resized.split()[-1].point(lambda p: int(p * opacity_pct))
            wm_resized.putalpha(alpha_chan)

            # 计算位置（将 watermark 居中放置其 bounding box）
            tx_w, tx_h = wm_resized.size
            pos_mode = self.position.get()
            padding_edge = 10
            if pos_mode == "topleft":
                pos = (padding_edge, padding_edge)
            elif pos_mode == "topcenter":
                pos = ((w - tx_w) // 2, padding_edge)
            elif pos_mode == "topright":
                pos = (w - tx_w - padding_edge, padding_edge)
            elif pos_mode == "centerleft":
                pos = (padding_edge, (h - tx_h) // 2)
            elif pos_mode == "center":
                pos = ((w - tx_w) // 2, (h - tx_h) // 2)
            elif pos_mode == "centerright":
                pos = (w - tx_w - padding_edge, (h - tx_h) // 2)
            elif pos_mode == "bottomleft":
                pos = (padding_edge, h - tx_h - padding_edge)
            elif pos_mode == "bottomcenter":
                pos = ((w - tx_w) // 2, h - tx_h - padding_edge)
            elif pos_mode == "bottomright":
                pos = (w - tx_w - padding_edge, h - tx_h - padding_edge)
            else:
                cx = int(self.custom_x * w)
                cy = int(self.custom_y * h)
                pos = (int(cx - tx_w // 2), int(cy - tx_h // 2))

            txt_layer.paste(wm_resized, pos, wm_resized)
            out = Image.alpha_composite(base, txt_layer)
            return out

    # ---------------- 导出 ----------------
    def export_selected_image(self):
        if self.current_index is None:
            messagebox.showwarning("提示", "请先在列表中选择一张图片")
            return
        self._export_images([self.images[self.current_index]])

    def export_images(self):
        if not self.images:
            messagebox.showwarning("提示", "请先导入图片")
            return
        self._export_images(self.images)

    def _export_images(self, paths):
        out_dir = filedialog.askdirectory(title="选择输出文件夹（不能是原图所在文件夹，默认禁止）")
        if not out_dir:
            return

        # 检查是否与原图某个目录相同 -> 默认禁止
        for p in paths:
            if os.path.abspath(out_dir) == os.path.abspath(os.path.dirname(p)):
                messagebox.showerror("错误", "输出目录不能与任一原图所在目录相同（为防覆盖）。请选择其他目录。")
                return

        fmt = self.out_format.get().upper()
        count = 0
        errors = []
        for p in paths:
            try:
                im = Image.open(p).convert("RGBA")
                # 应用缩放（根据导出设置）
                if self.export_scale_mode.get() == "percent":
                    pct = max(1, self.export_scale_percent.get())
                    new_w = max(1, int(im.width * pct / 100.0))
                    new_h = max(1, int(im.height * pct / 100.0))
                    im = im.resize((new_w, new_h), Image.LANCZOS)

                # 在原始尺寸上应用水印（使用当前设置）
                saved_orig = self.orig_image
                self.orig_image = im
                wm_applied = self._apply_watermark_to_image(im, for_preview=False)
                self.orig_image = saved_orig

                basename = os.path.basename(p)
                name, ext = os.path.splitext(basename)
                if self.name_rule.get() == "keep":
                    out_name_base = f"{name}"
                elif self.name_rule.get() == "prefix":
                    out_name_base = f"{self.prefix.get()}{name}"
                else:
                    out_name_base = f"{name}{self.suffix.get()}"

                # 防止覆盖：如果文件存在则自动编号
                if fmt == "JPEG":
                    out_path = os.path.join(out_dir, out_name_base + ".jpg")
                    rgb = wm_applied.convert("RGB")
                    i = 1
                    final_out = out_path
                    while os.path.exists(final_out):
                        final_out = os.path.join(out_dir, f"{out_name_base}_{i}.jpg")
                        i += 1
                    rgb.save(final_out, "JPEG", quality=self.jpeg_quality.get())
                else:  # PNG
                    out_path = os.path.join(out_dir, out_name_base + ".png")
                    i = 1
                    final_out = out_path
                    while os.path.exists(final_out):
                        final_out = os.path.join(out_dir, f"{out_name_base}_{i}.png")
                        i += 1
                    wm_applied.save(final_out, "PNG")
                count += 1
            except Exception as e:
                errors.append((p, str(e)))
                print("导出失败：", p, e)

        msg = f"导出完成：{count} 张图片已保存到\n{out_dir}"
        if errors:
            msg += f"\n\n{len(errors)} 张图片导出失败（见控制台）。"
        messagebox.showinfo("导出完成", msg)

    # ---------------- 模板与设置保存 ----------------
    def save_template(self):
        name = tk.simpledialog.askstring("保存模板", "请输入模板名称：")
        if not name:
            return
        settings = self._gather_settings()
        self.templates[name] = settings
        self._save_data()
        self._refresh_tpl_menu()
        messagebox.showinfo("模板已保存", f"模板 '{name}' 已保存。")

    def load_template(self):
        name = self.tpl_var.get()
        if not name or name not in self.templates:
            messagebox.showwarning("提示", "请选择一个模板再加载")
            return
        settings = self.templates[name]
        self._apply_settings(settings)
        self.update_preview()
        messagebox.showinfo("模板已加载", f"模板 '{name}' 已加载。")

    def delete_template(self):
        name = self.tpl_var.get()
        if not name or name not in self.templates:
            messagebox.showwarning("提示", "请选择一个模板再删除")
            return
        if messagebox.askyesno("确认删除", f"确定要删除模板 '{name}' 吗？"):
            del self.templates[name]
            self._save_data()
            self._refresh_tpl_menu()

    def _gather_settings(self):
        # 将当前设置序列化为可 JSON 保存的字典
        return {
            "wm_type": self.wm_type.get(),
            "watermark_text": self.watermark_text.get(),
            "font_size": int(self.font_size.get()),
            "font_color": self.font_color,
            "font_file": self.font_file,
            "rotation": int(self.rotation.get()),
            "add_shadow": bool(self.add_shadow.get()),
            "wm_image_path": self.wm_image_path,
            "wm_image_scale": int(self.wm_image_scale.get()),
            "wm_image_opacity": int(self.wm_image_opacity.get()),
            "position": self.position.get(),
            "custom_x": float(self.custom_x),
            "custom_y": float(self.custom_y),
            "opacity": float(self.opacity.get()),
            "out_format": self.out_format.get(),
            "name_rule": self.name_rule.get(),
            "prefix": self.prefix.get(),
            "suffix": self.suffix.get(),
            "jpeg_quality": int(self.jpeg_quality.get()),
            "export_scale_mode": self.export_scale_mode.get(),
            "export_scale_percent": int(self.export_scale_percent.get()),
        }

    def _apply_settings(self, s):
        try:
            self.wm_type.set(s.get("wm_type", "text"))
            self.watermark_text.set(s.get("watermark_text", ""))
            self.font_size.set(s.get("font_size", 36))
            self.font_color = s.get("font_color", "#FF0000")
            self.font_file = s.get("font_file", "")
            self.rotation.set(s.get("rotation", 0))
            self.add_shadow.set(s.get("add_shadow", True))
            self.wm_image_path = s.get("wm_image_path", "")
            if self.wm_image_path and os.path.exists(self.wm_image_path):
                try:
                    self.wm_image = Image.open(self.wm_image_path).convert("RGBA")
                    thumb = self.wm_image.copy()
                    thumb.thumbnail((60, 60), Image.LANCZOS)
                    self.wm_image_tk = ImageTk.PhotoImage(thumb)
                    self.wm_img_label.config(text=os.path.basename(self.wm_image_path))
                except Exception:
                    self.wm_image = None
            self.wm_image_scale.set(s.get("wm_image_scale", 30))
            self.wm_image_opacity.set(s.get("wm_image_opacity", 80))
            self.position.set(s.get("position", "center"))
            self.custom_x = s.get("custom_x", 0.5)
            self.custom_y = s.get("custom_y", 0.5)
            self.opacity.set(s.get("opacity", 0.6))
            self.out_format.set(s.get("out_format", "JPEG"))
            self.name_rule.set(s.get("name_rule", "prefix"))
            self.prefix.set(s.get("prefix", "wm_"))
            self.suffix.set(s.get("suffix", "_watermarked"))
            self.jpeg_quality.set(s.get("jpeg_quality", 90))
            self.export_scale_mode.set(s.get("export_scale_mode", "original"))
            self.export_scale_percent.set(s.get("export_scale_percent", 100))
            # 更新 font label
            self.font_label.config(text=os.path.basename(self.font_file) if self.font_file else "(使用系统默认字体)")
        except Exception as e:
            print("应用设置失败：", e)

    def _refresh_tpl_menu(self):
        menu = self.tpl_menu["menu"]
        menu.delete(0, "end")
        names = sorted(self.templates.keys())
        if not names:
            names = [""]
        for n in names:
            menu.add_command(label=n, command=lambda v=n: self.tpl_var.set(v))
        # 设置当前模板变量
        if names and names[0] != "":
            self.tpl_var.set(names[0])

    def _save_data(self):
        data = {
            "templates": self.templates,
            "last_settings": self._gather_settings()
        }
        try:
            with open(DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("保存数据失败：", e)

    def load_data(self):
        if not os.path.exists(DATA_PATH):
            return
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.templates = data.get("templates", {})
            last = data.get("last_settings")
            if last:
                self._apply_settings(last)
            self._refresh_tpl_menu()
        except Exception as e:
            print("加载数据失败：", e)

    def on_close(self):
        # 保存当前设置为 last_settings
        try:
            self._save_data()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    # 如果系统装有 tkinterdnd2，可以创建 TkinterDnD.Tk() 来支持拖拽窗口级别；
    # 但为兼容起见，这里优先使用普通 Tk 并通过 widget 的 drop_target_register 尝试注册拖拽。
    if DND_AVAILABLE:
        try:
            root = TkinterDnD.Tk()
        except Exception:
            root = tk.Tk()
    else:
        root = tk.Tk()
    app = WatermarkerApp(root)
    root.geometry("1200x800")
    root.mainloop()
