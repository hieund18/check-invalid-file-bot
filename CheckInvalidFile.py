import os
import json
import re
import shutil
import subprocess
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from git import Repo, exc

# ===================================
# === CONFIGURATION (Cấu hình) =====
# ===================================

# --- Bot & Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "7664663330:AAGk132lgzUlSlKPtHYTds5GHtvuLEjvfRM")

# --- Git Repositories ---
# Repo nguồn chứa code cần kiểm tra và deploy
SOURCE_REPO_URL = "http://10.168.3.145:8887/outsource.git"
SOURCE_REPO_BRANCH = "UPCODE_VTT"

# Repo đích, nơi sẽ chứa code đã được làm sạch và deploy
DEPLOY_REPO_URL = "https://scm.devops.vnpt.vn/scm.ehealth.it/PM2_VNPTHISL2_DEPLOY.git"
DEPLOY_REPO_BRANCH = "master"

# --- Paths (Đường dẫn) ---
# Sử dụng một thư mục gốc để chứa mọi thứ cho gọn
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
REPO_PATH = os.path.join(WORKSPACE, "outsource")
DEST_PATH = os.path.join(WORKSPACE, "outsource_cleaned")
JSON_PATH = os.path.join(WORKSPACE, "ProvinceRules.json")
DEPLOY_REPO = os.path.join(WORKSPACE, "PM2_VNPTHISL2_DEPLOY")

# --- Validation Rules ---
MAX_TELEGRAM_MESSAGE_LEN = 4000
FORBIDDEN_SQL_KEYWORDS = ["update", "delete", "insert", "truncate", "drop"]

# ===================================
# === UTILITY FUNCTIONS (Hàm tiện ích) ===
# ===================================

def prepare_repo(repo_path, repo_url, branch):
    """
    Chuẩn bị một repository: clone nếu chưa có, pull nếu đã có.
    """
    print(f"--- Chuẩn bị kho git tại: {repo_path} ---")
    try:
        if os.path.exists(repo_path):
            print(f"Thư mục đã tồn tại. Đang cập nhật từ branch '{branch}'...")
            repo = Repo(repo_path)
            # Kiểm tra xem remote origin có đúng không
            if repo.remotes.origin.url != repo_url:
                 print(f"URL của remote đã thay đổi. Đang cập nhật...")
                 repo.delete_remote('origin')
                 repo.create_remote('origin', repo_url)
            repo.git.checkout(branch)
            repo.git.pull()
            print("✅ Cập nhật thành công.")
        else:
            print(f"Thư mục chưa tồn tại. Đang clone từ branch '{branch}'...")
            Repo.clone_from(repo_url, repo_path, branch=branch)
            print("✅ Clone thành công.")
        return True
    except exc.GitCommandError as e:
        print(f"❌ LỖI GIT: Không thể chuẩn bị kho git {repo_path}.")
        print(f"Lỗi chi tiết: {e}")
        return False
    except Exception as e:
        print(f"❌ LỖI KHÔNG XÁC ĐỊNH: {e}")
        return False

def remove_sql_comments(text):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'--.*', '', text)
    return text

def load_province_rules(json_path):
    if not os.path.exists(json_path):
        print(f"❌ Lỗi: Không tìm thấy file ProvinceRules.json tại '{json_path}'")
        return {}
    with open(json_path, 'r', encoding='utf-8') as f:
        province_data = json.load(f)
    rules = {}
    for entry in province_data:
        ma_tinh = entry["ma_tinh"].strip().lower()
        if ma_tinh:
            rules[ma_tinh] = [s.lower() for s in entry["duoi_file"]]
    return rules

def get_today_date_folder(repo_path):
    today_str = datetime.now().strftime("%Y%m%d")
    repo = Repo(repo_path)
    all_files = repo.git.ls_files().splitlines()
    folder_dates = {f.split("/")[0] for f in all_files if re.fullmatch(r"\d{8}", f.split("/")[0])}
    return today_str if today_str in folder_dates else None

def validate_file(repo_path, file, commit_msg, province_rules):
    matched = False
    ma_tinh_match = None
    reason = ""

    for ma_tinh, duoi_files in province_rules.items():
        if ma_tinh in commit_msg:
            ma_tinh_match = ma_tinh
            if any(duoi in file.lower() for duoi in duoi_files):
                matched = True
                break

    if not ma_tinh_match:
        return False, "Mã tỉnh không hợp lệ", None
    elif not matched:
        return False, "Tên file không chứa mã đơn vị hợp lệ", ma_tinh_match

    if file.lower().endswith(".sql"):
        if "duc" not in file.lower():
            file_path = os.path.join(repo_path, file)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as sql_file:
                    lines = sql_file.readlines()
                    cleaned = remove_sql_comments("".join(lines).lower())
                    found = [kw for kw in FORBIDDEN_SQL_KEYWORDS if kw in cleaned]
                    if found:
                        return False, f"File SQL chứa từ khóa không hợp lệ: {', '.join(found)}", ma_tinh_match
                    while lines and not lines[-1].strip():
                        lines.pop()
                    if not lines or not lines[-1].strip().endswith("/"):
                        return False, "File SQL không kết thúc bằng dấu '/'", ma_tinh_match
            except Exception as e:
                return False, f"Không thể đọc file: {e}", ma_tinh_match
    return True, "", ma_tinh_match

