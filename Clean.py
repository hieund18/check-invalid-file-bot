import os
import json
import re
import shutil
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from git import Repo

# === Config ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "7664663330:AAGk132lgzUlSlKPtHYTds5GHtvuLEjvfRM")
REPO_PATH = os.getenv("REPO_PATH")
DEST_PATH = os.getenv("DEST_PATH")
JSON_PATH = os.getenv("JSON_PATH")
DEPLOY_REPO = os.getenv("DEPLOY_REPO")
GIT_BRANCH = os.getenv("GIT_BRANCH")
MAX_TELEGRAM_MESSAGE_LEN = 4000
FORBIDDEN_SQL_KEYWORDS = ["update", "delete", "insert", "truncate", "drop"]
# === Utility ===
def remove_sql_comments(text):
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r'--.*', '', text)
    return text

def load_province_rules(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        province_data = json.load(f)
    rules = {}
    for entry in province_data:
        ma_tinh = entry["ma_tinh"].strip().lower()
        if ma_tinh:
            rules[ma_tinh] = [s.lower() for s in entry["duoi_file"]]
    return rules

def git_pull(repo_path):
    repo = Repo(repo_path)
    repo.git.checkout(GIT_BRANCH)
    repo.git.pull()

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
        if("duc" not in file.lower()):
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

def check_files_validity(repo_path, province_rules, target_folder, ma_tinh_filter=None):
    repo = Repo(repo_path)
    all_files = repo.git.ls_files().splitlines()
    filtered_files = [f for f in all_files if f.startswith(target_folder)]

    report = []

    for file in filtered_files:
        commits = list(repo.iter_commits(paths=file, max_count=1))
        if not commits:
            continue
        commit = commits[0]
        commit_msg = commit.message.strip().lower()

        if ma_tinh_filter and ma_tinh_filter not in commit_msg:
            continue

        is_valid, reason, ma_tinh_match = validate_file(repo_path, file, commit_msg, province_rules)
        if not is_valid:
            report.append(
                f"❌ File không hợp lệ: {file}\n"
                f"   📌 Lý do: {reason}\n"
                f"   📝 Mã tỉnh: {ma_tinh_match or 'Không xác định'}\n"
                f"   👤 Author: {commit.author.name}\n"
                f"   📅 Date:   {commit.committed_datetime}"
            )

    if not report:
        return [f"✅ Tất cả file hợp lệ cho tỉnh `{ma_tinh_filter.upper()}`." if ma_tinh_filter else "✅ Tất cả file đều hợp lệ."]
    return report

async def send_long_report(chat_id, context, report_lines):
    current_msg = ""
    for line in report_lines:
        if len(current_msg) + len(line) + 2 > MAX_TELEGRAM_MESSAGE_LEN:
            await context.bot.send_message(chat_id=chat_id, text=current_msg.strip())
            current_msg = ""
        current_msg += line + "\n\n"
    if current_msg.strip():
        await context.bot.send_message(chat_id=chat_id, text=current_msg.strip())

# === /checkvalidfile
async def checkvalidfile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ma_tinh_filter = context.args[0].strip().lower() if context.args else None

    province_rules = load_province_rules(JSON_PATH)
    if ma_tinh_filter and ma_tinh_filter not in province_rules:
        await update.message.reply_text(f"❌ Mã tỉnh `{ma_tinh_filter}` không hợp lệ. Vui lòng kiểm tra lại.")
        return

    await context.bot.send_message(chat_id=chat_id, text="⏳ Đang thực hiện pull code mới nhất...")
    try:
        git_pull(REPO_PATH)
        await context.bot.send_message(chat_id=chat_id, text="✅ Đã cập nhật code mới nhất.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi git pull:\n{e}")
        return

    latest_folder = get_today_date_folder(REPO_PATH)
    if not latest_folder:
        await context.bot.send_message(chat_id=chat_id, text="❌ Không tìm thấy thư mục ngày hôm nay.")
        return

    target_folder = latest_folder + "/"
    await context.bot.send_message(chat_id=chat_id, text=f"📂 Đang kiểm tra thư mục ngày hôm nay: `{target_folder}`")
    await context.bot.send_message(chat_id=chat_id, text="🔍 Đang kiểm tra file hợp lệ...")

    try:
        report_lines = check_files_validity(REPO_PATH, province_rules, target_folder, ma_tinh_filter)
        await send_long_report(chat_id, context, report_lines)
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi kiểm tra file:\n{e}")

def copy_folder(src, dst):
    if os.path.exists(dst):
        shutil.rmtree(dst)  # Xóa thư mục đích nếu đã tồn tại
    shutil.copytree(src, dst)  # Copy lại toàn bộ

async def deploy_to_folder(context, chat_id, commit_msg_today, latest_folder, cleaned_path, deploy_folder):
    target_latest_path = os.path.join(DEPLOY_REPO, latest_folder)
    target_deploy_path = os.path.join(target_latest_path, deploy_folder)

    os.makedirs(target_latest_path, exist_ok=True)
    os.makedirs(target_deploy_path, exist_ok=True)

    try:
        for item in os.listdir(cleaned_path):
            s = os.path.join(cleaned_path, item)
            d = os.path.join(target_deploy_path, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Đã copy sang `{target_deploy_path}`.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi copy sang deploy {deploy_folder}:\n{e}")
        return False
    return True

async def upcode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(context.args) < 2:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Vui lòng nhập đúng cú pháp:\n/upcode <tên_thư_mục> <commit_message>\n\nVí dụ: /upcode BVDAKHOA_17H19 https://cntt.vnpt.vn/browse/IT360-1539852"
        )
        return
    
    deploy_folder = context.args[0].strip().upper()

    if not re.match(r"^(BVDAKHOA|BVLONGAN)_\d{2}H\d{2}$", deploy_folder):
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Tên thư mục không đúng định dạng.\nVí dụ hợp lệ: BVDAKHOA_17H09 hoặc BVLONGAN_17H09")
        return
    
    # Commit message lấy trực tiếp từ câu lệnh
    commit_msg_today = " ".join(context.args[1:]).strip()
    if not commit_msg_today:
        await context.bot.send_message(chat_id=chat_id, text="❌ Bạn chưa nhập commit message.")
        return

    await context.bot.send_message(chat_id=chat_id, text=f"🚀 Bắt đầu upcode với thư mục deploy: `{deploy_folder}`")
    await context.bot.send_message(chat_id=chat_id, text=f"📝 Commit message: `{commit_msg_today}`")

    # === Git pull repo gốc ===
    await context.bot.send_message(chat_id=chat_id, text="⏳ Đang thực hiện pull code mới nhất...")
    try:
        git_pull(REPO_PATH)
        await context.bot.send_message(chat_id=chat_id, text="✅ Đã cập nhật code mới nhất.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Git pull lỗi: {e}")
        return
    
    latest_folder = get_today_date_folder(REPO_PATH)
    if not latest_folder:
        await context.bot.send_message(chat_id=chat_id, text="❌ Không tìm thấy thư mục ngày hôm nay.")
        return

    original_path = os.path.join(REPO_PATH, latest_folder)
    cleaned_path = os.path.join(DEST_PATH, latest_folder)

    try:
        copy_folder(original_path, cleaned_path)
        await context.bot.send_message(chat_id=chat_id, text=f"📂 Đã copy thư mục {latest_folder} sang {cleaned_path}")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi sao chép thư mục:\n{e}")
        return

    try:
        province_rules = load_province_rules(JSON_PATH)
        repo = Repo(REPO_PATH)
        all_files = repo.git.ls_files().splitlines()
        filtered_files = [f for f in all_files if f.startswith(latest_folder + "/")]

        deleted = 0
        for file in filtered_files:
            commits = list(repo.iter_commits(paths=file, max_count=1))
            if not commits:
                continue
            commit = commits[0]
            commit_msg = commit.message.strip().lower()

            is_valid, _, _ = validate_file(REPO_PATH, file, commit_msg, province_rules)
            if not is_valid:
                relative_path = file[len(latest_folder)+1:]
                file_to_delete = os.path.join(cleaned_path, relative_path)
                if os.path.exists(file_to_delete):
                    os.remove(file_to_delete)
                    deleted += 1

            for root, _, files in os.walk(cleaned_path):
                for file_name in files:
                    if file_name.lower().endswith(".jrxml"):
                        jrxml_file_to_delete = os.path.join(root, file_name)
                        if os.path.exists(jrxml_file_to_delete):
                            os.remove(jrxml_file_to_delete)
                            deleted += 1

        await context.bot.send_message(chat_id=chat_id, text=f"🧹 Đã xóa {deleted} file không hợp lệ và file jrxml.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi xóa file:\n{e}")
    
    await context.bot.send_message(chat_id=chat_id, text="⏳ Đang thực hiện pull code mới nhất trên thư mục deploy...")
    try:
        repo = Repo(DEPLOY_REPO)
        repo.git.checkout("master")
        repo.git.pull()
        await context.bot.send_message(chat_id=chat_id, text="✅ Đã cập nhật code mới nhất trên thư mục deploy.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Git pull lỗi: {e}")
        return

    # Tạo thư mục deploy dạng: {DEPLOY_REPO}/{latest_folder}/{deploy_folder}
    target_latest_path = os.path.join(DEPLOY_REPO, latest_folder)
    target_deploy_path = os.path.join(target_latest_path, deploy_folder)

    # Tạo thư mục ngày nếu chưa có
    os.makedirs(target_latest_path, exist_ok=True)

    # Tạo thư mục deploy (VD: BVDAKHOA_17H09)
    os.makedirs(target_deploy_path, exist_ok=True)

    try:
        # Copy toàn bộ nội dung từ cleaned_path vào target_deploy_path
        for item in os.listdir(cleaned_path):
            s = os.path.join(cleaned_path, item)
            d = os.path.join(target_deploy_path, item)
            
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

        await context.bot.send_message(chat_id=chat_id, text=f"✅ Đã copy sang `{target_deploy_path}`.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi copy sang deploy:\n{e}")
        return
    
    # === Commit & Push vào repo deploy ===
    try:
        repo = Repo(DEPLOY_REPO)
        repo.git.checkout("master")

        # Add toàn bộ thay đổi
        repo.git.add(A=True)

        # Commit với nội dung từ file commit
        repo.index.commit(commit_msg_today)

        # Push lên remote
        repo.git.push("origin", "master")

        await context.bot.send_message(chat_id=chat_id, text=f"✅ Đã commit và push lên git với message:\n{commit_msg_today}")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi commit/push code:\n{e}")
        return
    
async def deploy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(context.args) < 1:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Vui lòng nhập đúng cú pháp:\n/deploy <commit_message>\n\nVí dụ: /deploy https://cntt.vnpt.vn/browse/IT360-1539852"
        )
        return

    commit_msg_today = " ".join(context.args).strip()
    if not commit_msg_today:
        await context.bot.send_message(chat_id=chat_id, text="❌ Bạn chưa nhập commit message.")
        return

    await context.bot.send_message(chat_id=chat_id, text=f"🚀 Bắt đầu deploy với commit:\n`{commit_msg_today}`")

    # Git pull repo gốc
    await context.bot.send_message(chat_id=chat_id, text="⏳ Đang thực hiện pull code mới nhất...")
    try:
        git_pull(REPO_PATH)
        await context.bot.send_message(chat_id=chat_id, text="✅ Đã cập nhật code mới nhất.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Git pull lỗi: {e}")
        return

    latest_folder = get_today_date_folder(REPO_PATH)
    if not latest_folder:
        await context.bot.send_message(chat_id=chat_id, text="❌ Không tìm thấy thư mục ngày hôm nay.")
        return

    original_path = os.path.join(REPO_PATH, latest_folder)
    cleaned_path = os.path.join(DEST_PATH, latest_folder)

    try:
        copy_folder(original_path, cleaned_path)
        await context.bot.send_message(chat_id=chat_id, text=f"📂 Đã copy thư mục {latest_folder} sang {cleaned_path}")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi sao chép thư mục:\n{e}")
        return

    # Clean file invalid
    try:
        province_rules = load_province_rules(JSON_PATH)
        repo = Repo(REPO_PATH)
        all_files = repo.git.ls_files().splitlines()
        filtered_files = [f for f in all_files if f.startswith(latest_folder + "/")]

        deleted = 0
        for file in filtered_files:
            commits = list(repo.iter_commits(paths=file, max_count=1))
            if not commits:
                continue
            commit = commits[0]
            commit_msg = commit.message.strip().lower()

            is_valid, _, _ = validate_file(REPO_PATH, file, commit_msg, province_rules)
            if not is_valid:
                relative_path = file[len(latest_folder)+1:]
                file_to_delete = os.path.join(cleaned_path, relative_path)
                if os.path.exists(file_to_delete):
                    os.remove(file_to_delete)
                    deleted += 1

        for root, _, files in os.walk(cleaned_path):
            for file_name in files:
                if file_name.lower().endswith(".jrxml"):
                    jrxml_file_to_delete = os.path.join(root, file_name)
                    if os.path.exists(jrxml_file_to_delete):
                        os.remove(jrxml_file_to_delete)
                        deleted += 1

        await context.bot.send_message(chat_id=chat_id, text=f"🧹 Đã xóa {deleted} file không hợp lệ và file jrxml.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi xóa file:\n{e}")

    # Pull repo deploy
    await context.bot.send_message(chat_id=chat_id, text="⏳ Đang cập nhật repo deploy...")
    try:
        repo = Repo(DEPLOY_REPO)
        repo.git.checkout("master")
        repo.git.pull()
        await context.bot.send_message(chat_id=chat_id, text="✅ Repo deploy đã được cập nhật.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Git pull lỗi: {e}")
        return

    # Deploy vào 2 thư mục mặc định
    deploy_folders = ["BVDAKHOA_17H19", "BVLONGAN_17H19"]
    for folder in deploy_folders:
        success = await deploy_to_folder(context, chat_id, commit_msg_today, latest_folder, cleaned_path, folder)
        if not success:
            return

    # Commit & push deploy repo
    try:
        repo = Repo(DEPLOY_REPO)
        repo.git.checkout("master")
        repo.git.add(A=True)
        repo.index.commit(commit_msg_today)
        repo.git.push("origin", "master")
        await context.bot.send_message(chat_id=chat_id, text=f"✅ Đã commit và push lên git với message:\n{commit_msg_today}")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Lỗi khi commit/push code:\n{e}")
        return


# === Main
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("checkinvalidfile", checkvalidfile_command))
    app.add_handler(CommandHandler("upcode", upcode_command))
    app.add_handler(CommandHandler("deploy", deploy_command))

    print("🤖 Bot đang chạy...")
    app.run_polling()
