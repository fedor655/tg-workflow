# -*- coding: utf-8 -*-
"""
Расшифровка аудио/видео в текст с таймкодами (Whisper large-v3).

Использование:
  1) перетащить файл (или несколько) на _расшифровать.bat
  2) или запустить без аргументов — возьмёт самую свежую запись из папки
     скрипта и подпапки «созвоны»

Результат кладётся в подпапку «расшифровки» рядом со скриптом.
"""
import os, sys, glob, subprocess, tempfile, time

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "расшифровки")
# где искать свежую запись, если файл не передан явно:
WATCH_DIRS = [BASE, os.path.join(BASE, "созвоны")]
MEDIA = (".mkv", ".mp4", ".m4a", ".mp3", ".wav", ".ogg", ".opus", ".webm", ".mov", ".avi")


def newest_media():
    found = []
    for d in WATCH_DIRS:
        for ext in MEDIA:
            found += glob.glob(os.path.join(d, "*" + ext))
    if not found:
        return None
    return max(found, key=os.path.getmtime)


def to_wav(src, dst):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src,
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst],
        check=True)


def transcribe(wav, pipe):
    segs, _ = pipe.transcribe(wav, language="ru", batch_size=8, vad_filter=True,
                              vad_parameters=dict(min_silence_duration_ms=700))
    lines = []
    for s in segs:
        m, sec = divmod(int(s.start), 60)
        h, m = divmod(m, 60)
        lines.append("[%d:%02d:%02d] %s" % (h, m, sec, s.text.strip()))
    return lines


def main():
    files = [a for a in sys.argv[1:] if os.path.isfile(a)]
    if not files:
        n = newest_media()
        if not n:
            print("Не нашёл ни одной записи. Перетащи файл на .bat"); return
        print("Файл не указан — беру самую свежую запись:")
        print("  " + os.path.basename(n))
        files = [n]

    os.makedirs(OUT_DIR, exist_ok=True)
    todo = []
    for f in files:
        dst = os.path.join(OUT_DIR, os.path.splitext(os.path.basename(f))[0] + ".txt")
        if os.path.exists(dst):
            print("уже расшифрован, пропускаю: " + os.path.basename(f))
            continue
        todo.append((f, dst))
    if not todo:
        print("Нечего делать."); return

    print("\nЗагружаю модель распознавания (первый запуск — дольше)...")
    from faster_whisper import WhisperModel, BatchedInferencePipeline
    try:
        model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    except Exception:
        print("Видеокарта недоступна, иду на процессоре — будет медленнее.")
        model = WhisperModel("large-v3", device="cpu", compute_type="int8")
    pipe = BatchedInferencePipeline(model=model)
    print("Модель готова.\n")

    for src, dst in todo:
        t0 = time.time()
        print("→ " + os.path.basename(src))
        wav = os.path.join(tempfile.gettempdir(), "stt_tmp.wav")
        try:
            to_wav(src, wav)
        except Exception as e:
            print("   не смог извлечь звук: %s" % e); continue
        lines = transcribe(wav, pipe)
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write("# " + os.path.basename(src) + "\n")
            fh.write("# расшифровано автоматически (Whisper large-v3), возможны ошибки\n\n")
            fh.write("\n".join(lines))
        try:
            os.remove(wav)
        except OSError:
            pass
        print("   готово: %d реплик за %d сек" % (len(lines), time.time() - t0))
        print("   " + dst + "\n")

    print("Всё. Файлы лежат в: " + OUT_DIR)


if __name__ == "__main__":
    main()
