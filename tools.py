# tools.py
import os
import csv
import sys

CSV_PATH = "data/products.csv"
IMG_DIR  = "images/products"
LOG_PATH = "image_rename_log.txt"

def open_csv_safely(path):
    """
    文字コードを順に試して開く（utf-8 → utf-8-sig → cp932）
    """
    tried = []
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            f = open(path, "r", encoding=enc, newline="")
            # ヘッダー1行だけ読んで戻す（読み取り確認）
            pos = f.tell()
            f.readline()
            f.seek(pos)
            print(f"🔎 CSV encoding detected: {enc}")
            return f
        except Exception as e:
            tried.append(f"{enc}: {e}")
    raise RuntimeError("CSV を開けませんでした:\n" + "\n".join(tried))

def normalize(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_").replace("-", "_")

def main():
    if not os.path.exists(CSV_PATH):
        print(f"❌ CSV が見つかりません: {CSV_PATH}")
        return
    if not os.path.exists(IMG_DIR):
        print(f"❌ 画像フォルダが見つかりません: {IMG_DIR}")
        return

    print("🔄 CSVファイルと画像フォルダを確認中...")

    # 画像フォルダの一覧を作っておく
    files = os.listdir(IMG_DIR)
    files_lower = [f.lower() for f in files]

    renamed = []
    not_found = []

    # CSV を安全に開く
    with open_csv_safely(CSV_PATH) as f:
        reader = csv.DictReader(f)
        # 想定する列名
        #   id / name / file_name（file_nameは無くてもOK）
        for row in reader:
            pid = (row.get("id") or "").strip()
            name = row.get("name") or ""
            file_name_hint = row.get("file_name") or ""

            if not pid:
                continue

            target_file = None

            # 1) file_name があればそれを優先（拡張子はなんでもOK）
            if file_name_hint:
                try_name = file_name_hint.lower()
                # 完全一致
                if try_name in files_lower:
                    target_file = files[files_lower.index(try_name)]
                else:
                    # 拡張子違いの可能性 → stem で探す
                    stem = os.path.splitext(try_name)[0]
                    for f in files:
                        if os.path.splitext(f.lower())[0] == stem:
                            target_file = f
                            break

            # 2) ダメなら商品名の部分一致でざっくり探す
            if not target_file and name:
                words = [w for w in normalize(name).split("_") if w]
                for f in files:
                    fl = normalize(os.path.splitext(f)[0])
                    if all(w in fl for w in words[:2]):  # 2語くらい一致で採用
                        target_file = f
                        break

            if target_file:
                old_path = os.path.join(IMG_DIR, target_file)
                ext = os.path.splitext(target_file)[1].lower() or ".jpg"
                new_name = f"{pid}{ext}"
                new_path = os.path.join(IMG_DIR, new_name)

                if os.path.abspath(old_path) == os.path.abspath(new_path):
                    # すでに想定名ならスキップ
                    print(f"↪ そのまま: {target_file}")
                else:
                    # 既に同名がある場合は上書きを避けてスキップ
                    if os.path.exists(new_path):
                        print(f"⚠ 同名ありでスキップ: {new_name}  ← {target_file}")
                    else:
                        os.rename(old_path, new_path)
                        renamed.append((target_file, new_name))
                        print(f"✅ {target_file} → {new_name}")
            else:
                not_found.append(name or f"(id={pid})")

    # ログ出力
    with open(LOG_PATH, "w", encoding="utf-8") as log:
        log.write("=== 画像ファイル名変更ログ ===\n\n")
        for old, new in renamed:
            log.write(f"✅ {old} → {new}\n")
        if not_found:
            log.write("\n=== 見つからなかった商品 ===\n")
            for n in not_found:
                log.write(f"⚠ {n}\n")

    print(f"\n📄 ログ: {LOG_PATH}")
    print(f"🔚 完了: 変更 {len(renamed)} 件 / 未マッチ {len(not_found)} 件")

if __name__ == "__main__":
    main()
