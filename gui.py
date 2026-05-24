"""
视频标题分类工具 - 图形界面
支持 Stage1 / Stage1b / Stage1c / Stage2 全流程操作
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess
import threading
import os
import sys
from pathlib import Path
from datetime import datetime

# 导入 Provider 管理模块
from providers import (
    get_available_providers, get_provider_config, get_api_key,
    check_provider_availability, get_provider_display_name,
    get_providers_for_gui
)

PROJECT_DIR = Path(__file__).parent.resolve()
PYTHON = sys.executable
DEFAULT_CSV = "output/title_review.csv"


class ToolTip:
    """鼠标悬停提示工具类"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 20
        y += self.widget.winfo_rooty() + 25
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                        background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                        font=("Microsoft YaHei", 9), wraplength=350)
        label.pack(ipadx=4, ipady=2)

    def hide_tip(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class LogRedirector:
    """将 print 输出重定向到 GUI 文本框"""
    def __init__(self, text_widget, tag="stdout"):
        self.text_widget = text_widget
        self.tag = tag

    def write(self, msg):
        if msg.strip():
            self.text_widget.after(0, self._append, msg)

    def _append(self, msg):
        self.text_widget.configure(state="normal")
        self.text_widget.insert(tk.END, msg + "\n", self.tag)
        self.text_widget.see(tk.END)
        self.text_widget.configure(state="disabled")

    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("视频标题分类工具 v5.0")
        self.geometry("900x850")
        self.minsize(800, 700)

        self.process = None
        self.running = False

        # 共享 CSV 路径变量
        self.csv_var = tk.StringVar(value=DEFAULT_CSV)

        self._build_ui()
        self._sync_csv()

    def _build_ui(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._build_stage1_tab()
        self._build_stage1b_tab()
        self._build_stage1c_tab()
        self._build_stage2_tab()

        # 切换标签页时同步 CSV
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="运行日志")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill=tk.X, padx=4, pady=2)
        ttk.Button(log_toolbar, text="清空日志", command=self._clear_log).pack(side=tk.RIGHT)
        self.stop_btn = ttk.Button(log_toolbar, text="停止", command=self._stop_process, state="disabled")
        self.stop_btn.pack(side=tk.RIGHT, padx=4)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, state="disabled",
            font=("Consolas", 9), wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.log_text.tag_configure("stdout", foreground="#cccccc")
        self.log_text.tag_configure("stderr", foreground="#ff6666")
        self.log_text.tag_configure("info", foreground="#66ccff")

        sys.stdout = LogRedirector(self.log_text, "stdout")
        sys.stderr = LogRedirector(self.log_text, "stderr")

    # ==================== CSV 路径同步 ====================
    def _sync_csv(self):
        """同步所有标签页的 CSV 路径"""
        csv = self.csv_var.get()
        self.s1_output_var.set(csv)
        self.s1b_csv_var.set(csv)
        self.s1c_csv_var.set(csv)
        self.s2_csv_var.set(csv)

    def _on_tab_changed(self, event=None):
        """切换标签页时，用共享变量同步"""
        # 从当前活动标签页读取 CSV 路径，更新到共享变量
        tab = self.notebook.select()
        tab_name = self.notebook.tab(tab, "text")
        if "Stage1 " in tab_name:
            current = self.s1_output_var.get()
        elif "Stage1b" in tab_name:
            current = self.s1b_csv_var.get()
        elif "Stage1c" in tab_name:
            current = self.s1c_csv_var.get()
        elif "Stage2" in tab_name:
            current = self.s2_csv_var.get()
        else:
            return
        if current:
            self.csv_var.set(current)
            self._sync_csv()

    # ==================== Stage1 ====================
    def _build_stage1_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Stage1 扫描")

        # 目录选择
        dir_frame = ttk.LabelFrame(tab, text="扫描目录")
        dir_frame.pack(fill=tk.X, padx=8, pady=4)
        self.s1_dir_var = tk.StringVar()
        dir_entry = ttk.Entry(dir_frame, textvariable=self.s1_dir_var, width=60)
        dir_entry.pack(side=tk.LEFT, padx=4, pady=4, fill=tk.X, expand=True)
        ToolTip(dir_entry, "要扫描的视频/图片目录路径\n支持递归扫描所有子目录")
        ttk.Button(dir_frame, text="浏览...", command=self._browse_s1_dir).pack(side=tk.RIGHT, padx=4)

        # 输出文件
        out_frame = ttk.LabelFrame(tab, text="输出文件")
        out_frame.pack(fill=tk.X, padx=8, pady=4)
        self.s1_output_var = tk.StringVar(value=DEFAULT_CSV)
        out_entry = ttk.Entry(out_frame, textvariable=self.s1_output_var, width=60)
        out_entry.pack(side=tk.LEFT, padx=4, pady=4, fill=tk.X, expand=True)
        ToolTip(out_entry, "输出的CSV待审表文件路径\n默认: output/title_review.csv")
        ttk.Button(out_frame, text="浏览...", command=self._browse_s1_output).pack(side=tk.RIGHT, padx=4)

        # 选项
        opt_frame = ttk.LabelFrame(tab, text="选项")
        opt_frame.pack(fill=tk.X, padx=8, pady=4)
        self.s1_append_var = tk.BooleanVar()
        append_cb = ttk.Checkbutton(opt_frame, text="追加模式（保留已有记录）", variable=self.s1_append_var)
        append_cb.pack(anchor=tk.W, padx=4)
        ToolTip(append_cb, "启用：新扫描的记录追加到现有CSV\n禁用：覆盖现有CSV文件\n适合分批扫描多个目录")
        
        self.s1_force_var = tk.BooleanVar()
        force_cb = ttk.Checkbutton(opt_frame, text="强制重新分类（忽略已有中括号）", variable=self.s1_force_var)
        force_cb.pack(anchor=tk.W, padx=4)
        ToolTip(force_cb, "启用：处理所有文件，包括已有[标签]的文件\n禁用：跳过已分类的文件\n用于重新整理已有标签的文件")

        # 排除目录
        excl_frame = ttk.LabelFrame(tab, text="排除目录（每行一个）")
        excl_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.s1_exclude_text = tk.Text(excl_frame, height=3, font=("Microsoft YaHei", 9))
        self.s1_exclude_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        ToolTip(self.s1_exclude_text, "要排除的目录名或路径（每行一个）\n\n示例：\ntemp\nbackup\nF:\\Download\\broken\n\n支持目录名或绝对路径")

        # 运行按钮
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        run_btn = ttk.Button(btn_frame, text="开始扫描", command=self._run_stage1)
        run_btn.pack(fill=tk.X, padx=4)
        ToolTip(run_btn, "开始扫描指定目录\n提取文件名关键词，生成待审表\n标记无意义标题为needs_vision=true")

    # ==================== Stage1b ====================
    def _build_stage1b_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Stage1b AI优化")

        # 顶部：CSV文件和Provider
        top_frame = ttk.Frame(tab)
        top_frame.pack(fill=tk.X, padx=8, pady=4)
        
        csv_frame = ttk.LabelFrame(top_frame, text="待审表文件")
        csv_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.s1b_csv_var = tk.StringVar(value=DEFAULT_CSV)
        csv_entry = ttk.Entry(csv_frame, textvariable=self.s1b_csv_var)
        csv_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4, pady=4)
        ToolTip(csv_entry, "Stage1生成的待审表CSV文件\n只处理needs_vision=false的记录")
        ttk.Button(csv_frame, text="浏览", command=self._browse_s1b_csv, width=6).pack(side=tk.LEFT, padx=(0, 4))

        # Provider 下拉框（自动检测可用）
        prov_frame = ttk.LabelFrame(top_frame, text="AI Provider")
        prov_frame.pack(side=tk.LEFT, padx=4)
        
        self.s1b_providers = get_available_providers("1b")
        self.s1b_provider_options = [p["id"] for p in self.s1b_providers]
        self.s1b_provider_display = [p["name"] for p in self.s1b_providers]
        
        self.s1b_provider_var = tk.StringVar()
        self.s1b_provider_combo = ttk.Combobox(prov_frame, textvariable=self.s1b_provider_var, 
                                                values=self.s1b_provider_display, state="readonly", width=15)
        self.s1b_provider_combo.pack(side=tk.LEFT, padx=4, pady=4)
        
        if self.s1b_provider_display:
            self.s1b_provider_combo.current(0)
        
        self.s1b_provider_combo.bind("<<ComboboxSelected>>", self._on_s1b_provider_change)
        
        # Provider 描述标签
        self.s1b_prov_desc = ttk.Label(prov_frame, text="", foreground="gray")
        self.s1b_prov_desc.pack(side=tk.LEFT, padx=4)
        self._update_s1b_provider_desc()

        # 参数行
        param_frame = ttk.Frame(tab)
        param_frame.pack(fill=tk.X, padx=8, pady=4)
        
        ttk.Label(param_frame, text="模型:").pack(side=tk.LEFT)
        self.s1b_model_var = tk.StringVar()
        self.s1b_model_entry = ttk.Entry(param_frame, textvariable=self.s1b_model_var, width=20)
        self.s1b_model_entry.pack(side=tk.LEFT, padx=(2, 12))
        ToolTip(self.s1b_model_entry, "留空使用默认模型")
        
        ttk.Label(param_frame, text="每批:").pack(side=tk.LEFT)
        self.s1b_batch_var = tk.IntVar(value=5)
        ttk.Spinbox(param_frame, textvariable=self.s1b_batch_var, from_=1, to=20, width=4).pack(side=tk.LEFT, padx=(2, 12))
        
        ttk.Label(param_frame, text="间隔:").pack(side=tk.LEFT)
        self.s1b_delay_var = tk.DoubleVar(value=2.0)
        ttk.Spinbox(param_frame, textvariable=self.s1b_delay_var, from_=0.5, to=30, increment=0.5, width=4).pack(side=tk.LEFT, padx=(2, 4))
        ttk.Label(param_frame, text="秒").pack(side=tk.LEFT)

        # 预览和编辑区域
        preview_frame = ttk.LabelFrame(tab, text="AI优化预览（可编辑）")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        
        # 说明标签
        ttk.Label(preview_frame, text="点击「AI优化」后，结果会显示在这里。您可以手动修改，然后点击「确认填入」。", 
                  foreground="gray").pack(anchor=tk.W, padx=4, pady=2)
        
        # 创建Treeview表格
        columns = ("original", "optimized", "status")
        self.s1b_tree = ttk.Treeview(preview_frame, columns=columns, show="headings", height=10)
        self.s1b_tree.heading("original", text="原始标题")
        self.s1b_tree.heading("optimized", text="AI优化标题（可编辑）")
        self.s1b_tree.heading("status", text="状态")
        self.s1b_tree.column("original", width=200)
        self.s1b_tree.column("optimized", width=250)
        self.s1b_tree.column("status", width=80)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(preview_frame, orient="vertical", command=self.s1b_tree.yview)
        self.s1b_tree.configure(yscrollcommand=scrollbar.set)
        
        self.s1b_tree.pack(side="left", fill=tk.BOTH, expand=True, padx=4, pady=4)
        scrollbar.pack(side="right", fill="y", pady=4)
        
        # 绑定双击编辑事件
        self.s1b_tree.bind("<Double-1>", self._on_s1b_edit)
        
        # 绑定右键菜单
        self.s1b_context_menu = tk.Menu(self.s1b_tree, tearoff=0)
        self.s1b_context_menu.add_command(label="采用原标题", command=self._on_s1b_use_original)
        self.s1b_context_menu.add_command(label="编辑", command=self._on_s1b_edit_menu)
        self.s1b_context_menu.add_separator()
        self.s1b_context_menu.add_command(label="删除此行", command=self._on_s1b_delete)
        self.s1b_tree.bind("<Button-3>", self._on_s1b_context_menu)  # 右键
        
        # 存储优化结果
        self.s1b_results = {}

        # 按钮区域
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        
        ttk.Button(btn_frame, text="AI优化", command=self._run_stage1b_preview).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="确认填入", command=self._run_stage1b_confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="清空", command=self._clear_s1b_preview).pack(side=tk.LEFT, padx=4)

    def _on_s1b_provider_change(self, event=None):
        """Stage1b Provider 变化时更新描述和默认模型"""
        self._update_s1b_provider_desc()
        # 更新默认模型
        idx = self.s1b_provider_combo.current()
        if idx >= 0 and idx < len(self.s1b_providers):
            default_model = self.s1b_providers[idx].get("default_model", "")
            self.s1b_model_var.set(default_model)

    def _update_s1b_provider_desc(self):
        """更新 Stage1b Provider 描述"""
        idx = self.s1b_provider_combo.current()
        if idx >= 0 and idx < len(self.s1b_providers):
            desc = self.s1b_providers[idx].get("description", "")
            self.s1b_prov_desc.config(text=desc)

    def _get_s1b_provider_id(self):
        """获取当前选择的 Stage1b Provider ID"""
        idx = self.s1b_provider_combo.current()
        if idx >= 0 and idx < len(self.s1b_provider_options):
            return self.s1b_provider_options[idx]
        return "gcli"

    def _on_s1b_edit(self, event):
        """双击编辑AI优化标题"""
        item = self.s1b_tree.selection()
        if not item:
            return
        
        # 获取当前值
        item = item[0]
        values = self.s1b_tree.item(item, "values")
        if not values:
            return
        
        # 创建编辑对话框
        dialog = tk.Toplevel(self)
        dialog.title("编辑优化标题")
        dialog.geometry("400x150")
        dialog.transient(self)
        dialog.grab_set()
        
        ttk.Label(dialog, text=f"原始标题: {values[0][:50]}").pack(padx=8, pady=4)
        
        ttk.Label(dialog, text="优化标题:").pack(padx=8, anchor=tk.W)
        entry = ttk.Entry(dialog, width=50)
        entry.insert(0, values[1])
        entry.pack(padx=8, pady=4)
        entry.select_range(0, tk.END)
        entry.focus_set()
        
        def confirm():
            new_value = entry.get().strip()
            if new_value:
                self.s1b_tree.item(item, values=(values[0], new_value, "已修改"))
                self.s1b_results[values[0]] = new_value
            dialog.destroy()
        
        ttk.Button(dialog, text="确认", command=confirm).pack(pady=8)
        entry.bind("<Return>", lambda e: confirm())

    def _on_s1b_context_menu(self, event):
        """显示右键菜单"""
        item = self.s1b_tree.identify_row(event.y)
        if item:
            self.s1b_tree.selection_set(item)
            self.s1b_context_menu.post(event.x_root, event.y_root)

    def _on_s1b_use_original(self):
        """右键：采用原标题"""
        item = self.s1b_tree.selection()
        if not item:
            return
        item = item[0]
        values = self.s1b_tree.item(item, "values")
        if values:
            original = values[0]
            self.s1b_tree.item(item, values=(original, original, "采用原标题"))
            self.s1b_results[original] = original

    def _on_s1b_edit_menu(self):
        """右键：编辑"""
        self._on_s1b_edit(None)

    def _on_s1b_delete(self):
        """右键：删除此行"""
        item = self.s1b_tree.selection()
        if not item:
            return
        item = item[0]
        values = self.s1b_tree.item(item, "values")
        if values and values[0] in self.s1b_results:
            del self.s1b_results[values[0]]
        self.s1b_tree.delete(item)

    def _run_stage1b_preview(self):
        """AI优化预览（调用AI但不写入文件）"""
        csv_path = self.s1b_csv_var.get().strip()
        if not csv_path or not Path(csv_path).exists():
            messagebox.showwarning("提示", "请先选择有效的待审表文件。")
            return
        
        # 清空预览
        self._clear_s1b_preview()
        
        # 读取CSV
        try:
            import csv
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        except Exception as e:
            messagebox.showerror("错误", f"读取CSV失败: {e}")
            return
        
        # 筛选needs_vision=false的记录
        provider = self._get_s1b_provider_id()
        col = f'{provider}_title'
        pending = [r for r in rows 
                   if r.get('original_title', '').strip() 
                   and r.get('needs_vision', 'false').strip().lower() != 'true'
                   and not r.get(col, '').strip()]
        
        if not pending:
            messagebox.showinfo("提示", "没有需要优化的标题（所有标题都需要视觉识别或已优化）。")
            return
        
        # 显示在预览表格中
        for row in pending[:50]:  # 最多显示50条
            original = row['original_title'].strip()
            self.s1b_tree.insert("", "end", values=(original, "", "待优化"))
        
        # 调用AI优化
        self._ai_optimize_titles(pending[:50], provider)

    def _ai_optimize_titles(self, rows, provider):
        """调用AI优化标题"""
        import threading
        
        # 获取参数
        model = self.s1b_model_var.get().strip()
        batch_size = self.s1b_batch_var.get()
        delay = self.s1b_delay_var.get()
        
        # 使用 providers 模块获取默认模型
        if not model:
            config = get_provider_config(provider)
            if config:
                model = config.get("default_model", "")
        
        def _worker():
            try:
                # 导入AI优化模块
                from stage1b_ai_refine import call_ollama_batch, call_zhipu_batch, call_gcli_batch
                
                call_fns = {
                    "ollama": call_ollama_batch,
                    "zhipu": call_zhipu_batch,
                    "gcli": call_gcli_batch
                }
                call_fn = call_fns.get(provider)
                if not call_fn:
                    print(f"[错误] 不支持的Provider: {provider}")
                    return
                
                # 使用 providers 模块获取 API Key
                api_key = get_api_key(provider)
                
                # 分批处理
                for batch_start in range(0, len(rows), batch_size):
                    batch = rows[batch_start:batch_start + batch_size]
                    titles = [r['original_title'].strip() for r in batch]
                    
                    print(f"[AI优化] 处理批次 {batch_start//batch_size + 1}, {len(titles)} 条")
                    
                    # 调用AI
                    if provider == "ollama":
                        results = call_fn(titles=titles, model=model)
                    else:
                        results = call_fn(titles=titles, model=model, api_key=api_key)
                    
                    # 更新预览表格
                    for (row, result) in zip(batch, results):
                        original = row['original_title'].strip()
                        optimized = result if result else original
                        
                        # 更新表格
                        for item in self.s1b_tree.get_children():
                            values = self.s1b_tree.item(item, "values")
                            if values and values[0] == original:
                                self.s1b_tree.item(item, values=(original, optimized, "已优化"))
                                self.s1b_results[original] = optimized
                                break
                    
                    # 延迟
                    if batch_start + batch_size < len(rows):
                        import time
                        time.sleep(delay)
                
                print("[AI优化] 完成")
                
            except Exception as e:
                print(f"[AI优化] 错误: {e}")
                import traceback
                traceback.print_exc()
        
        # 在后台线程运行
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _run_stage1b_confirm(self):
        """确认填入优化结果"""
        if not self.s1b_results:
            messagebox.showwarning("提示", "没有优化结果可填入。请先运行AI优化。")
            return
        
        csv_path = self.s1b_csv_var.get().strip()
        if not csv_path or not Path(csv_path).exists():
            messagebox.showwarning("提示", "请先选择有效的待审表文件。")
            return
        
        # 读取CSV
        try:
            import csv
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                fieldnames = reader.fieldnames
        except Exception as e:
            messagebox.showerror("错误", f"读取CSV失败: {e}")
            return
        
        # 确保列存在
        provider = self._get_s1b_provider_id()
        col = f'{provider}_title'
        if col not in fieldnames:
            fieldnames.append(col)
        
        # 填入优化结果
        count = 0
        for row in rows:
            original = row.get('original_title', '').strip()
            if original in self.s1b_results:
                row[col] = self.s1b_results[original]
                row['final_name'] = self.s1b_results[original]
                count += 1
        
        # 保存CSV
        try:
            with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            messagebox.showinfo("完成", f"已填入 {count} 条优化结果。")
        except Exception as e:
            messagebox.showerror("错误", f"保存CSV失败: {e}")

    def _clear_s1b_preview(self):
        """清空预览"""
        for item in self.s1b_tree.get_children():
            self.s1b_tree.delete(item)
        self.s1b_results.clear()

    # ==================== Stage1c ====================
    def _build_stage1c_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Stage1c 视觉识别")

        # 创建可滚动区域（支持鼠标滚轮）
        container = ttk.Frame(tab)
        container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 绑定鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def _bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        def _unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)
        scrollable_frame.bind("<Enter>", _bind_mousewheel)
        scrollable_frame.bind("<Leave>", _unbind_mousewheel)

        # ========== 内容区域 ==========
        content_frame = ttk.Frame(scrollable_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # ---- 第一行：CSV文件 + Provider ----
        row1 = ttk.Frame(content_frame)
        row1.pack(fill=tk.X, pady=(0, 8))
        
        # CSV 文件
        csv_frame = ttk.LabelFrame(row1, text="待审表文件")
        csv_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.s1c_csv_var = tk.StringVar(value=DEFAULT_CSV)
        csv_entry_frame = ttk.Frame(csv_frame)
        csv_entry_frame.pack(fill=tk.X, padx=4, pady=4)
        csv_entry = ttk.Entry(csv_entry_frame, textvariable=self.s1c_csv_var)
        csv_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(csv_entry_frame, text="浏览", command=self._browse_s1c_csv, width=6).pack(side=tk.LEFT, padx=(4, 0))
        ToolTip(csv_entry, "Stage1生成的待审表CSV文件路径")

        # 云端 VLM Provider（下拉框自动检测）
        prov_frame = ttk.LabelFrame(row1, text="云端 VLM")
        prov_frame.pack(side=tk.LEFT, padx=4)
        
        self.s1c_providers = get_available_providers("1c")
        self.s1c_provider_options = [p["id"] for p in self.s1c_providers]
        self.s1c_provider_display = [p["name"] for p in self.s1c_providers]
        
        self.s1c_provider_var = tk.StringVar()
        self.s1c_provider_combo = ttk.Combobox(prov_frame, textvariable=self.s1c_provider_var, 
                                                values=self.s1c_provider_display, state="readonly", width=15)
        self.s1c_provider_combo.pack(side=tk.LEFT, padx=6, pady=4)
        
        if self.s1c_provider_display:
            self.s1c_provider_combo.current(0)
        
        self.s1c_provider_combo.bind("<<ComboboxSelected>>", self._on_s1c_provider_change)
        
        # Provider 描述标签
        self.s1c_prov_desc = ttk.Label(prov_frame, text="", foreground="gray")
        self.s1c_prov_desc.pack(side=tk.LEFT, padx=4)
        self._update_s1c_provider_desc()

        # ---- CLIP 本地预分类 ----
        clip_frame = ttk.LabelFrame(content_frame, text="CLIP 本地预分类")
        clip_frame.pack(fill=tk.X, pady=(0, 8))
        
        # 第一行：启用开关 + 多标签
        clip_row1 = ttk.Frame(clip_frame)
        clip_row1.pack(fill=tk.X, padx=8, pady=(4, 2))
        self.s1c_clip_var = tk.BooleanVar()
        clip_cb = ttk.Checkbutton(clip_row1, text="启用 CLIP 预分类", variable=self.s1c_clip_var)
        clip_cb.pack(side=tk.LEFT)
        ToolTip(clip_cb, "使用CLIP模型在本地预分类\n可节省云端API调用\n需要下载模型到models/clip/")
        
        self.s1c_multilabel_var = tk.BooleanVar(value=True)
        ml_cb = ttk.Checkbutton(clip_row1, text="多标签模式", variable=self.s1c_multilabel_var)
        ml_cb.pack(side=tk.LEFT, padx=(16, 0))
        ToolTip(ml_cb, "启用：返回所有匹配的标签\n示例：JK制服_百褶裙_白丝_站姿\n\n禁用：只返回最匹配的单个标签\n示例：JK制服")
        
        # 第二行：参数
        clip_row2 = ttk.Frame(clip_frame)
        clip_row2.pack(fill=tk.X, padx=8, pady=(0, 6))
        
        ttk.Label(clip_row2, text="置信度:").pack(side=tk.LEFT)
        self.s1c_clip_thresh_var = tk.DoubleVar(value=0.25)
        thresh_spin = ttk.Spinbox(clip_row2, textvariable=self.s1c_clip_thresh_var, from_=0.1, to=0.9, increment=0.05, width=5)
        thresh_spin.pack(side=tk.LEFT, padx=(2, 12))
        ToolTip(thresh_spin, "CLIP分类置信度阈值\n低于此值会调用云端VLM补充\n0.25=默认，0.1=更宽松，0.5=更严格")
        
        ttk.Label(clip_row2, text="分析帧数:").pack(side=tk.LEFT)
        self.s1c_clip_frames_var = tk.IntVar(value=5)
        frames_spin = ttk.Spinbox(clip_row2, textvariable=self.s1c_clip_frames_var, from_=1, to=10, width=4)
        frames_spin.pack(side=tk.LEFT, padx=(2, 12))
        ToolTip(frames_spin, "CLIP分析的视频帧数\n帧数越多分析越全面，但速度越慢\n建议3-8帧")
        
        ttk.Label(clip_row2, text="VLM帧数:").pack(side=tk.LEFT)
        self.s1c_vlm_frames_var = tk.IntVar(value=3)
        vlm_spin = ttk.Spinbox(clip_row2, textvariable=self.s1c_vlm_frames_var, from_=1, to=5, width=4)
        vlm_spin.pack(side=tk.LEFT, padx=(2, 0))
        ToolTip(vlm_spin, "送入云端VLM的帧数\n多帧可提高识别准确度\n建议2-3帧")

        # ---- 关键帧检测 + Embedding 检测（并排） ----
        detect_frame = ttk.Frame(content_frame)
        detect_frame.pack(fill=tk.X, pady=(0, 8))
        
        # 关键帧检测
        keyframe_frame = ttk.LabelFrame(detect_frame, text="关键帧检测")
        keyframe_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        
        kf_row = ttk.Frame(keyframe_frame)
        kf_row.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(kf_row, text="差异阈值:").pack(side=tk.LEFT)
        self.s1c_keyframe_thresh_var = tk.DoubleVar(value=30.0)
        kf_spin = ttk.Spinbox(kf_row, textvariable=self.s1c_keyframe_thresh_var, from_=10.0, to=100.0, increment=5.0, width=5)
        kf_spin.pack(side=tk.LEFT, padx=(2, 12))
        ToolTip(kf_spin, "帧差异检测阈值\n越低越敏感（检测更多变化）\n30=默认，10=很敏感，80=不敏感")
        
        ttk.Label(kf_row, text="最大帧数:").pack(side=tk.LEFT)
        self.s1c_max_keyframes_var = tk.IntVar(value=8)
        mkf_spin = ttk.Spinbox(kf_row, textvariable=self.s1c_max_keyframes_var, from_=3, to=20, width=4)
        mkf_spin.pack(side=tk.LEFT, padx=(2, 0))
        ToolTip(mkf_spin, "最大关键帧数量\n帧数越多分析越全面\n建议5-10帧")

        # Embedding 检测
        embed_frame = ttk.LabelFrame(detect_frame, text="Embedding 变化检测")
        embed_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        
        emb_row1 = ttk.Frame(embed_frame)
        emb_row1.pack(fill=tk.X, padx=8, pady=(4, 0))
        self.s1c_embed_var = tk.BooleanVar(value=True)
        emb_cb = ttk.Checkbutton(emb_row1, text="启用（检测穿着变化）", variable=self.s1c_embed_var)
        emb_cb.pack(side=tk.LEFT)
        ToolTip(emb_cb, "基于CLIP Embedding检测人体区域变化\n比标签比较更准确\n专注检测穿着是否改变")
        
        emb_row2 = ttk.Frame(embed_frame)
        emb_row2.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Label(emb_row2, text="相似度:").pack(side=tk.LEFT)
        self.s1c_embed_thresh_var = tk.DoubleVar(value=0.75)
        emb_spin = ttk.Spinbox(emb_row2, textvariable=self.s1c_embed_thresh_var, from_=0.5, to=0.95, increment=0.05, width=5)
        emb_spin.pack(side=tk.LEFT, padx=(2, 4))
        ToolTip(emb_spin, "Embedding相似度阈值\n低于此值认为有变化\n0.75=稳健，0.6=敏感，0.9=宽松")
        ttk.Label(emb_row2, text="(0.75=稳健)", foreground="gray").pack(side=tk.LEFT)

        # ---- UHD 人体检测 ----
        uhd_frame = ttk.LabelFrame(content_frame, text="UHD 人体检测")
        uhd_frame.pack(fill=tk.X, pady=(0, 8))
        
        uhd_row1 = ttk.Frame(uhd_frame)
        uhd_row1.pack(fill=tk.X, padx=8, pady=(4, 2))
        self.s1c_uhd_var = tk.BooleanVar(value=True)
        uhd_cb = ttk.Checkbutton(uhd_row1, text="启用人体检测", variable=self.s1c_uhd_var)
        uhd_cb.pack(side=tk.LEFT)
        ToolTip(uhd_cb, "使用UHD超轻量模型检测视频中的人体\n自动找到包含人体的帧\n提高分析准确性")
        
        uhd_row2 = ttk.Frame(uhd_frame)
        uhd_row2.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Label(uhd_row2, text="置信度:").pack(side=tk.LEFT)
        self.s1c_uhd_thresh_var = tk.DoubleVar(value=0.5)
        uhd_spin = ttk.Spinbox(uhd_row2, textvariable=self.s1c_uhd_thresh_var, from_=0.1, to=0.9, increment=0.05, width=5)
        uhd_spin.pack(side=tk.LEFT, padx=(2, 12))
        ToolTip(uhd_spin, "人体检测置信度阈值\n低于此值不认为检测到人体\n0.5=默认，0.3=更敏感")
        ttk.Label(uhd_row2, text="最大重试:").pack(side=tk.LEFT)
        self.s1c_uhd_retries_var = tk.IntVar(value=3)
        retry_spin = ttk.Spinbox(uhd_row2, textvariable=self.s1c_uhd_retries_var, from_=1, to=10, width=4)
        retry_spin.pack(side=tk.LEFT, padx=(2, 0))
        ToolTip(retry_spin, "人体检测最大重试次数\n视频较长时可增加重试\n建议3-5次")

        # ---- 其他选项 ----
        other_frame = ttk.LabelFrame(content_frame, text="其他选项")
        other_frame.pack(fill=tk.X, pady=(0, 8))
        
        # 复选框行
        other_row1 = ttk.Frame(other_frame)
        other_row1.pack(fill=tk.X, padx=8, pady=(4, 2))
        self.s1c_retry_var = tk.BooleanVar()
        retry_cb = ttk.Checkbutton(other_row1, text="重试失败行", variable=self.s1c_retry_var)
        retry_cb.pack(side=tk.LEFT)
        ToolTip(retry_cb, "重新处理之前失败的行\n（vision_description为[ERROR]的）")
        
        self.s1c_dryrun_var = tk.BooleanVar()
        dryrun_cb = ttk.Checkbutton(other_row1, text="模拟运行", variable=self.s1c_dryrun_var)
        dryrun_cb.pack(side=tk.LEFT, padx=(12, 0))
        ToolTip(dryrun_cb, "模拟运行，不实际调用API\n用于预览将要处理的文件")
        
        self.s1c_all_var = tk.BooleanVar()
        all_cb = ttk.Checkbutton(other_row1, text="处理所有标题", variable=self.s1c_all_var)
        all_cb.pack(side=tk.LEFT, padx=(12, 0))
        ToolTip(all_cb, "处理所有标题（忽略needs_vision标记）\n默认只处理needs_vision=true的文件")
        
        # 单文件处理行
        other_row2 = ttk.Frame(other_frame)
        other_row2.pack(fill=tk.X, padx=8, pady=(0, 6))
        ttk.Label(other_row2, text="单文件:").pack(side=tk.LEFT)
        self.s1c_single_var = tk.StringVar()
        single_entry = ttk.Entry(other_row2, textvariable=self.s1c_single_var, width=40)
        single_entry.pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)
        ToolTip(single_entry, "仅处理指定的文件名\n如：IMG_7940.MP4\n留空则处理所有待处理文件")

        # ---- 运行按钮（固定在底部） ----
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        
        # 添加分隔线
        ttk.Separator(btn_frame, orient="horizontal").pack(fill=tk.X, pady=(0, 8))
        
        run_btn = ttk.Button(btn_frame, text="▶ 开始视觉识别", command=self._run_stage1c)
        run_btn.pack(fill=tk.X, padx=4, ipady=6)
        ToolTip(run_btn, "开始执行视觉识别\n将使用CLIP+云端VLM分析视频/图片\n提取关键词并生成标准化标题")

    # ==================== Stage2 ====================
    def _build_stage2_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Stage2 重命名")

        csv_frame = ttk.LabelFrame(tab, text="待审表文件")
        csv_frame.pack(fill=tk.X, padx=8, pady=4)
        self.s2_csv_var = tk.StringVar(value=DEFAULT_CSV)
        csv_entry = ttk.Entry(csv_frame, textvariable=self.s2_csv_var, width=60)
        csv_entry.pack(side=tk.LEFT, padx=4, pady=4, fill=tk.X, expand=True)
        ToolTip(csv_entry, "已审核的CSV待审表文件\n只有review_status为「已确认」的记录会被重命名")
        ttk.Button(csv_frame, text="浏览...", command=self._browse_s2_csv).pack(side=tk.RIGHT, padx=4)

        # 批量确认
        confirm_frame = ttk.LabelFrame(tab, text="批量确认")
        confirm_frame.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(confirm_frame, text="将 CSV 中所有「待审核」记录标记为「已确认」").pack(anchor=tk.W, padx=4, pady=2)
        confirm_btn = ttk.Button(confirm_frame, text="全部确认", command=self._run_batch_confirm)
        confirm_btn.pack(anchor=tk.W, padx=4, pady=4)
        ToolTip(confirm_btn, "一键将所有「待审核」改为「已确认」\n适合确认所有标题无误后批量操作")

        # 说明
        info_frame = ttk.LabelFrame(tab, text="操作说明")
        info_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        info_text = (
            "1. 先用 Stage1 生成待审表\n"
            "2. （可选）用 Stage1c 视觉识别提取关键词\n"
            "3. 点击「全部确认」批量标记，或手动编辑 CSV\n"
            "4. 先用「模拟运行」预览结果\n"
            "5. 确认无误后执行「正式重命名」\n\n"
            "提示：\n"
            "- 已确认的行才会被重命名\n"
            "- 冲突文件名会自动追加序号（_1, _2）\n"
            "- 日志保存在 logs/rename_log.txt"
        )
        ttk.Label(info_frame, text=info_text, justify=tk.LEFT, wraplength=700).pack(padx=8, pady=8, anchor=tk.NW)

        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        dryrun_btn = ttk.Button(btn_frame, text="模拟运行", command=self._run_stage2_dryrun)
        dryrun_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ToolTip(dryrun_btn, "模拟运行，预览将要重命名的文件\n不实际执行重命名操作\n建议先模拟再正式执行")
        
        run_btn = ttk.Button(btn_frame, text="正式重命名", command=self._run_stage2)
        run_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        ToolTip(run_btn, "执行重命名操作\n只有「已确认」的文件会被重命名\n操作不可逆，建议先模拟运行")

    # ==================== 浏览按钮 ====================
    def _browse_s1_dir(self):
        d = filedialog.askdirectory(title="选择扫描目录")
        if d:
            self.s1_dir_var.set(d)

    def _browse_s1_output(self):
        f = filedialog.asksaveasfilename(title="选择输出文件", defaultextension=".csv",
                                          filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
        if f:
            self.s1_output_var.set(f)
            self.csv_var.set(f)

    def _browse_s1b_csv(self):
        f = filedialog.askopenfilename(title="选择待审表", filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
        if f:
            self.s1b_csv_var.set(f)
            self.csv_var.set(f)

    def _browse_s1c_csv(self):
        f = filedialog.askopenfilename(title="选择待审表", filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
        if f:
            self.s1c_csv_var.set(f)
            self.csv_var.set(f)

    def _on_s1c_provider_change(self, event=None):
        """Stage1c Provider 变化时更新描述"""
        self._update_s1c_provider_desc()

    def _update_s1c_provider_desc(self):
        """更新 Stage1c Provider 描述"""
        idx = self.s1c_provider_combo.current()
        if idx >= 0 and idx < len(self.s1c_providers):
            desc = self.s1c_providers[idx].get("description", "")
            self.s1c_prov_desc.config(text=desc)

    def _get_s1c_provider_id(self):
        """获取当前选择的 Stage1c Provider ID"""
        idx = self.s1c_provider_combo.current()
        if idx >= 0 and idx < len(self.s1c_provider_options):
            return self.s1c_provider_options[idx]
        return "gcli"

    def _browse_s2_csv(self):
        f = filedialog.askopenfilename(title="选择待审表", filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")])
        if f:
            self.s2_csv_var.set(f)
            self.csv_var.set(f)

    # ==================== 运行命令 ====================
    def _run_command(self, cmd: list[str], label: str):
        if self.running:
            messagebox.showwarning("提示", "已有任务在运行中，请等待完成。")
            return

        self.running = True
        self.stop_btn.configure(state="normal")
        self._clear_log()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 启动 {label}")
        print(f"命令: {' '.join(cmd)}")
        print("-" * 60)

        def _worker():
            try:
                self.process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    bufsize=1, cwd=str(PROJECT_DIR)
                )
                for line in self.process.stdout:
                    print(line.rstrip())
                self.process.wait()
                retcode = self.process.returncode
                print("-" * 60)
                if retcode == 0:
                    print(f"[{label}] 执行完成")
                else:
                    print(f"[{label}] 退出码: {retcode}")
            except Exception as e:
                print(f"[错误] {e}")
            finally:
                self.running = False
                self.process = None
                self.stop_btn.configure(state="disabled")

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _stop_process(self):
        if self.process and self.running:
            try:
                self.process.terminate()
                print("[用户] 已发送停止信号")
            except Exception as e:
                print(f"[错误] 停止失败: {e}")

    # ==================== Stage1 ====================
    def _run_stage1(self):
        target_dir = self.s1_dir_var.get().strip()
        if not target_dir:
            messagebox.showwarning("提示", "请选择扫描目录。")
            return
        if not Path(target_dir).exists():
            messagebox.showerror("错误", f"目录不存在: {target_dir}")
            return

        cmd = [PYTHON, "stage1_extract_propose.py", "-d", target_dir, "-o", self.s1_output_var.get()]
        if self.s1_append_var.get():
            cmd.append("-a")
        if self.s1_force_var.get():
            cmd.append("--force-reclassify")

        excludes = self.s1_exclude_text.get("1.0", tk.END).strip().split("\n")
        for ex in excludes:
            ex = ex.strip()
            if ex:
                cmd.extend(["--exclude-dir", ex])

        self._run_command(cmd, "Stage1 扫描")

    # ==================== Stage1b ====================
    def _run_stage1b(self):
        csv_path = self.s1b_csv_var.get().strip()
        if not csv_path:
            messagebox.showwarning("提示", "请选择待审表文件。")
            return

        cmd = [PYTHON, "stage1b_ai_refine.py", "-c", csv_path, "-p", self.s1b_provider_var.get()]
        model = self.s1b_model_var.get().strip()
        if model:
            cmd.extend(["-m", model])
        cmd.extend(["--batch-size", str(self.s1b_batch_var.get())])
        cmd.extend(["--delay", str(self.s1b_delay_var.get())])
        if self.s1b_dryrun_var.get():
            cmd.append("--dry-run")

        self._run_command(cmd, "Stage1b AI优化")

    # ==================== Stage1c ====================
    def _run_stage1c(self):
        csv_path = self.s1c_csv_var.get().strip()
        if not csv_path:
            messagebox.showwarning("提示", "请选择待审表文件。")
            return

        # 检查 Provider 可用性
        provider = self._get_s1c_provider_id()
        availability = check_provider_availability(provider)
        if not availability["available"]:
            messagebox.showerror("错误", f"Provider '{provider}' 不可用: {availability['reason']}")
            return

        cmd = [PYTHON, "stage1c_vision_refine.py", "-c", csv_path, "-p", provider]

        # CLIP 参数
        if self.s1c_clip_var.get():
            cmd.append("--use-clip")
            cmd.extend(["--clip-threshold", str(self.s1c_clip_thresh_var.get())])
            cmd.extend(["--clip-frames", str(self.s1c_clip_frames_var.get())])
            cmd.extend(["--vlm-frames", str(self.s1c_vlm_frames_var.get())])
            if not self.s1c_multilabel_var.get():
                cmd.append("--single-label")

        # 关键帧检测参数
        cmd.extend(["--keyframe-threshold", str(self.s1c_keyframe_thresh_var.get())])
        cmd.extend(["--max-keyframes", str(self.s1c_max_keyframes_var.get())])

        # Embedding 检测参数
        if self.s1c_embed_var.get():
            cmd.append("--use-embedding-detection")
            cmd.extend(["--embedding-threshold", str(self.s1c_embed_thresh_var.get())])
        else:
            cmd.append("--no-embedding-detection")

        # UHD 人体检测参数
        if not self.s1c_uhd_var.get():
            cmd.append("--no-frame-selector")
        else:
            cmd.extend(["--conf-threshold", str(self.s1c_uhd_thresh_var.get())])
            cmd.extend(["--max-retries", str(self.s1c_uhd_retries_var.get())])

        # 其他参数
        if self.s1c_retry_var.get():
            cmd.append("--retry-errors")
        if self.s1c_dryrun_var.get():
            cmd.append("--dry-run")
        if self.s1c_all_var.get():
            cmd.append("--all")

        single = self.s1c_single_var.get().strip()
        if single:
            cmd.extend(["--single", single])

        self._run_command(cmd, "Stage1c 视觉识别")

    # ==================== Stage2 ====================
    def _run_batch_confirm(self):
        csv_path = self.s2_csv_var.get().strip()
        if not csv_path:
            messagebox.showwarning("提示", "请选择待审表文件。")
            return
        if not Path(csv_path).exists():
            messagebox.showerror("错误", f"文件不存在: {csv_path}")
            return

        try:
            import pandas as pd
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
            if "review_status" not in df.columns:
                messagebox.showerror("错误", "CSV 中没有 review_status 列")
                return

            count = len(df)
            df["review_status"] = "已确认"
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"[批量确认] 已将 {count} 条记录标记为「已确认」")
            print(f"[批量确认] 文件: {csv_path}")
            messagebox.showinfo("完成", f"已将 {count} 条记录标记为「已确认」")
        except Exception as e:
            messagebox.showerror("错误", f"操作失败: {e}")

    def _run_stage2_dryrun(self):
        csv_path = self.s2_csv_var.get().strip()
        if not csv_path:
            messagebox.showwarning("提示", "请选择待审表文件。")
            return
        cmd = [PYTHON, "stage2_apply_rename.py", "-c", csv_path, "--dry-run"]
        self._run_command(cmd, "Stage2 模拟运行")

    def _run_stage2(self):
        csv_path = self.s2_csv_var.get().strip()
        if not csv_path:
            messagebox.showwarning("提示", "请选择待审表文件。")
            return
        if not messagebox.askyesno("确认", "确定要执行重命名吗？\n请确保已用模拟运行验证过结果。"):
            return
        cmd = [PYTHON, "stage2_apply_rename.py", "-c", csv_path]
        self._run_command(cmd, "Stage2 重命名")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")

    def destroy(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        super().destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()

