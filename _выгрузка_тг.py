# -*- coding: utf-8 -*-
"""
Выгрузка СВОИХ сообщений из Telegram в текст с таймкодами.
Голосовые расшифровываются автоматически (Whisper large-v3).

Читает ТОЛЬКО твой аккаунт через официальный Telegram API.
Никакого пробива и чужих аккаунтов — только твои диалоги.

=== ПЕРВЫЙ ЗАПУСК ===
1) pip install telethon faster-whisper   (+ ffmpeg в PATH)
2) получить api_id/api_hash: https://my.telegram.org -> API development tools
3) скопировать _tg_secret.example.py -> _tg_secret.py и вписать туда ключи
4) запустить — Telegram спросит номер и код один раз, дальше вход запомнится.

Кого выгружать — список CHATS ниже. Можно писать числовой id (надёжнее всего),
@username или примерное имя. Если чат не нашёлся — открой
выгрузки\_список чатов.txt (создаётся при запуске) и впиши оттуда точное имя/id.
"""
import os, sys, asyncio, subprocess, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "выгрузки")
VOICE_DIR = os.path.join(OUT_DIR, "голосовые")
SESSION = os.path.join(BASE, "_tg_session")

# --- кого выгружать: числовой id (надёжнее всего), @username или примерное имя ---
# id всех своих чатов можно подсмотреть в выгрузки\_список чатов.txt после первого запуска
CHATS = [
    "@durov",              # пример: по username
    "Имя Фамилия",         # пример: по имени из твоих контактов
    "123456789",           # пример: по числовому id
]

SINCE = "2026-07-01"          # с какой даты тянуть, ГГГГ-ММ-ДД
TRANSCRIBE_VOICE = True        # расшифровывать голосовые

# ------------------------------------------------------------------
try:
    from _tg_secret import API_ID, API_HASH
except Exception:
    print("Нет файла _tg_secret.py. Скопируй _tg_secret.example.py и впиши ключи."); sys.exit(1)

from telethon import TelegramClient
from datetime import datetime, timezone

_whisper = None
def get_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel, BatchedInferencePipeline
        try:
            m = WhisperModel("large-v3", device="cuda", compute_type="float16")
        except Exception:
            m = WhisperModel("large-v3", device="cpu", compute_type="int8")
        _whisper = BatchedInferencePipeline(model=m)
    return _whisper


def transcribe(path):
    wav = os.path.join(tempfile.gettempdir(), "tg_voice.wav")
    try:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path,
                        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav], check=True)
    except Exception:
        return "[не удалось извлечь звук]"
    segs, _ = get_whisper().transcribe(wav, language="ru", batch_size=8, vad_filter=True)
    text = " ".join(s.text.strip() for s in segs).strip()
    try:
        os.remove(wav)
    except OSError:
        pass
    return text or "[тишина]"


def sender_name(s):
    if s is None:
        return "?"
    fn = getattr(s, "first_name", "") or ""
    ln = getattr(s, "last_name", "") or ""
    nm = (fn + " " + ln).strip()
    return nm or getattr(s, "title", None) or getattr(s, "username", None) or "?"


def find_dialog(req, dialogs):
    """Ищем диалог по id / username / примерному имени.
    dialogs идёт по свежести, поэтому среди тёзок берём самый активный."""
    req = str(req).strip()
    r = req.lower().lstrip("@")
    if req.lstrip("-").isdigit():           # точный id — самый надёжный путь
        for d in dialogs:
            if str(d.entity.id) == req.lstrip("-"):
                return d
    for d in dialogs:                       # username
        un = getattr(d.entity, "username", None)
        if un and un.lower() == r:
            return d
    for d in dialogs:                       # подстрока в любую сторону, первый по свежести
        n = (d.name or "").strip().lower()
        if n and (r in n or n in r):
            return d
    return None


async def dump_chat(client, entity, title, since_dt):
    safe = "".join(c for c in str(title) if c not in '\\/:*?"<>|').strip()[:80]
    out_path = os.path.join(OUT_DIR, safe + ".txt")
    lines, n_msg, n_voice = [], 0, 0
    # newest-first, обрываемся когда ушли раньше даты, потом переворачиваем
    collected = []
    async for msg in client.iter_messages(entity):
        if msg.date < since_dt:
            break
        collected.append(msg)
    for msg in reversed(collected):
        stamp = msg.date.astimezone().strftime("%Y-%m-%d %H:%M")
        who = sender_name(await msg.get_sender())
        if msg.voice or msg.video_note:
            n_voice += 1
            dur = int(getattr(msg.file, "duration", 0) or 0)
            if TRANSCRIBE_VOICE:
                os.makedirs(VOICE_DIR, exist_ok=True)
                fn = await client.download_media(msg, file=os.path.join(VOICE_DIR, "%s_%s" % (safe, msg.id)))
                txt = transcribe(fn) if fn else "[нет файла]"
                lines.append("[%s] %s (голос, %dс): %s" % (stamp, who, dur, txt))
            else:
                lines.append("[%s] %s (голос, %dс)" % (stamp, who, dur))
        elif msg.text:
            lines.append("[%s] %s: %s" % (stamp, who, msg.text.replace("\n", " ")))
        else:
            continue
        n_msg += 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# %s\n# выгружено %s, сообщений с %s\n\n" % (
            title, datetime.now().strftime("%Y-%m-%d %H:%M"), SINCE))
        f.write("\n".join(lines))
    print("  %-40s %4d сообщ, %d голос -> %s.txt" % (title, n_msg, n_voice, safe))


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    since_dt = datetime.strptime(SINCE, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    print("Вошёл как: %s\n" % sender_name(await client.get_me()))

    print("Читаю список диалогов...")
    dialogs = await client.get_dialogs()
    # справочник всех чатов — чтобы можно было вписать точное имя/id
    idx = os.path.join(OUT_DIR, "_список чатов.txt")
    with open(idx, "w", encoding="utf-8") as f:
        for d in dialogs:
            kind = "группа" if d.is_group else ("канал" if d.is_channel else "личка")
            f.write("%-12s %-14d %s\n" % (kind, d.entity.id, d.name or "?"))
    print("Всего диалогов: %d (полный список: %s)\n" % (len(dialogs), idx))

    for req in CHATS:
        d = find_dialog(req, dialogs)
        if d is None:
            print("  «%s» — не нашёл. Загляни в _список чатов.txt и впиши точное имя/id." % req)
            continue
        try:
            await dump_chat(client, d.entity, d.name, since_dt)
        except Exception as e:
            print("  «%s» — ошибка при выгрузке: %s" % (d.name, e))

    await client.disconnect()
    print("\nГотово. Файлы в: %s" % OUT_DIR)


if __name__ == "__main__":
    asyncio.run(main())
