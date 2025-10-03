pipeline {
    agent any

    triggers {
        pollSCM('H/15 * * * *')   // check repo mỗi 15 phút
    }

    environment {
        // Định nghĩa các biến môi trường ở đây
        // Sử dụng Jenkins Credentials để lưu trữ token một cách an toàn
        BOT_TOKEN = credentials('BOT_TOKEN')
        
        // Các đường dẫn này sẽ là đường dẫn bên trong workspace của Jenkins
        // Jenkins sẽ tự động tạo một thư mục làm việc (workspace) cho mỗi job
        // REPO_PATH = "${env.WORKSPACE}/outsource"
        // DEST_PATH = "${env.WORKSPACE}/outsource_cleaned"
        // JSON_PATH = "${env.WORKSPACE}/ProvinceRules.json"
        // COMMIT_PATH = "${env.WORKSPACE}/commit_message.txt"
        // DEPLOY_REPO = "${env.WORKSPACE}/PM2_VNPTHISL2_DEPLOY"
        // GIT_BRANCH = "UPCODE_VTT"
    }

    stages {
        // Giai đoạn 1: Cài đặt môi trường
        stage('Setup Environment') {
            steps {
                script {
                    // Tạo và kích hoạt môi trường ảo Python
                    // Điều này giúp cô lập dependencies của project
                    sh """
                        scl enable rh-python38 '
                            echo "--- Inside SCL environment ---"
                            
                            # XÓA MÔI TRƯỜNG ẢO CŨ ĐỂ ĐẢM BẢO SẠCH SẼ
                            rm -rf venv

                            # 1. Tạo môi trường ảo (sẽ dùng python 3.8)
                            python -m venv venv
                            
                            # 2. Kích hoạt môi trường ảo
                            source venv/bin/activate
                            
                            # 3. Nâng cấp pip và cài đặt thư viện
                            python -m pip install --upgrade pip
                            pip install -r requirements.txt
                            
                            echo "--- Environment setup complete ---"
                        '
                    """
                }
            }
        }

        // stage('Prepare Deploy Repo') {
        //     steps {
        //         // Sử dụng sh '''...''' để chứa nhiều dòng lệnh shell
        //         sh '''
        //             echo ">>> Đang chuẩn bị kho deploy (DEPLOY_REPO)..."

        //             # <-- THAY ĐỔI URL NÀY CHO ĐÚNG VỚI DỰ ÁN CỦA BẠN
        //             DEPLOY_REPO_URL="https://scm.devops.vnpt.vn/scm.ehealth.it/PM2_VNPTHISL2_DEPLOY.git"

        //             # Logic: Nếu thư mục chưa tồn tại thì clone, nếu đã tồn tại thì pull
        //             if [ -d "${DEPLOY_REPO}" ]; then
        //               echo "Thư mục deploy đã tồn tại. Đang cập nhật..."
        //               cd "${DEPLOY_REPO}"
        //               git pull
        //             else
        //               echo "Thư mục deploy chưa tồn tại. Đang clone..."
        //               git clone "${DEPLOY_REPO_URL}" "${DEPLOY_REPO}"
        //             fi

        //             echo ">>> Kho deploy đã sẵn sàng."
        //         '''
        //     }
        // }

        // Giai đoạn 3: Chạy Bot
        stage('Run Telegram Bot') {
            steps {
                script {
                    echo "Stopping any previous running bot instance..."
                    // Tìm và dừng tiến trình bot cũ nếu có, để tránh chạy nhiều con bot cùng lúc
                    // Lệnh `|| true` để job không bị lỗi nếu không tìm thấy tiến trình nào
                    def SCRIPT_NAME = 'CheckInvalidFile.py' 

                    sh "pkill -f 'CheckInvalidFile.py' || true"
                    
                    echo "Starting the bot in the background..."
                    // Chạy bot trong nền (background) bằng `nohup` và `&`
                    // Jenkins job sẽ không bị "treo" ở bước này và có thể kết thúc
                    // Log của bot sẽ được ghi vào file bot.log
                    sh "scl enable rh-python38 'nohup venv/bin/python CheckInvalidFile.py > bot.log 2>&1 &'"
                }
            }
        }
    }
    
    post {
        // Kịch bản này sẽ chạy NẾU pipeline THÀNH CÔNG
        success {
            script {
                echo "Pipeline thành công! Đang gửi thông báo..."
                
                // Sử dụng withCredentials để truy cập biến BOT_TOKEN một cách an toàn
                withCredentials([string(credentialsId: 'BOT_TOKEN', variable: 'TELEGRAM_TOKEN')]) {
                    // Tạo nội dung tin nhắn
                    def successMessage = "✅ **[THÀNH CÔNG]** Job **'${env.JOB_NAME}'** build **#${env.BUILD_NUMBER}** đã khởi động lại Bot thành công."
                    
                    // Gửi tin nhắn bằng lệnh sh với curl
                    // Biến TELEGRAM_TOKEN bây giờ là một biến môi trường thông thường, an toàn để sử dụng
                    sh """
                        curl -s -X POST -H 'Content-Type: application/json' \
                            -d '{"chat_id": "-4960856865", "text": "${successMessage}", "parse_mode": "Markdown"}' \
                            "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage"
                    """
                }
            }
        }
        
        // Kịch bản này sẽ chạy NẾU pipeline THẤT BẠI
        failure {
            script {
                echo "Pipeline thất bại! Đang gửi thông báo..."

                withCredentials([string(credentialsId: 'BOT_TOKEN', variable: 'TELEGRAM_TOKEN')]) {
                    // Tạo nội dung tin nhắn
                    def failureMessage = "❌ **[THẤT BẠI]** Job **'${env.JOB_NAME}'** build **#${env.BUILD_NUMBER}** đã gặp lỗi.\nXem chi tiết tại: ${env.BUILD_URL}"
                    
                    // Gửi tin nhắn bằng lệnh sh với curl
                    sh """
                        curl -s -X POST -H 'Content-Type: application/json' \
                            -d '{"chat_id": "-4960856865", "text": "${failureMessage}", "parse_mode": "Markdown"}' \
                            "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage"
                    """
                }
            }
        }
    }
}