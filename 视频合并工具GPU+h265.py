import os
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from threading import Thread, Event
from queue import Queue
import time
import random
from itertools import cycle
from concurrent.futures import ThreadPoolExecutor, as_completed
import platform
import re
import sys
import traceback

class VideoMergerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("视频组合工具 v1.2 (H.265版)")
        self.root.geometry("600x800")
        
        # 变量初始化
        self.folder_a = tk.StringVar()
        self.folder_b = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.resolution = tk.StringVar(value="720x1280")
        self.filename_prefix = tk.StringVar(value="合并视频")
        self.combination_mode = tk.StringVar(value="all")
        self.random_count = tk.StringVar(value="10")
        self.hardware_accel = tk.StringVar(value="auto")
        self.detected_gpu_type, self.gpu_details, self.driver_version = self.detect_gpu_type()
        self.total_videos = 0
        self.processed_videos = 0
        self.stop_event = Event()
        self.worker_thread = None
        self.message_queue = Queue()
        self.progress_queue = Queue()
        self.gpu_supported, self.min_driver_required = self.check_gpu_support()
        self.ffmpeg_path = self.find_ffmpeg()  # 查找FFmpeg路径
        
        # GUI布局
        self.create_widgets()
        
        # 启动队列检查
        self.check_queue()
    
    def find_ffmpeg(self):
        """尝试在系统路径或本地目录中找到ffmpeg"""
        # 首先检查系统PATH中的ffmpeg
        try:
            subprocess.run(['ffmpeg', '-version'], 
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return 'ffmpeg'
        except FileNotFoundError:
            pass
        
        # 检查程序所在目录下的bin文件夹
        local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin', 'ffmpeg')
        if os.name == 'nt':
            local_path += '.exe'
        
        if os.path.exists(local_path):
            return local_path
        
        # 如果都找不到，返回None
        return None
    
    def create_widgets(self):
        # 文件夹选择部分
        frame_folders = ttk.LabelFrame(self.root, text="文件夹设置", padding=10)
        frame_folders.pack(fill=tk.X, padx=10, pady=1)
        
        # 文件夹A
        ttk.Label(frame_folders, text="A面文件夹:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(frame_folders, textvariable=self.folder_a, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(frame_folders, text="浏览...", command=lambda: self.select_folder(self.folder_a)).grid(row=0, column=2)
        
        # 文件夹B
        ttk.Label(frame_folders, text="B面文件夹:").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(frame_folders, textvariable=self.folder_b, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(frame_folders, text="浏览...", command=lambda: self.select_folder(self.folder_b)).grid(row=1, column=2)
        
        # 输出文件夹
        ttk.Label(frame_folders, text="输出文件夹:").grid(row=2, column=0, sticky=tk.W)
        ttk.Entry(frame_folders, textvariable=self.output_folder, width=50).grid(row=2, column=1, padx=5)
        ttk.Button(frame_folders, text="浏览...", command=lambda: self.select_folder(self.output_folder)).grid(row=2, column=2)
        
        # 设置部分
        frame_settings = ttk.LabelFrame(self.root, text="合并设置", padding=10)
        frame_settings.pack(fill=tk.X, padx=10, pady=1)
        
        # 分辨率选择
        ttk.Label(frame_settings, text="输出分辨率:").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(frame_settings, text="720x1280 (竖屏)", variable=self.resolution, value="720x1280").grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(frame_settings, text="1280x720 (横屏)", variable=self.resolution, value="1280x720").grid(row=0, column=2, sticky=tk.W)
        
        # 文件名前缀
        ttk.Label(frame_settings, text="输出文件名前缀:").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(frame_settings, textvariable=self.filename_prefix, width=20).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(frame_settings, text="(自动添加序号，如：前缀1.mp4)").grid(row=1, column=2, sticky=tk.W)
        
        # 硬件加速选项
        ttk.Label(frame_settings, text="硬件加速:").grid(row=2, column=0, sticky=tk.W)
        self.accel_combo = ttk.Combobox(
            frame_settings, 
            textvariable=self.hardware_accel,
            values=["auto", "CPU", "NVIDIA", "AMD", "Intel"],
            state="readonly",
            width=10
        )
        self.accel_combo.grid(row=2, column=1, sticky=tk.W)
        self.accel_combo.set("auto")
        
        # GPU支持状态
        gpu_status = "支持" if self.gpu_supported else f"不支持 (需要驱动: {self.min_driver_required})"
        ttk.Label(frame_settings, text=f"GPU状态: {gpu_status}").grid(row=2, column=2, sticky=tk.W)
        
        # FFmpeg状态
        ffmpeg_status = "已找到" if self.ffmpeg_path else "未找到"
        ttk.Label(frame_settings, text=f"FFmpeg状态: {ffmpeg_status}").grid(row=3, column=0, sticky=tk.W)
        if not self.ffmpeg_path:
            ttk.Button(frame_settings, text="下载FFmpeg", command=self.download_ffmpeg).grid(row=3, column=1, sticky=tk.W)
        
        # 并发控制
        ttk.Label(frame_settings, text="并发任务数:").grid(row=4, column=0, sticky=tk.W)
        self.thread_count = ttk.Combobox(frame_settings, values=[1, 2, 4, 8], width=5, state="readonly")
        self.thread_count.current(2)  # 默认设置为1，避免GPU资源冲突
        self.thread_count.grid(row=4, column=1, sticky=tk.W)
        
        # GPU详细信息
        frame_gpu_info = ttk.LabelFrame(self.root, text="GPU信息", padding=10)
        frame_gpu_info.pack(fill=tk.X, padx=10, pady=1)
        
        gpu_info_text = tk.Text(frame_gpu_info, height=4, state=tk.DISABLED, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(frame_gpu_info, orient=tk.VERTICAL, command=gpu_info_text.yview)
        gpu_info_text.configure(yscrollcommand=scrollbar.set)
        
        gpu_info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        gpu_info_text.config(state=tk.NORMAL)
        gpu_info_text.insert(tk.END, f"检测到: {self.detected_gpu_type}\n")
        gpu_info_text.insert(tk.END, f"驱动版本: {self.driver_version}\n")
        gpu_info_text.insert(tk.END, f"详细信息: {self.gpu_details}\n")
        gpu_info_text.insert(tk.END, f"支持状态: {'支持' if self.gpu_supported else f'需要驱动版本 {self.min_driver_required} 或更高'}")
        gpu_info_text.config(state=tk.DISABLED)
        
        # 组合模式选择
        frame_mode = ttk.LabelFrame(self.root, text="组合模式", padding=10)
        frame_mode.pack(fill=tk.X, padx=10, pady=1)
        
        ttk.Radiobutton(
            frame_mode, 
            text="全组合模式 (A×B): 每个A与每个B组合一次", 
            variable=self.combination_mode, 
            value="all"
        ).grid(row=0, column=0, sticky=tk.W, columnspan=3)
        
        ttk.Radiobutton(
            frame_mode, 
            text="A优先模式 (A数量): 每个A使用一次(B可重复)", 
            variable=self.combination_mode, 
            value="a_priority"
        ).grid(row=1, column=0, sticky=tk.W, columnspan=3)
        
        ttk.Radiobutton(
            frame_mode, 
            text="B优先模式 (B数量): 每个B使用一次(A可重复)", 
            variable=self.combination_mode, 
            value="b_priority"
        ).grid(row=2, column=0, sticky=tk.W, columnspan=3)
        
        # 随机组合模式
        frame_random = ttk.Frame(frame_mode)
        frame_random.grid(row=3, column=0, sticky=tk.W, columnspan=3, pady=(5,0))
        
        ttk.Radiobutton(
            frame_random, 
            text="随机组合模式:", 
            variable=self.combination_mode, 
            value="random"
        ).pack(side=tk.LEFT)
        
        ttk.Entry(frame_random, textvariable=self.random_count, width=5).pack(side=tk.LEFT, padx=5)
        ttk.Label(frame_random, text="个随机组合").pack(side=tk.LEFT)
        
        # 信息显示
        frame_info = ttk.LabelFrame(self.root, text="处理日志", padding=10)
        frame_info.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.info_text = tk.Text(frame_info, height=8, state=tk.DISABLED, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(frame_info, orient=tk.VERTICAL, command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=scrollbar.set)
        
        self.info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 进度条
        self.progress = ttk.Progressbar(self.root, orient=tk.HORIZONTAL, mode='determinate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)
        
        # 状态标签
        self.status_label = ttk.Label(self.root, text="准备就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(fill=tk.X, padx=10, pady=(0, 5))
        
        # 操作按钮
        frame_buttons = ttk.Frame(self.root)
        frame_buttons.pack(fill=tk.X, padx=10, pady=5)
        
        self.start_button = ttk.Button(frame_buttons, text="开始合并", command=self.start_merging)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(frame_buttons, text="停止", command=self.stop_merging, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(frame_buttons, text="清空日志", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_buttons, text="更新驱动", command=self.show_driver_update_info).pack(side=tk.LEFT, padx=5)
        ttk.Button(frame_buttons, text="退出", command=self.root.quit).pack(side=tk.RIGHT, padx=5)
    
    def download_ffmpeg(self):
        """引导用户下载FFmpeg"""
        import webbrowser
        webbrowser.open("https://ffmpeg.org/download.html")
        messagebox.showinfo("下载FFmpeg", "请下载FFmpeg并解压到程序目录下的bin文件夹中")
    
    def show_driver_update_info(self):
        message = "要启用GPU加速，请更新您的显卡驱动程序：\n\n"
        
        if "NVIDIA" in self.detected_gpu_type:
            message += "1. 访问 NVIDIA 驱动程序下载页面: https://www.nvidia.com/Download/index.aspx\n"
            message += "2. 选择您的显卡型号和操作系统\n"
            message += "3. 下载并安装最新的驱动程序 (至少需要版本 470.42 或更高)\n"
            message += f"\n当前驱动版本: {self.driver_version}\n需要版本: 470.42 或更高"
        
        elif "AMD" in self.detected_gpu_type:
            message += "1. 访问 AMD 驱动程序下载页面: https://www.amd.com/support\n"
            message += "2. 选择您的显卡型号和操作系统\n"
            message += "3. 下载并安装最新的 Adrenalin 驱动程序\n"
        
        elif "Intel" in self.detected_gpu_type:
            message += "1. 访问 Intel 驱动程序下载页面: https://downloadcenter.intel.com/\n"
            message += "2. 搜索您的显卡型号\n"
            message += "3. 下载并安装最新的图形驱动程序\n"
        
        else:
            message = "未检测到专用显卡，无法提供驱动程序更新信息"
        
        messagebox.showinfo("更新显卡驱动程序", message)
    
    def detect_gpu_type(self):
        detected_type = "未知"
        details = "未检测到详细信息"
        driver_version = "未知"
        
        try:
            # 尝试获取NVIDIA信息
            if os.name == 'nt':
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=name,driver_version', '--format=csv,noheader'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=name,driver_version', '--format=csv,noheader'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
            
            if result.returncode == 0 and result.stdout.strip():
                gpu_info = result.stdout.decode().split('\n')[0].strip()
                parts = gpu_info.split(',')
                if len(parts) >= 2:
                    gpu_name = parts[0].strip()
                    driver_version = parts[1].strip()
                    detected_type = "NVIDIA"
                    details = gpu_name
                    return detected_type, details, driver_version
                else:
                    # 如果解析失败，使用整个字符串
                    detected_type = "NVIDIA"
                    details = gpu_info
                    return detected_type, details, driver_version
            
            # 尝试获取AMD信息
            try:
                import wmi
                w = wmi.WMI()
                for gpu in w.Win32_VideoController():
                    if "AMD" in gpu.Name or "Radeon" in gpu.Name:
                        detected_type = "AMD"
                        details = f"{gpu.Name}"
                        driver_version = gpu.DriverVersion if hasattr(gpu, 'DriverVersion') else "未知"
                        return detected_type, details, driver_version
            except:
                pass
            
            # 尝试获取Intel信息
            try:
                import wmi
                w = wmi.WMI()
                for gpu in w.Win32_VideoController():
                    if "Intel" in gpu.Name:
                        detected_type = "Intel"
                        details = f"{gpu.Name}"
                        driver_version = gpu.DriverVersion if hasattr(gpu, 'DriverVersion') else "未知"
                        return detected_type, details, driver_version
            except:
                pass
            
            # 尝试通过dxdiag获取信息
            if os.name == 'nt':
                result = subprocess.run(
                    ['dxdiag', '/t', 'dxdiag_output.txt'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    try:
                        with open('dxdiag_output.txt', 'r', encoding='utf-16') as f:
                            content = f.read()
                            if "NVIDIA" in content:
                                detected_type = "NVIDIA"
                            elif "AMD" in content or "Radeon" in content:
                                detected_type = "AMD"
                            elif "Intel" in content:
                                detected_type = "Intel"
                            
                            # 提取显卡名称
                            match = re.search(r"Card name: (.*)", content)
                            if match:
                                details = match.group(1).strip()
                            
                            # 提取驱动程序版本
                            match = re.search(r"Driver Version: (.*)", content)
                            if match:
                                driver_version = match.group(1).strip()
                            
                            return detected_type, details, driver_version
                    except:
                        pass
        
        except Exception as e:
            details = f"检测失败: {str(e)}"
        
        return detected_type, details, driver_version
    
    def check_gpu_support(self):
        min_driver_required = "未知"
        try:
            # 检查FFmpeg是否支持GPU编码器
            if not self.ffmpeg_path:
                return False, "需要FFmpeg"
                
            result = subprocess.run(
                [self.ffmpeg_path, '-encoders'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            encoders = result.stdout + result.stderr
            gpu_encoder_supported = "nvenc" in encoders.lower() or "amf" in encoders.lower() or "qsv" in encoders.lower()
            
            # 对于NVIDIA，检查驱动版本是否满足最低要求
            if "nvidia" in self.detected_gpu_type.lower():
                min_driver_required = "470.42"
                try:
                    # 解析当前驱动版本
                    if self.driver_version != "未知":
                        current_version_parts = [int(x) for x in self.driver_version.split('.')[:2]]
                        min_version_parts = [int(x) for x in min_driver_required.split('.')]
                        
                        # 检查版本是否足够
                        if (current_version_parts[0] < min_version_parts[0] or 
                           (current_version_parts[0] == min_version_parts[0] and current_version_parts[1] < min_version_parts[1])):
                            return False, min_driver_required
                except:
                    pass
            
            return gpu_encoder_supported, min_driver_required
        except:
            return False, min_driver_required
    
    def select_folder(self, folder_var):
        folder = filedialog.askdirectory()
        if folder:
            folder_var.set(folder)
    
    def clear_log(self):
        self.info_text.config(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.config(state=tk.DISABLED)
    
    def log_message(self, message):
        self.info_text.config(state=tk.NORMAL)
        self.info_text.insert(tk.END, message + "\n")
        self.info_text.see(tk.END)
        self.info_text.config(state=tk.DISABLED)
    
    def update_status(self, message):
        self.status_label.config(text=message)
    
    def check_queue(self):
        # 处理消息队列
        while not self.message_queue.empty():
            message = self.message_queue.get()
            if message == "RESET_UI":
                self.reset_ui()
            else:
                self.log_message(message)
        
        # 处理进度队列
        while not self.progress_queue.empty():
            processed, total = self.progress_queue.get()
            self.processed_videos = processed
            self.progress["maximum"] = total
            self.progress["value"] = processed
            percent = (processed / total) * 100 if total > 0 else 0
            status = f"处理中: {processed}/{total} ({percent:.1f}%)"
            if processed == total:
                status = f"完成: {processed}个视频已生成"
            self.update_status(status)
        
        # 每100毫秒检查一次队列
        self.root.after(100, self.check_queue)
    
    def reset_ui(self):
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.update_status("准备就绪")
        self.stop_event.clear()
    
    def get_unique_filename(self, folder, base_filename):
        """生成唯一的文件名，避免覆盖现有文件"""
        name, ext = os.path.splitext(base_filename)
        counter = 1
        new_filename = base_filename
        
        while os.path.exists(os.path.join(folder, new_filename)):
            new_filename = f"{name}_{counter}{ext}"
            counter += 1
        
        return new_filename
    
    def get_gpu_encoder(self, gpu_type):
        gpu_type = gpu_type.lower()
        
        if "nvidia" in gpu_type:
            return "hevc_nvenc"  # H.265编码
        elif "amd" in gpu_type:
            return "hevc_amf"    # H.265编码
        elif "intel" in gpu_type:
            return "hevc_qsv"    # H.265编码
        else:
            return "libx265"     # CPU H.265编码
    
    def start_merging(self):
        if not self.ffmpeg_path:
            messagebox.showerror("错误", "未找到FFmpeg！请先安装FFmpeg并添加到系统PATH或程序目录下的bin文件夹中。")
            return
            
        folder_a = self.folder_a.get()
        folder_b = self.folder_b.get()
        output_folder = self.output_folder.get()
        filename_prefix = self.filename_prefix.get().strip()
        mode = self.combination_mode.get()
        hardware_accel = self.hardware_accel.get()
        
        if not all([folder_a, folder_b, output_folder]):
            messagebox.showerror("错误", "请选择所有必需的文件夹!")
            return
        
        if not filename_prefix:
            messagebox.showerror("错误", "请输入输出文件名前缀!")
            return
        
        try:
            os.makedirs(output_folder, exist_ok=True)
        except Exception as e:
            messagebox.showerror("错误", f"无法创建输出文件夹: {str(e)}")
            return
        
        # 获取视频文件列表
        try:
            videos_a = sorted([f for f in os.listdir(folder_a) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))])
            videos_b = sorted([f for f in os.listdir(folder_b) if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))])
        except Exception as e:
            messagebox.showerror("错误", f"无法读取视频文件: {str(e)}")
            return
        
        if not videos_a or not videos_b:
            messagebox.showerror("错误", "至少一个文件夹中没有视频文件!")
            return
        
        # 根据模式计算总任务数
        if mode == "all":
            total = len(videos_a) * len(videos_b)
            mode_desc = f"全组合模式 (A×B): {len(videos_a)} × {len(videos_b)} = {total} 个组合"
        elif mode == "a_priority":
            total = len(videos_a)
            mode_desc = f"A优先模式: {len(videos_a)} 个组合 (B可能重复使用)"
        elif mode == "b_priority":
            total = len(videos_b)
            mode_desc = f"B优先模式: {len(videos_b)} 个组合 (A可能重复使用)"
        elif mode == "random":
            try:
                total = int(self.random_count.get())
                if total <= 0:
                    raise ValueError("数量必须大于0")
            except ValueError as e:
                messagebox.showerror("错误", f"请输入有效的随机组合数量: {str(e)}")
                return
            mode_desc = f"随机组合模式: {total} 个随机组合"
        
        self.total_videos = total
        self.processed_videos = 0
        self.stop_event.clear()
        
        # 确定编码器
        if hardware_accel == "auto":
            encoder = self.get_gpu_encoder(self.detected_gpu_type)
        elif hardware_accel == "NVIDIA":
            encoder = "hevc_nvenc"
        elif hardware_accel == "AMD":
            encoder = "hevc_amf"
        elif hardware_accel == "Intel":
            encoder = "hevc_qsv"
        else:
            encoder = "libx265"
        
        # 如果GPU不支持，强制使用CPU
        if encoder != "libx265" and not self.gpu_supported:
            self.log_message(f"警告: GPU支持不足 (需要驱动版本: {self.min_driver_required}, 当前: {self.driver_version})")
            self.log_message("已自动切换到CPU编码")
            encoder = "libx265"
        
        # 在GPU模式下强制并发任务数为1
        max_workers = int(self.thread_count.get())
        if encoder != "libx265":
            max_workers = 1  # GPU模式下强制单任务
            self.log_message("注意: GPU加速模式已启用，并发任务数强制设置为1以避免资源冲突")
        
        self.clear_log()
        self.log_message(f"找到 {len(videos_a)} 个开头视频和 {len(videos_b)} 个结尾视频")
        self.log_message(f"组合模式: {mode_desc}")
        self.log_message(f"输出文件名格式: {filename_prefix}1.mp4, {filename_prefix}2.mp4, ...")
        self.log_message(f"编码方式: {'GPU加速' if encoder != 'libx265' else 'CPU'} ({encoder})")
        self.log_message(f"并发任务数: {max_workers}")
        self.log_message("开始组合处理...")
        
        self.progress["maximum"] = total
        self.progress["value"] = 0
        
        # 更新按钮状态
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        # 创建工作线程
        self.worker_thread = Thread(
            target=self.process_combinations,
            args=(folder_a, folder_b, output_folder, videos_a, videos_b, filename_prefix, mode, encoder, max_workers),
            daemon=True
        )
        self.worker_thread.start()
    
    def process_combinations(self, folder_a, folder_b, output_folder, videos_a, videos_b, filename_prefix, mode, encoder, max_workers):
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 生成组合列表
                if mode == "all":
                    combinations = [(a, b) for a in videos_a for b in videos_b]
                elif mode == "a_priority":
                    b_cycle = cycle(videos_b)
                    combinations = [(a, next(b_cycle)) for a in videos_a]
                elif mode == "b_priority":
                    a_cycle = cycle(videos_a)
                    combinations = [(next(a_cycle), b) for b in videos_b]
                elif mode == "random":
                    try:
                        total = int(self.random_count.get())
                        if total <= 0:
                            raise ValueError("数量必须大于0")
                        
                        # 生成所有可能的组合
                        all_combinations = [(a, b) for a in videos_a for b in videos_b]
                        
                        # 如果请求的组合数超过总数，则使用所有组合
                        if total > len(all_combinations):
                            total = len(all_combinations)
                            self.message_queue.put(f"警告: 随机组合数超过最大可能组合数，已调整为 {total}")
                        
                        # 随机选择不重复的组合
                        random.seed(time.time())
                        combinations = random.sample(all_combinations, total)
                    except ValueError as e:
                        self.message_queue.put(f"错误: {str(e)}")
                        return
                
                futures = []
                for idx, (video_a, video_b) in enumerate(combinations, 1):
                    if self.stop_event.is_set():
                        break
                    
                    input_a = os.path.join(folder_a, video_a)
                    input_b = os.path.join(folder_b, video_b)
                    
                    # 生成基础输出文件名并确保唯一
                    base_filename = f"{filename_prefix}{idx}.mp4"
                    unique_filename = self.get_unique_filename(output_folder, base_filename)
                    output_file = os.path.join(output_folder, unique_filename)
                    
                    future = executor.submit(
                        self.merge_videos,
                        input_a, input_b, output_file, idx, encoder
                    )
                    futures.append(future)
                    self.progress_queue.put((0, self.total_videos))
                
                # 等待任务完成
                for i, future in enumerate(as_completed(futures), 1):
                    if self.stop_event.is_set():
                        # 取消未完成的任务
                        for f in futures:
                            f.cancel()
                        break
                    
                    try:
                        future.result()
                        self.progress_queue.put((i, self.total_videos))
                    except Exception as e:
                        if not isinstance(e, subprocess.CalledProcessError):
                            self.message_queue.put(f"错误: {str(e)}")
            
            if not self.stop_event.is_set():
                self.message_queue.put("所有视频组合完成!")
                self.progress_queue.put((self.total_videos, self.total_videos))
            else:
                self.message_queue.put("处理已停止")
            
        except Exception as e:
            self.message_queue.put(f"处理过程中发生错误: {str(e)}")
        finally:
            self.message_queue.put("RESET_UI")
    
    def merge_videos(self, video_a, video_b, output_file, index, encoder):
        if self.stop_event.is_set():
            return

        resolution = self.resolution.get()
        width, height = resolution.split('x')
        
        # 构建FFmpeg命令
        cmd = [
            self.ffmpeg_path,
            '-hide_banner',
            '-loglevel', 'error',
            '-i', video_a,
            '-i', video_b,
            '-filter_complex', 
            f'[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,'
            f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0];'
            f'[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,'
            f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v1];'
            '[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[v][a]',
            '-map', '[v]',
            '-map', '[a]',
            '-c:v', encoder,
            '-preset', 'medium',
            '-crf', '18',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-y',
            output_file
        ]
        
        # 针对特定GPU编码器添加额外参数
        if encoder == "hevc_nvenc":
            cmd.extend([
                '-rc', 'vbr',
                '-cq', '12',
                '-qmin', '8',
                '-qmax', '24',
                '-b:v', '0',
                '-maxrate', '50M',
                '-profile:v', 'main',
                '-tune', 'hq',
                '-gpu', '0' if platform.system() == 'Windows' else '-1',
                '-preset', 'p7',
                '-multipass', 'fullres',
                '-weighted_pred', '1',
                '-spatial_aq', '1',
                '-temporal_aq', '1',
                '-gpu', '0' if platform.system() == 'Windows' else '-1'
            ])
        elif encoder == "hevc_amf":
            cmd.extend([
                '-usage', 'lowlatency',
                '-quality', 'balanced',
                '-b:v', '12M'
            ])
        elif encoder == "hevc_qsv":
            cmd.extend([
                '-global_quality', '16',
                '-preset', 'balanced',
                '-b:v', '12M'
            ])
        else:  # CPU模式 (libx265)
            cmd.extend([
                '-b:v', '7M'
            ])
        
        try:
            # Windows系统隐藏窗口
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore',
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # 等待进程完成
            stdout, stderr = process.communicate()
            return_code = process.returncode
            
            if return_code == 0:
                self.message_queue.put(f"成功: 已生成 {os.path.basename(output_file)}")
            else:
                # 获取错误信息
                error_msg = stderr.strip() if stderr else f"返回码: {return_code}"
                
                # 记录详细错误信息
                error_log = f"错误处理 #{index}:\n命令: {' '.join(cmd)}\n错误信息: {error_msg}"
                self.message_queue.put(error_log)
                
                # 如果是GPU错误，尝试回退到CPU编码
                if "Nvenc" in error_msg or "AMF" in error_msg or "QSV" in error_msg or "GPU" in error_msg:
                    self.message_queue.put(f"GPU编码失败 (#{index}), 尝试使用CPU编码...")
                    self.merge_videos(video_a, video_b, output_file, index, "libx265")
                else:
                    # 对于其他错误，尝试使用更简单的CPU编码
                    self.message_queue.put(f"尝试使用更简单的CPU编码 (#{index})...")
                    self.merge_videos(video_a, video_b, output_file, index, "libx265")
                
        except Exception as e:
            if not self.stop_event.is_set():
                # 尝试使用CPU编码作为最后手段
                self.message_queue.put(f"严重错误处理 #{index}: {str(e)}, 尝试使用CPU编码...")
                self.merge_videos(video_a, video_b, output_file, index, "libx265")
    
    def stop_merging(self):
        self.stop_event.set()
        self.message_queue.put("正在停止处理，请稍候...")
        self.stop_button.config(state=tk.DISABLED)

if __name__ == "__main__":
    # 添加异常捕获和日志记录
    import traceback
    try:
        root = tk.Tk()
        app = VideoMergerApp(root)
        root.mainloop()
    except Exception as e:
        with open("error.log", "w") as f:
            f.write(traceback.format_exc())
        messagebox.showerror("崩溃报告", f"程序崩溃:\n{str(e)}\n详细信息已保存到error.log")