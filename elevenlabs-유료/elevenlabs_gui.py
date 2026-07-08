#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
일레븐랩스 대본 -> 음성 자동 변환기 (버튼만 누르면 되는 버전)
txt 파일의 각 줄을 순서대로 mp3(001.mp3, 002.mp3 ...)로 만들어 줍니다.
코딩 지식이 전혀 없어도 사용할 수 있습니다.
"""

import os
import sys
import json
import time
import re
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import requests
except ImportError:
    _r = tk.Tk(); _r.withdraw()
    messagebox.showerror(
        "설치 필요",
        "'requests' 라이브러리가 필요합니다.\n\n"
        "함께 들어있는 실행 파일\n"
        "(실행_윈도우.bat 또는 실행_맥.command)로 켜면 자동으로 설치됩니다.")
    sys.exit(1)

# 설정 파일 위치 (exe로 묶었을 때도 exe 옆에 저장되게 처리)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "설정.json")

MODEL_ID = "eleven_multilingual_v2"   # 한국어 지원 모델


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def sanitize(name):
    """폴더 이름에 못 쓰는 글자를 _ 로 바꿉니다."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip().strip(".")
    return name or "제목없음"


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.running = False
        self.cancel = False
        self.txt_path = tk.StringVar()
        self.out_dir = tk.StringVar(value=self.cfg.get("out_dir", ""))

        root.title("대본 → 음성 자동 변환기")
        root.geometry("580x670")
        root.minsize(520, 600)

        pad = {"padx": 14, "pady": 5}

        tk.Label(root, text="① 아래 두 칸만 한 번 입력하면 자동 저장됩니다",
                 font=("", 11, "bold")).pack(anchor="w", **pad)

        f1 = tk.Frame(root); f1.pack(fill="x", **pad)
        tk.Label(f1, text="API 키", width=9, anchor="w").pack(side="left")
        self.api_entry = tk.Entry(f1, show="*")
        self.api_entry.pack(side="left", fill="x", expand=True)
        self.api_entry.insert(0, self.cfg.get("api_key", ""))

        f2 = tk.Frame(root); f2.pack(fill="x", **pad)
        tk.Label(f2, text="목소리 ID", width=9, anchor="w").pack(side="left")
        self.voice_entry = tk.Entry(f2)
        self.voice_entry.pack(side="left", fill="x", expand=True)
        self.voice_entry.insert(0, self.cfg.get("voice_id", ""))

        ttk.Separator(root).pack(fill="x", pady=8)
        tk.Label(root, text="② 대본 파일과 저장 위치 고르기",
                 font=("", 11, "bold")).pack(anchor="w", **pad)

        f3 = tk.Frame(root); f3.pack(fill="x", **pad)
        tk.Button(f3, text="대본 파일 선택 (.txt)", command=self.pick_txt,
                  width=18).pack(side="left")
        tk.Label(f3, textvariable=self.txt_path, fg="gray",
                 anchor="w").pack(side="left", padx=8, fill="x", expand=True)

        f4 = tk.Frame(root); f4.pack(fill="x", **pad)
        tk.Button(f4, text="저장 폴더 선택", command=self.pick_dir,
                  width=18).pack(side="left")
        tk.Label(f4, textvariable=self.out_dir, fg="gray",
                 anchor="w").pack(side="left", padx=8, fill="x", expand=True)

        f5 = tk.Frame(root); f5.pack(fill="x", **pad)
        tk.Label(f5, text="제목(선택)", width=9, anchor="w").pack(side="left")
        self.title_entry = tk.Entry(f5)
        self.title_entry.pack(side="left", fill="x", expand=True)
        tk.Label(root, text="   ※ 비우면 대본 파일 이름으로 저장돼요. "
                            "결과는 [연-월]/[날짜_제목] 폴더에 정리됩니다.",
                 fg="gray").pack(anchor="w", padx=14)

        ttk.Separator(root).pack(fill="x", pady=8)

        btnrow = tk.Frame(root); btnrow.pack(fill="x", **pad)
        self.start_btn = tk.Button(btnrow, text="▶  음성 만들기 시작", height=2,
                                   font=("", 13, "bold"), command=self.start)
        self.start_btn.pack(side="left", fill="x", expand=True)
        self.stop_btn = tk.Button(btnrow, text="■ 정지", height=2,
                                  font=("", 11), command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(root)
        self.progress.pack(fill="x", **pad)
        self.status = tk.Label(root, text="대기 중", anchor="w", fg="gray")
        self.status.pack(fill="x", padx=14)

        self.log = tk.Text(root, height=9, state="disabled", bg="#f7f7f7")
        self.log.pack(fill="both", expand=True, padx=14, pady=8)

    # ---- 백그라운드 스레드에서 화면을 안전하게 갱신하기 위한 헬퍼 ----
    def ui(self, fn):
        self.root.after(0, fn)

    def log_msg(self, msg):
        def _do():
            self.log.config(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.config(state="disabled")
        self.ui(_do)

    def set_status(self, msg):
        self.ui(lambda: self.status.config(text=msg))

    def set_progress(self, value, maximum=None):
        def _do():
            if maximum is not None:
                self.progress.config(maximum=maximum)
            self.progress.config(value=value)
        self.ui(_do)

    # ---- 버튼 동작 ----
    def pick_txt(self):
        p = filedialog.askopenfilename(
            title="대본 txt 파일 선택",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")])
        if p:
            self.txt_path.set(p)
            if not self.out_dir.get():
                self.out_dir.set(os.path.join(os.path.dirname(p), "일레븐 음성출력"))

    def pick_dir(self):
        d = filedialog.askdirectory(title="저장 폴더 선택")
        if d:
            self.out_dir.set(d)

    def start(self):
        if self.running:
            return
        api_key = self.api_entry.get().strip()
        voice_id = self.voice_entry.get().strip()
        txt = self.txt_path.get()
        out = self.out_dir.get()

        if not api_key or not voice_id:
            messagebox.showwarning("확인", "API 키와 목소리 ID를 입력하세요.")
            return
        if not txt or not os.path.exists(txt):
            messagebox.showwarning("확인", "대본 txt 파일을 선택하세요.")
            return
        if not out:
            messagebox.showwarning("확인", "저장 폴더를 선택하세요.")
            return

        self.cfg.update({"api_key": api_key, "voice_id": voice_id, "out_dir": out})
        save_config(self.cfg)

        # 날짜/제목/기간별 폴더 경로 만들기: 저장폴더/연-월/날짜_제목
        now = datetime.now()
        title = self.title_entry.get().strip()
        if not title:
            title = os.path.splitext(os.path.basename(txt))[0]
        title = sanitize(title)
        final_out = os.path.join(out, now.strftime("%Y-%m"),
                                 f"{now.strftime('%Y-%m-%d')}_{title}")

        self.running = True
        self.cancel = False
        self.start_btn.config(state="disabled", text="만드는 중...")
        self.stop_btn.config(state="normal", text="■ 정지")
        threading.Thread(target=self.worker,
                         args=(api_key, voice_id, txt, final_out), daemon=True).start()

    def stop(self):
        # 현재 문장까지만 만들고 멈춥니다.
        self.cancel = True
        self.stop_btn.config(state="disabled", text="정지 중...")
        self.set_status("정지 중... (현재 문장 끝나면 멈춰요)")

    def worker(self, api_key, voice_id, txt, out):
        try:
            os.makedirs(out, exist_ok=True)
            with open(txt, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]

            total = len(lines)
            self.set_progress(0, maximum=total)
            self.log_msg(f"저장 위치: {out}")
            self.log_msg(f"총 {total}개 문장을 변환합니다.")

            index_rows = []
            for i, text in enumerate(lines, start=1):
                if self.cancel:
                    break
                fname = f"{i:03d}.mp3"
                fpath = os.path.join(out, fname)
                index_rows.append(f"{fname}\t{text}")
                self.set_status(f"[{i}/{total}] {text[:22]}")

                if os.path.exists(fpath):
                    self.log_msg(f"{fname}  이미 있음 · 건너뜀")
                    self.set_progress(i)
                    continue

                ok = self.make_one(api_key, voice_id, text, fpath)
                self.log_msg(f"{fname}  {'완료' if ok else '실패 · 건너뜀'}")
                self.set_progress(i)
                time.sleep(0.3)

            with open(os.path.join(out, "_목록.txt"), "w", encoding="utf-8") as f:
                f.write("파일명\t문장\n" + "\n".join(index_rows))

            if self.cancel:
                self.set_status("정지됨")
                self.log_msg("\n정지했습니다. 여기까지 만든 파일은 저장돼 있어요. "
                             "다시 시작하면 이어서 만듭니다.")
            else:
                self.set_status("완료!")
                self.log_msg("\n끝났습니다! 저장 폴더를 확인하세요.")
                self.ui(lambda: messagebox.showinfo("완료", "음성 파일이 모두 만들어졌습니다."))
        except Exception as e:
            self.log_msg(f"오류: {e}")
            self.ui(lambda: messagebox.showerror("오류", str(e)))
        finally:
            self.running = False
            self.cancel = False
            self.ui(lambda: self.start_btn.config(state="normal",
                                                  text="▶  음성 만들기 시작"))
            self.ui(lambda: self.stop_btn.config(state="disabled", text="■ 정지"))

    def make_one(self, api_key, voice_id, text, fpath):
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        payload = {
            "text": text,
            "model_id": MODEL_ID,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8,
                               "style": 0.0, "use_speaker_boost": True},
        }
        for _ in range(3):
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=60)
            except requests.RequestException:
                time.sleep(4)
                continue
            if r.status_code == 200:
                with open(fpath, "wb") as out_f:
                    out_f.write(r.content)
                return True
            if r.status_code == 429:
                self.log_msg("   (요청이 몰려 8초 대기)")
                time.sleep(8)
                continue
            if r.status_code == 401:
                self.log_msg("   API 키가 올바른지 확인하세요 (401)")
                return False
            self.log_msg(f"   오류 {r.status_code}: {r.text[:120]}")
            return False
        return False


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()