def copy_folder(src, dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

# ===================================
# === TELEGRAM COMMAND HANDLERS =====
# ===================================

async def checkinvalidfile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ma_tinh_filter = context.args[0].strip().lower() if context.args else None
    
    await context.bot.send_message(chat_id=chat_id, text="⏳ Đang cập nhật lại repo nguồn...")
    if not prepare_repo(REPO_PATH, SOURCE_REPO_URL, SOURCE_REPO_BRANCH):
        await context.bot.send_message(chat_id=chat_id, text="❌ Lỗi nghiêm trọng khi cập nhật repo nguồn. Vui lòng kiểm tra log.")
        return

    province_rules = load_province_rules(JSON_PATH)
    if not province_rules:
         await context.bot.send_message(chat_id=chat_id, text="❌ Không thể tải file luật. Kiểm tra file `ProvinceRules.json`.")
         return

    if ma_tinh_filter and ma_tinh_filter not in province_rules:
        await update.message.reply_text(f"❌ Mã tỉnh `{ma_tinh_filter}` không hợp lệ. Vui lòng kiểm tra lại.")
        return

    latest_folder = get_today_date_folder(REPO_PATH)
    if not latest_folder:
        await context.bot.send_message(chat_id=chat_id, text="❌ Không tìm thấy thư mục của ngày hôm nay trong repo nguồn.")
        return

    target_folder = latest_folder + "/"
    await context.bot.send_message(chat_id=chat_id, text=f"📂 Đang kiểm tra thư mục: `{target_folder}`")
    
    repo = Repo(REPO_PATH)
    all_files = repo.git.ls_files().splitlines()
    filtered_files = [f for f in all_files if f.startswith(target_folder)]
    report = []
    for file in filtered_files:
        commits = list(repo.iter_commits(paths=file, max_count=1))
        if not commits: continue
        commit = commits[0]
        commit_msg = commit.message.strip().lower()
        if ma_tinh_filter and ma_tinh_filter not in commit_msg: continue
        is_valid, reason, ma_tinh_match = validate_file(REPO_PATH, file, commit_msg, province_rules)
        if not is_valid:
            report.append(
                f"❌ File không hợp lệ: {file}\n"
                f"   📌 Lý do: {reason}\n"
                f"   📝 Mã tỉnh: {ma_tinh_match or 'Không xác định'}\n"
                f"   👤 Author: {commit.author.name}\n"
                f"   📅 Date:   {commit.committed_datetime}"
            )
    if not report:
        report = [f"✅ Tất cả file hợp lệ cho tỉnh `{ma_tinh_filter.upper()}`." if ma_tinh_filter else "✅ Tất cả file đều hợp lệ."]

    # Gửi report
    current_msg = ""
    for line in report:
        if len(current_msg) + len(line) + 2 > MAX_TELEGRAM_MESSAGE_LEN:
            await context.bot.send_message(chat_id=chat_id, text=current_msg.strip())
            current_msg = ""
        current_msg += line + "\n\n"
    if current_msg.strip():
        await context.bot.send_message(chat_id=chat_id, text=current_msg.strip())


async def upcode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(context.args) < 2:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Cú pháp sai!\n/upcode <thời_gian> <commit_message>\n\nVí dụ: `/upcode 17H19 https://cntt.vnpt.vn/browse/IT360-1545724`"
        )
        return

    time_str = context.args[0].strip().upper()
    commit_msg_today = " ".join(context.args[1:]).strip()

    if not re.match(r"^\d{2}H\d{2}$", time_str):
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Định dạng thời gian '{time_str}' không hợp lệ. Ví dụ: 17H19")
        return

    await context.bot.send_message(chat_id=chat_id, text=f"🚀 Bắt đầu deploy với thời gian `{time_str}`...")
    
    # 1. Pull repo nguồn
    await context.bot.send_message(chat_id=chat_id, text="[1/6] ⏳ Đang cập nhật repo nguồn...")
    if not prepare_repo(REPO_PATH, SOURCE_REPO_URL, SOURCE_REPO_BRANCH):
        await context.bot.send_message(chat_id=chat_id, text="❌ Lỗi khi cập nhật repo nguồn.")
        return
    await context.bot.send_message(chat_id=chat_id, text="✅ Repo nguồn đã được cập nhật.")

    latest_folder = get_today_date_folder(REPO_PATH)
    if not latest_folder:
        await context.bot.send_message(chat_id=chat_id, text="❌ Không tìm thấy thư mục ngày hôm nay trong repo nguồn.")
        return

    # 2. Copy sang thư mục làm sạch
    await context.bot.send_message(chat_id=chat_id, text=f"[2/6] 📂 Đang copy `{latest_folder}` để xử lý...")
    original_path = os.path.join(REPO_PATH, latest_folder)
    cleaned_path = os.path.join(DEST_PATH, latest_folder)
    try:
        copy_folder(original_path, cleaned_path)
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi sao chép thư mục: {e}")
        return

    # 3. Dọn dẹp file không hợp lệ và jrxml
    await context.bot.send_message(chat_id=chat_id, text="[3/6] 🧹 Đang dọn dẹp file không hợp lệ...")
    deleted_count = 0
    try:
        province_rules = load_province_rules(JSON_PATH)
        repo = Repo(REPO_PATH)
        all_files = [f for f in repo.git.ls_files().splitlines() if f.startswith(latest_folder + "/")]
        
        for file in all_files:
            commits = list(repo.iter_commits(paths=file, max_count=1))
            if not commits: continue
            is_valid, _, _ = validate_file(REPO_PATH, file, commits[0].message.strip().lower(), province_rules)
            if not is_valid:
                file_to_delete = os.path.join(cleaned_path, os.path.relpath(file, latest_folder))
                if os.path.exists(file_to_delete):
                    os.remove(file_to_delete)
                    deleted_count += 1
        
        for root, _, files in os.walk(cleaned_path):
            for file_name in files:
                if file_name.lower().endswith(".jrxml"):
                    jrxml_file_path = os.path.join(root, file_name)
                    if os.path.exists(jrxml_file_path):
                        os.remove(jrxml_file_path)
                        deleted_count += 1
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Đã xóa {deleted_count} file không hợp lệ.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi xóa file: {e}")
        return

    # 4. Pull repo deploy
    await context.bot.send_message(chat_id=chat_id, text="[4/6] ⏳ Đang cập nhật repo deploy...")
    if not prepare_repo(DEPLOY_REPO, DEPLOY_REPO_URL, DEPLOY_REPO_BRANCH):
        await context.bot.send_message(chat_id=chat_id, text="❌ Lỗi khi cập nhật repo deploy.")
        return
    await context.bot.send_message(chat_id=chat_id, text="✅ Repo deploy đã được cập nhật.")

    # 5. Copy vào các thư mục deploy
    await context.bot.send_message(chat_id=chat_id, text="[5/6] 🚀 Đang copy code sạch vào thư mục deploy...")
    deploy_folders = [f"BVDAKHOA_{time_str}", f"BVLONGAN_{time_str}"]
    target_latest_path = os.path.join(DEPLOY_REPO, latest_folder)
    for folder in deploy_folders:
        try:
            target_deploy_path = os.path.join(target_latest_path, folder)
            copy_folder(cleaned_path, target_deploy_path)
            await context.bot.send_message(chat_id=chat_id, text=f"✅ Đã copy vào `{os.path.relpath(target_deploy_path, WORKSPACE)}`")
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi copy sang {folder}: {e}")
            return
            
    # 6. Commit & Push
    await context.bot.send_message(chat_id=chat_id, text="[6/6] ⬆️ Đang commit và push lên Git...")
    try:
        repo = Repo(DEPLOY_REPO)
        repo.git.add(A=True)
        repo.index.commit(commit_msg_today)
        repo.git.push("origin", DEPLOY_REPO_BRANCH)
        await context.bot.send_message(chat_id=chat_id, text=f"🎉 **DEPLOY THÀNH CÔNG!**\nĐã push lên git với message:\n`{commit_msg_today}`")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi commit/push code:\n{e}")

