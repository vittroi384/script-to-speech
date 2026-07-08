#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
대본 -> 음성 자동 변환기 (무료 · Microsoft Edge 목소리 / edge-tts)
txt 파일의 각 줄을 순서대로 mp3(001.mp3, 002.mp3 ...)로 만들어 줍니다.
API 키도, 계정도, 비용도 필요 없습니다. 인터넷 연결만 있으면 됩니다.
목소리별로 폴더가 따로 생겨서(InJoon / Hyunsu) 서로 안 섞입니다.
"""

import os
import sys
import time
import re
import asyncio
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import edge_tts
except ImportError:
    _r = tk.Tk(); _r.withdraw()
    messagebox.showerror(
        "설치 필요",
        "'edge-tts' 라이브러리가 필요합니다.\n\n"
        "함께 들어있는 실행 파일(실행.bat)로 켜면 자동으로 설치됩니다.")
    sys.exit(1)

# ====== 목소리 목록 (필요하면 여기 이름만 바꾸면 됩니다) ======
VOICES = {
    "InJoon (남성 · 안정적·무난)": "ko-KR-InJoonNeural",
    "Hyunsu (남성 · 최신·더 자연스러움)": "ko-KR-HyunsuMultilingualNeural",
}
BOTH_LABEL = "둘 다 비교용 (두 목소리 모두)"

# 말하기 속도 옵션
SPEEDS = {
    "보통": "+0%",
    "조금 느리게": "-12%",
    "조금 빠르게": "+12%",
}
# ==========================================================


def short_name(voice_id):
    """ko-KR-InJoonNeural -> InJoon (폴더 이름용)"""
    n = voice_id.replace("ko-KR-", "").replace("Neural", "").replace("Multilingual", "")
    return n or voice_id


def sanitize(name):
    """폴더 이름에 못 쓰는 글자를 _ 로 바꿉니다."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip().strip(".")
    return name or "제목없음"


async def synth(text, voice, rate, path):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(path)