# ===================================
# === MAIN EXECUTION ================
# ===================================

if __name__ == "__main__":
    print("=============================================")
    print("=== KHỞI ĐỘNG BOT DEPLOY TỰ ĐỘNG ===")
    print("=============================================")
    
    # Bước 1: Chuẩn bị repo nguồn
    if not prepare_repo(REPO_PATH, SOURCE_REPO_URL, SOURCE_REPO_BRANCH):
        print(" >> Dừng chương trình do không thể chuẩn bị repo nguồn.")
        exit(1)

    # Bước 2: Chuẩn bị repo deploy
    if not prepare_repo(DEPLOY_REPO, DEPLOY_REPO_URL, DEPLOY_REPO_BRANCH):
        print(" >> Dừng chương trình do không thể chuẩn bị repo deploy.")
        exit(1)
        
    # Bước 3: Khởi động bot
    print("\n--- Tất cả kho git đã sẵn sàng. Khởi động bot... ---")
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("❌ Lỗi: BOT_TOKEN chưa được cấu hình. Vui lòng sửa lại trong script.")
        exit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("checkinvalidfile", checkinvalidfile_command))
    app.add_handler(CommandHandler("upcode", upcode_command))
    
    print("🤖 Bot đang chạy... Nhấn CTRL+C để dừng.")
    app.run_polling()