class App:
    def __init__(self, root):
        self.root = root
        self.running = False
        self.cancel = False
        self.txt_path = tk.StringVar()
        self.out_dir = tk.StringVar()

        root.title("대본 → 음성 변환기 (무료 · Edge 목소리)")
        root.geometry("560x650")
        root.minsize(520, 600)
        pad = {"padx": 14, "pady": 5}

        tk.Label(root, text="① 목소리와 속도 고르기",
                 font=("", 11, "bold")).pack(anchor="w", **pad)

        f1 = tk.Frame(root); f1.pack(fill="x", **pad)
        tk.Label(f1, text="목소리", width=7, anchor="w").pack(side="left")
        self.voice_cb = ttk.Combobox(
            f1, values=list(VOICES.keys()) + [BOTH_LABEL], state="readonly")
        self.voice_cb.current(0)
        self.voice_cb.pack(side="left", fill="x", expand=True)

        f1b = tk.Frame(root); f1b.pack(fill="x", **pad)
        tk.Label(f1b, text="속도", width=7, anchor="w").pack(side="left")
        self.speed_cb = ttk.Combobox(
            f1b, values=list(SPEEDS.keys()), state="readonly")
        self.speed_cb.current(0)
        self.speed_cb.pack(side="left", fill="x", expand=True)

        ttk.Separator(root).pack(fill="x", pady=8)
        tk.Label(root, text="② 대본 파일과 저장 위치 고르기",
                 font=("", 11, "bold")).pack(anchor="w", **pad)

        f2 = tk.Frame(root); f2.pack(fill="x", **pad)
        tk.Button(f2, text="대본 파일 선택 (.txt)", command=self.pick_txt,
                  width=18).pack(side="left")
        tk.Label(f2, textvariable=self.txt_path, fg="gray",
                 anchor="w").pack(side="left", padx=8, fill="x", expand=True)

        f3 = tk.Frame(root); f3.pack(fill="x", **pad)
        tk.Button(f3, text="저장 폴더 선택", command=self.pick_dir,
                  width=18).pack(side="left")
        tk.Label(f3, textvariable=self.out_dir, fg="gray",
                 anchor="w").pack(side="left", padx=8, fill="x", expand=True)

        f4 = tk.Frame(root); f4.pack(fill="x", **pad)
        tk.Label(f4, text="제목(선택)", width=7, anchor="w").pack(side="left")
        self.title_entry = tk.Entry(f4)
        self.title_entry.pack(side="left", fill="x", expand=True)
        tk.Label(root, text="   ※ 비우면 대본 파일 이름으로 저장돼요. "
                            "결과는 [연-월]/[날짜_제목]/목소리 폴더에 정리됩니다.",
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

    # ---- 백그라운드 스레드에서 화면을 안전하게 갱신 ----
    def ui(self, fn):
        self.root.after(0, fn)

    def log_msg(self, m):
        def _do():
            self.log.config(state="normal")
            self.log.insert("end", m + "\n"); self.log.see("end")
            self.log.config(state="disabled")
        self.ui(_do)

    def set_status(self, m):
        self.ui(lambda: self.status.config(text=m))

    def set_progress(self, v, mx=None):
        def _do():
            if mx is not None:
                self.progress.config(maximum=mx)
            self.progress.config(value=v)
        self.ui(_do)

    # ---- 버튼 ----
    def pick_txt(self):
        p = filedialog.askopenfilename(
            title="대본 txt 파일 선택",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")])
        if p:
            self.txt_path.set(p)
            if not self.out_dir.get():
                self.out_dir.set(os.path.join(os.path.dirname(p), "Edge 음성출력"))

    def pick_dir(self):
        d = filedialog.askdirectory(title="저장 폴더 선택")
        if d:
            self.out_dir.set(d)

    def start(self):
        if self.running:
            return
        txt = self.txt_path.get(); out = self.out_dir.get()
        if not txt or not os.path.exists(txt):
            messagebox.showwarning("확인", "대본 txt 파일을 선택하세요."); return
        if not out:
            messagebox.showwarning("확인", "저장 폴더를 선택하세요."); return

        choice = self.voice_cb.get()
        if choice == BOTH_LABEL:
            voices = list(VOICES.values())
        else:
            voices = [VOICES[choice]]
        rate = SPEEDS[self.speed_cb.get()]

        # 날짜/제목/기간별 폴더 경로: 저장폴더/연-월/날짜_제목  (그 안에 목소리 폴더)
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
                         args=(txt, final_out, voices, rate), daemon=True).start()

    def stop(self):
        # 현재 문장까지만 만들고 멈춥니다.
        self.cancel = True
        self.stop_btn.config(state="disabled", text="정지 중...")
        self.set_status("정지 중... (현재 문장 끝나면 멈춰요)")

    def worker(self, txt, out, voices, rate):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            with open(txt, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]

            total = len(lines) * len(voices)
            self.set_progress(0, mx=total)
            self.log_msg(f"저장 위치: {out}")
            done = 0

            for voice in voices:
                if self.cancel:
                    break
                vfolder = os.path.join(out, short_name(voice))
                os.makedirs(vfolder, exist_ok=True)
                self.log_msg(f"\n=== {short_name(voice)} 목소리로 변환 시작 "
                             f"({len(lines)}개 문장) ===")
                index_rows = []

                for i, text in enumerate(lines, start=1):
                    if self.cancel:
                        break
                    fname = f"{i:03d}.mp3"
                    fpath = os.path.join(vfolder, fname)
                    index_rows.append(f"{fname}\t{text}")
                    self.set_status(f"[{short_name(voice)}] "
                                    f"{i}/{len(lines)} · {text[:18]}")

                    if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                        self.log_msg(f"{fname} 이미 있음 · 건너뜀")
                        done += 1; self.set_progress(done); continue

                    ok = self.make_one(loop, text, voice, rate, fpath)
                    self.log_msg(f"{fname} {'완료' if ok else '실패'}")
                    done += 1; self.set_progress(done)
                    time.sleep(0.2)

                with open(os.path.join(vfolder, "_목록.txt"),
                          "w", encoding="utf-8") as f:
                    f.write("파일명\t문장\n" + "\n".join(index_rows))

            if self.cancel:
                self.set_status("정지됨")
                self.log_msg("\n정지했습니다. 여기까지 만든 파일은 저장돼 있어요. "
                             "다시 시작하면 이어서 만듭니다.")
            else:
                self.set_status("완료!")
                self.log_msg("\n끝났습니다! 저장 폴더 안에 목소리별 폴더를 확인하세요.")
                self.ui(lambda: messagebox.showinfo("완료",
                        "음성 파일이 모두 만들어졌습니다."))
        except Exception as e:
            self.log_msg(f"오류: {e}")
            self.ui(lambda: messagebox.showerror("오류", str(e)))
        finally:
            loop.close()
            self.running = False
            self.cancel = False
            self.ui(lambda: self.start_btn.config(state="normal",
                                                  text="▶  음성 만들기 시작"))
            self.ui(lambda: self.stop_btn.config(state="disabled", text="■ 정지"))

    def make_one(self, loop, text, voice, rate, fpath):
        for _ in range(3):
            try:
                loop.run_until_complete(synth(text, voice, rate, fpath))
                if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                    return True
                self.log_msg("   소리가 안 왔어요 → 재시도")
                time.sleep(2)
            except Exception as e:
                self.log_msg(f"   오류: {str(e)[:120]} → 재시도")
                time.sleep(3)
        return False


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()